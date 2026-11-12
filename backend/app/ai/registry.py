"""Model versioning: each training run is an immutable version directory with a manifest.

    artifacts/
      registry.json                    {"latest": "<version>", "versions": [...]}
      <version>/manifest.json          config, dataset fingerprint, git commit, SHA-256 per file
      <version>/anomaly/...            detectors (joblib / torch weights) + thresholds
      <version>/forecast/...           XGBoost (JSON), neural weights, conformal half-widths
      <version>/results.json           every metric from the evaluation
      <version>/report.md              human-readable evaluation report

Loading verifies every file's hash first, so a modified or swapped artifact is refused before
any (pickle-based) deserialisation happens.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class ArtifactIntegrityError(RuntimeError):
    pass


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def config_hash(config: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(config, sort_keys=True, default=str).encode()).hexdigest()[:8]


def git_commit(cwd: Path) -> str | None:
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=cwd, capture_output=True, text=True, timeout=5)
        return out.stdout.strip() or None
    except Exception:  # pragma: no cover - git missing
        return None


class ModelRegistry:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    @property
    def index_path(self) -> Path:
        return self.root / "registry.json"

    def _index(self) -> dict[str, Any]:
        if self.index_path.exists():
            return json.loads(self.index_path.read_text())
        return {"latest": None, "versions": []}

    def new_version(self, cfg_hash: str) -> tuple[str, Path]:
        version = f"v{datetime.now(UTC):%Y%m%d-%H%M%S}-{cfg_hash}"
        path = self.root / version
        path.mkdir(parents=True, exist_ok=False)
        return version, path

    def register(self, version: str, manifest: dict[str, Any]) -> dict[str, Any]:
        path = self.root / version
        files = {
            str(p.relative_to(path)).replace("\\", "/"): sha256(p)
            for p in sorted(path.rglob("*"))
            if p.is_file() and p.name != "manifest.json"
        }
        manifest = {**manifest, "version": version, "files": files}
        (path / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str))
        index = self._index()
        index["versions"] = [v for v in index["versions"] if v["version"] != version]
        index["versions"].append(
            {"version": version, "created_at": manifest.get("created_at"), "config_hash": manifest.get("config_hash")}
        )
        index["latest"] = version
        self.root.mkdir(parents=True, exist_ok=True)
        self.index_path.write_text(json.dumps(index, indent=2))
        return manifest

    def latest(self) -> str | None:
        return self._index().get("latest")

    def versions(self) -> list[dict[str, Any]]:
        return self._index()["versions"]

    def manifest(self, version: str) -> dict[str, Any]:
        return json.loads((self.root / version / "manifest.json").read_text())

    def verify(self, version: str) -> Path:
        path = self.root / version
        manifest = self.manifest(version)
        for rel, expected in manifest["files"].items():
            f = path / rel
            if not f.exists():
                raise ArtifactIntegrityError(f"{version}: missing artifact {rel}")
            if sha256(f) != expected:
                raise ArtifactIntegrityError(f"{version}: artifact {rel} does not match its recorded hash")
        return path
