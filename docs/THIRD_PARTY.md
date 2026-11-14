# Third-party software

Direct dependencies of ASTRA-MED with the licence each declares in its package metadata
(read from the installed packages on 2026-11-14). Transitive dependencies are pinned in
`backend/constraints.txt` and `frontend/package-lock.json`. All are open-source licences; check
the package itself before redistributing.

| Ecosystem | Package | Version | Licence |
| --- | --- | --- | --- |
| Python | fastapi | 0.162.2 | MIT |
| Python | uvicorn | 0.54.0 | BSD-3-Clause |
| Python | pydantic | 2.14.3 | MIT |
| Python | pydantic-settings | 2.16.2 | MIT |
| Python | SQLAlchemy | 2.0.57 | MIT |
| Python | asyncpg | 0.32.0 | Apache-2.0 |
| Python | aiosqlite | 0.22.1 | MIT License |
| Python | numpy | 2.4.6 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 |
| Python | pandas | 3.1.1 | BSD-3-Clause |
| Python | scikit-learn | 1.9.1 | BSD-3-Clause |
| Python | joblib | 1.6.0 | BSD-3-Clause |
| Python | xgboost-cpu | 3.2.0 | Apache-2.0 |
| Python | httpx | 0.28.1 | BSD-3-Clause |
| Python | scipy | 1.17.1 | BSD License |
| Python | alembic | 1.20.1 | MIT |
| Python | psutil | 7.2.2 | BSD-3-Clause |
| Python | torch | 2.15.0+cpu | BSD-3-Clause plus bundled components under Apache-2.0 and others (see the package) |
| npm | @tanstack/react-query | 5.107.1 | MIT |
| npm | class-variance-authority | 0.7.1 | Apache-2.0 |
| npm | cn | 0.5.2 | MIT |
| npm | lucide-react | 1.70.0 | ISC |
| npm | next | 16.4.5 | MIT |
| npm | next-themes | 0.4.6 | MIT |
| npm | openapi-fetch | 0.14.1 | MIT |
| npm | radix-ui | 1.8.1 | MIT |
| npm | react | 19.3.0 | MIT |
| npm | react-dom | 19.3.0 | MIT |
| npm | recharts | 3.10.1 | MIT |
| npm | sonner | 2.0.8 | MIT |
| npm | tw-animate-css | 1.4.0 | MIT |
| npm | zustand | 5.1.0 | MIT |
| npm (dev) | @tailwindcss/turbopack | 4.3.5 | MIT |
| npm (dev) | @types/node | 20.19.43 | MIT |
| npm (dev) | @types/react | 19.3.0 | MIT |
| npm (dev) | @types/react-dom | 19.3.0 | MIT |
| npm (dev) | eslint | 9.39.5 | MIT |
| npm (dev) | eslint-config-next | 16.4.5 | MIT |
| npm (dev) | openapi-typescript | 7.13.0 | MIT |
| npm (dev) | shadcn | 4.23.0 | MIT |
| npm (dev) | tailwindcss | 4.3.5 | MIT |
| npm (dev) | typescript | 5.9.3 | Apache-2.0 |
| npm (dev) | vitest | 3.2.7 | MIT |

## Data and fonts

- NASA data: see [DATASETS.md](DATASETS.md) for each source's terms and citation.
- Fonts: Barlow Semi Condensed and IBM Plex Sans, served through `next/font/google` (SIL Open Font License 1.1).
- Icons: Lucide (ISC licence).
