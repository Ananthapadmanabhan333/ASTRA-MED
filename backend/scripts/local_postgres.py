"""Run a local PostgreSQL server without Docker, using the pip-installed `pgserver` binaries.

    pip install -r requirements-pg.txt
    python scripts/local_postgres.py serve      # start PostgreSQL, then the API on it (Ctrl+C stops the API)
    python scripts/local_postgres.py start      # start PostgreSQL only; prints ASTRA_DATABASE_URL
    python scripts/local_postgres.py url        # print the connection URL of the running server
    python scripts/local_postgres.py status
    python scripts/local_postgres.py stop

Data lives in backend/.pgdata (git-ignored). The server listens on 127.0.0.1 only and uses
PostgreSQL's passwordless "trust" mode for local connections: development use only, never
expose it or reuse it for anything shared.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

BACKEND = Path(__file__).resolve().parents[1]
PGDATA = BACKEND / ".pgdata"
DATABASES = ("astra_med", "astra_med_test")


def _pgserver():
    try:
        import pgserver  # type: ignore[import-not-found]
    except ImportError:
        sys.exit("pgserver is not installed. Run: pip install -r requirements-pg.txt")
    return pgserver


def start():
    """Start (or attach to) the server and make sure the app databases exist."""
    srv = _pgserver().get_server(PGDATA, cleanup_mode=None)
    for db in DATABASES:
        if "(1 row)" not in srv.psql(f"select 1 from pg_database where datname = '{db}';"):
            srv.psql(f"create database {db};")
    return srv


def asyncpg_url(srv, database: str = "astra_med") -> str:
    parts = urlsplit(srv.get_uri())
    return f"postgresql+asyncpg://{parts.username or 'postgres'}@{parts.hostname}:{parts.port}/{database}"


def is_running() -> bool:
    pid_file = PGDATA / "postmaster.pid"
    if not pid_file.exists():
        return False
    try:
        import psutil

        return psutil.pid_exists(int(pid_file.read_text().splitlines()[0]))
    except Exception:
        return False


def stop() -> None:
    if not is_running():
        print("PostgreSQL is not running.")
        return
    _pgserver().pg_ctl(["-D", str(PGDATA), "stop", "-m", "fast"])
    print("PostgreSQL stopped.")


def main(argv: list[str]) -> None:
    cmd = argv[0] if argv else "start"
    if cmd == "start":
        srv = start()
        print(f"PostgreSQL running. Data: {PGDATA}")
        print(f"ASTRA_DATABASE_URL={asyncpg_url(srv)}")
        print(f"ASTRA_TEST_POSTGRES_URL={asyncpg_url(srv, 'astra_med_test')}")
    elif cmd == "url":
        if not is_running():
            sys.exit("PostgreSQL is not running. Start it with: python scripts/local_postgres.py start")
        print(asyncpg_url(start()))
    elif cmd == "status":
        print("running" if is_running() else "stopped")
    elif cmd == "stop":
        stop()
    elif cmd == "serve":
        srv = start()
        url = asyncpg_url(srv)
        print(f"API on PostgreSQL: {url}")
        env = {**os.environ, "ASTRA_DATABASE_URL": url}
        args = argv[1:] or ["--host", "127.0.0.1", "--port", "8000"]
        try:
            subprocess.run(
                [sys.executable, "-m", "uvicorn", "app.main:app", "--app-dir", str(BACKEND), *args],
                env=env,
                check=False,
            )
        except KeyboardInterrupt:
            pass
        print("API stopped. PostgreSQL keeps running; stop it with: python scripts/local_postgres.py stop")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
