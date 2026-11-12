"""Create ASTRA-MED user accounts in the configured database (ASTRA_DATABASE_URL).

    python scripts/create_users.py add <username> --role flight_surgeon [--name "Dr. A. Reyes"]
        Prompts for the password (not echoed). Roles: flight_surgeon, mission_operator, analyst, admin.
    python scripts/create_users.py list
    python scripts/create_users.py dev
        Development only: creates one demo account per role with a random password and writes the
        credentials to backend/.dev-users.json (git-ignored). Refused when ASTRA_ENVIRONMENT=production.

Passwords are stored only as scrypt hashes. Nothing is printed except usernames and roles.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import os
import secrets
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.core.config import get_settings  # noqa: E402
from app.core.errors import ConflictError  # noqa: E402
from app.db.session import create_engine, create_schema, create_session_factory  # noqa: E402
from app.security.rbac import Role  # noqa: E402
from app.security.service import AuthService  # noqa: E402

DEV_FILE = BACKEND / ".dev-users.json"
DEV_ACCOUNTS = (
    ("surgeon", "Dev Flight Surgeon", Role.FLIGHT_SURGEON),
    ("operator", "Dev Mission Operator", Role.MISSION_OPERATOR),
    ("analyst", "Dev Analyst", Role.ANALYST),
    ("admin", "Dev Administrator", Role.ADMIN),
)


async def _service() -> tuple[AuthService, object]:
    settings = get_settings()
    engine = create_engine(settings.database_url)
    await create_schema(engine)
    return AuthService(settings, create_session_factory(engine)), engine


async def add(username: str, role: str, name: str | None) -> None:
    password = getpass.getpass("Password: ")
    if password != getpass.getpass("Repeat password: "):
        sys.exit("Passwords do not match.")
    auth, engine = await _service()
    try:
        user = await auth.create_user(username, name or username, role, password)
    except ConflictError as exc:
        problems = (exc.details or {}).get("problems") or []
        sys.exit(" ".join([exc.message, *problems]))
    finally:
        await engine.dispose()
    print(f"created {user.username} ({user.role})")


async def list_users() -> None:
    auth, engine = await _service()
    try:
        for u in await auth.list_users():
            print(f"{u.username:24} {u.role:18} {'active' if u.active else 'inactive'}")
    finally:
        await engine.dispose()


async def dev() -> None:
    settings = get_settings()
    if settings.is_production:
        sys.exit("Refusing to create demo accounts when ASTRA_ENVIRONMENT=production.")
    existing = json.loads(DEV_FILE.read_text(encoding="utf-8")) if DEV_FILE.exists() else {}
    auth, engine = await _service()
    try:
        known = {u.username for u in await auth.list_users()}
        for username, name, role in DEV_ACCOUNTS:
            if username in known:
                continue
            password = "dev-" + secrets.token_urlsafe(15)
            await auth.create_user(username, name, role.value, password)
            existing[username] = {"password": password, "role": role.value}
            print(f"created {username} ({role.value})")
    finally:
        await engine.dispose()
    DEV_FILE.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")
    try:
        os.chmod(DEV_FILE, 0o600)
    except OSError:  # pragma: no cover - Windows ignores POSIX modes
        pass
    print(f"credentials for the demo accounts are in {DEV_FILE} (git-ignored; delete it when done)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p_add = sub.add_parser("add")
    p_add.add_argument("username")
    p_add.add_argument("--role", required=True, choices=[r.value for r in Role])
    p_add.add_argument("--name")
    sub.add_parser("list")
    sub.add_parser("dev")
    args = parser.parse_args()
    if args.command == "add":
        asyncio.run(add(args.username, args.role, args.name))
    elif args.command == "list":
        asyncio.run(list_users())
    else:
        asyncio.run(dev())


if __name__ == "__main__":
    main()
