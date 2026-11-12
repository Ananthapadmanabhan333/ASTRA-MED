"""Train and evaluate every AI model, then register a new model version.

    python -m app.ai.train                         # full experiment (default config, ~3-5 min on CPU)
    python -m app.ai.train --config experiments/configs/default.json
    python -m app.ai.train --quick                 # small smoke run; not for reported results
    python -m app.ai.train --if-missing            # only train when no model version exists yet
"""

from __future__ import annotations

import argparse
import logging
import shutil
import sys
from pathlib import Path

from app.ai.experiments.config import ExperimentConfig
from app.ai.experiments.runner import run
from app.ai.registry import ModelRegistry
from app.core.config import get_settings
from app.core.logging import configure_logging

BACKEND = Path(__file__).resolve().parents[2]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", type=Path, help="JSON experiment config")
    parser.add_argument("--quick", action="store_true", help="small, fast run (smoke test)")
    parser.add_argument("--artifacts", type=Path, default=None, help="artifact root (default: settings)")
    parser.add_argument("--if-missing", action="store_true", help="skip if a model version already exists")
    parser.add_argument("--no-publish", action="store_true", help="do not copy the report into experiments/results")
    args = parser.parse_args(argv)

    settings = get_settings()
    configure_logging(settings.log_level)
    root = args.artifacts or settings.ai_artifacts_path
    if args.if_missing and ModelRegistry(root).latest():
        logging.getLogger("astra.ai").info("model version %s already present; skipping", ModelRegistry(root).latest())
        return 0

    cfg = ExperimentConfig.from_file(args.config) if args.config else ExperimentConfig()
    if args.quick:
        cfg = cfg.quick()
    results = run(cfg, root)

    if not args.no_publish and not args.quick:
        out = BACKEND / "experiments" / "results"
        out.mkdir(parents=True, exist_ok=True)
        version_dir = Path(root) / results["version"]
        shutil.copy(version_dir / "results.json", out / "latest-results.json")
        shutil.copy(version_dir / "report.md", out / "latest-report.md")
    print(f"registered {results['version']} ({results['runtime_seconds']} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
