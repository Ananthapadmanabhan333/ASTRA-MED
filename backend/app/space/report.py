"""Data source documentation report, generated from the local store.

    python -m app.space.report --out ../docs/reports/nasa-data-sources-report.md

Uses ASTRA_DATABASE_URL like the API. Everything in the report is computed from stored records
and sync runs; nothing is estimated.
"""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select

from app.core.config import get_settings
from app.db.models import (
    DataSyncRunRow,
    EnvMeasurementRow,
    EnvMissionRow,
    OsdrStudyRow,
    SpaceNotificationRow,
    SpaceWeatherEventRow,
)
from app.db.session import create_engine, create_schema, create_session_factory
from app.space import classify, donki, eda, osdr
from app.space.provenance import CATEGORY_LABELS, EVALUATED_SOURCES, SOURCES


def _d(dt: datetime | None, fmt: str = "%Y-%m-%d") -> str:
    return dt.astimezone(UTC).strftime(fmt) if dt else "—"


async def build(database_url: str) -> str:
    engine = create_engine(database_url)
    await create_schema(engine)
    factory = create_session_factory(engine)
    out: list[str] = []
    w = out.append
    async with factory() as s:
        now = datetime.now(UTC)
        w("# NASA data sources: documentation report\n")
        w(f"Generated {now:%Y-%m-%d %H:%M} UTC from the ASTRA-MED store (`{engine.dialect.name}`). "
          "All figures are computed from stored records and synchronisation logs.\n")
        w("> ASTRA-MED is an independent research prototype. It is not affiliated with or endorsed by NASA. "
          "Crew data in ASTRA-MED are simulated; only the sources below are real.\n")
        w("## Data categories\n")
        w("| Category | Meaning |\n| --- | --- |")
        for k, v in CATEGORY_LABELS.items():
            w(f"| `{k}` | {v} |")
        w("")

        # ------------------------------------------------------------------ per source
        for sid, info in SOURCES.items():
            runs = (await s.execute(select(DataSyncRunRow.status, func.count()).where(DataSyncRunRow.source_id == sid)
                                    .group_by(DataSyncRunRow.status))).all()
            status = dict(runs)
            totals = (await s.execute(select(func.coalesce(func.sum(DataSyncRunRow.records_received), 0),
                                             func.coalesce(func.sum(DataSyncRunRow.invalid), 0),
                                             func.coalesce(func.sum(DataSyncRunRow.duplicates), 0))
                                      .where(DataSyncRunRow.source_id == sid))).one()
            endpoints = dict((await s.execute(select(DataSyncRunRow.endpoint, func.count())
                                              .where(DataSyncRunRow.source_id == sid, DataSyncRunRow.status != "failed")
                                              .group_by(DataSyncRunRow.endpoint))).all())
            last = (await s.scalars(select(DataSyncRunRow).where(DataSyncRunRow.source_id == sid)
                                    .order_by(DataSyncRunRow.started_at.desc()).limit(1))).first()
            w(f"## {info.name}\n")
            w(f"- **Provider:** {info.provider}")
            w(f"- **Homepage:** {info.homepage}")
            w("- **Endpoints (tried in order):** " + "; ".join(
                f"`{e.base_url}`{' (API key, server side)' if e.needs_key else ''}" for e in info.endpoints))
            w(f"- **Format:** {info.data_format}")
            w(f"- **Categories:** {', '.join(info.categories)}")
            w(f"- **Update frequency:** {info.update_frequency}")
            if info.units:
                w("- **Units:** " + "; ".join(f"{k}: {v}" for k, v in info.units.items()))
            w(f"- **Licence / use:** {info.license} ({info.license_url})")
            w(f"- **Citation:** {info.citation}")
            w(f"- **Synchronisation:** {sum(status.values())} runs ({', '.join(f'{k} {v}' for k, v in sorted(status.items())) or 'none'}); "
              f"last run {_d(last.started_at, '%Y-%m-%d %H:%M') if last else '—'} UTC ({last.status if last else '—'}).")
            w(f"- **Records received / invalid / duplicates skipped:** {int(totals[0]):,} / {int(totals[1]):,} / {int(totals[2]):,}")
            if endpoints:
                w("- **Successful runs by endpoint:** " + ", ".join(f"{k or 'n/a'} {v}" for k, v in endpoints.items()))
            w("- **Scientific limitations:**")
            for c in info.caveats:
                w(f"  - {c}")
            w("")

            if sid == "donki":
                n, first, last_ev = (await s.execute(select(func.count(), func.min(SpaceWeatherEventRow.start_time),
                                                            func.max(SpaceWeatherEventRow.start_time)))).one()
                notes = await s.scalar(select(func.count()).select_from(SpaceNotificationRow))
                w(f"Stored: **{n:,} events** ({_d(first)} to {_d(last_ev)}) and **{notes:,} notifications**.\n")
                w("| Type | Events | First | Last | Classified (scale or class) | Unit of magnitude |")
                w("| --- | --- | --- | --- | --- | --- |")
                for t in donki.EVENT_TYPES:
                    row = (await s.execute(select(func.count(), func.min(SpaceWeatherEventRow.start_time),
                                                  func.max(SpaceWeatherEventRow.start_time),
                                                  func.count(SpaceWeatherEventRow.severity))
                                           .where(SpaceWeatherEventRow.event_type == t))).one()
                    units = sorted(u for u in (await s.scalars(select(func.distinct(SpaceWeatherEventRow.magnitude_unit))
                                                               .where(SpaceWeatherEventRow.event_type == t))).all() if u)
                    if row[0]:
                        w(f"| {t} ({donki.EVENT_TYPES[t]}) | {row[0]:,} | {_d(row[1])} | {_d(row[2])} | {row[3]:,} | {', '.join(units) or '—'} |")
                w("")
                levels = Counter()
                for t, sev in (await s.execute(select(SpaceWeatherEventRow.event_type, SpaceWeatherEventRow.severity)
                                               .where(SpaceWeatherEventRow.event_type.in_(("FLR", "GST", "CME"))))).all():
                    levels[(t, sev)] += 1
                w("Severity distribution (NOAA R for flares, NOAA G for storms, DONKI speed class for CMEs):\n")
                w("| Type | Level | Events |\n| --- | --- | --- |")
                for (t, sev), c in sorted(levels.items(), key=lambda kv: (kv[0][0], -1 if kv[0][1] is None else kv[0][1])):
                    w(f"| {t} | {classify.describe(t, sev)} | {c:,} |")
                w("")
                endpoint_mix = dict((await s.execute(select(SpaceWeatherEventRow.endpoint, func.count())
                                                     .group_by(SpaceWeatherEventRow.endpoint))).all())
                w("Records by serving endpoint: " + ", ".join(f"{k} {v:,}" for k, v in endpoint_mix.items()) + ".\n")

            if sid == "eda":
                missions = (await s.scalars(select(EnvMissionRow).order_by(EnvMissionRow.start_time.is_(None),
                                                                            EnvMissionRow.start_time))).all()
                n = await s.scalar(select(func.count()).select_from(EnvMeasurementRow))
                units = (await s.execute(select(EnvMeasurementRow.quantity, func.count(func.distinct(EnvMeasurementRow.unit)),
                                                func.min(EnvMeasurementRow.unit))
                                         .group_by(EnvMeasurementRow.quantity))).all()
                w(f"Stored: **{n:,} aggregated measurements** from {sum(1 for m in missions if m.start_time)} of "
                  f"{len(missions)} listed missions.\n")
                w("Unit check (one unit per quantity expected): " + "; ".join(
                    f"{q} → {u}{' (MIXED)' if k != 1 else ''}" for q, k, u in units) + ".\n")
                w("Completeness is per distinct timestamp after merging rows that EDA splits across two records. "
                  "Out-of-range values (for example relative humidity above 100 %) are excluded and counted.\n")
                w("| Mission | Period | ISS temperature | ISS humidity | ISS CO₂ | Out of range | Split rows merged | Conflicts | Gaps > 3× sampling | Dose days (approx.) | GCR+SAA = total |")
                w("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
                for m in missions:
                    if not m.start_time:
                        q0 = m.quality or {}
                        if q0 and not any(v.get("valid") for v in q0.values()):
                            points = sum(v.get("raw_points", 0) for v in q0.values())
                            w(f"| {m.name} | no usable values: all {points:,} published readings are null | — | — | — | — | — | — | — | — | — |")
                        elif m.telemetry_synced_at or m.radiation_synced_at:
                            w(f"| {m.name} | no telemetry or dosimetry published | — | — | — | — | — | — | — | — | — |")
                        else:
                            w(f"| {m.name} | not ingested yet | — | — | — | — | — | — | — | — | — |")
                        continue
                    q = m.quality or {}

                    def pct(key: str, q=q) -> str:
                        v = q.get(key)
                        if not v or not v.get("raw_points"):
                            return "not recorded"
                        if not v.get("valid"):
                            return "all null"
                        return f"{v['completeness'] * 100:.1f}%"

                    tel = [v for k, v in q.items() if k.split(":")[0] in eda.TELEMETRY]
                    oor = sum(v["out_of_range"] for v in q.values())
                    dup = max((v["duplicates"] for v in tel), default=0)  # rows are shared by all fields
                    conf = sum(v.get("conflicts", 0) for v in tel)
                    gaps = sum(v["gaps"] for v in tel if v.get("platform") == "iss")
                    tot = q.get("dose_total_mgy_day:iss")
                    dose = f"{tot['valid']} ({tot['approximate_points']})" if tot else "—"
                    cons = ("ok" if tot["consistency_failures"] == 0 else f"{tot['consistency_failures']} mismatches") if tot else "—"
                    w(f"| {m.name} | {_d(m.start_time)} to {_d(m.end_time)} | {pct('temperature_c:iss')} | {pct('humidity_pct:iss')} | "
                      f"{pct('co2_ppm:iss')} | {oor:,} | {dup:,} | {conf:,} | {gaps:,} | {dose} | {cons} |")
                w("")

            if sid == "osdr":
                rows = (await s.scalars(select(OsdrStudyRow))).all()
                topics = Counter(t for r in rows for t in (r.topics or []) if not t.startswith("mission:"))
                linked = Counter(t.split(":", 1)[1] for r in rows for t in (r.topics or []) if t.startswith("mission:"))
                kinds = Counter((r.project_type or "unspecified").title() for r in rows)
                w(f"Stored: **{len(rows):,} studies** (metadata only).\n")
                w("| Topic preset | OSDR search term | Studies stored |\n| --- | --- | --- |")
                for key, label, term in osdr.TOPICS:
                    w(f"| {label} | `{term}` | {topics.get(key, 0)} |")
                w("")
                w("Project types: " + ", ".join(f"{k} {v}" for k, v in kinds.most_common()) + ".")
                if linked:
                    w("Studies linked to EDA missions: " + ", ".join(f"{k} {v}" for k, v in sorted(linked.items())) + ".")
                w("")

        # --------------------------------------------------------------- timestamps
        w("## Timestamp checks\n")
        w("All timestamps are stored and served as UTC (timezone-aware columns; DONKI and EDA document UTC). "
          "The dashboard converts to the selected display zone only when rendering.\n")
        w("| Table | Earliest | Latest | Rows |\n| --- | --- | --- | --- |")
        for label, col, table in (("space_weather_events.start_time", SpaceWeatherEventRow.start_time, SpaceWeatherEventRow),
                                  ("space_notifications.issue_time", SpaceNotificationRow.issue_time, SpaceNotificationRow),
                                  ("env_measurements.ts", EnvMeasurementRow.ts, EnvMeasurementRow),
                                  ("osdr_studies.release_date", OsdrStudyRow.release_date, OsdrStudyRow)):
            lo, hi, n = (await s.execute(select(func.min(col), func.max(col), func.count()).select_from(table))).one()
            w(f"| `{label}` | {_d(lo, '%Y-%m-%d %H:%M')} | {_d(hi, '%Y-%m-%d %H:%M')} | {n:,} |")
        future = await s.scalar(select(func.count()).where(SpaceWeatherEventRow.start_time > now))
        w(f"\nEvents dated in the future (should be none except model predictions): {future}.\n")

        w("## Evaluated but not integrated\n")
        for e in EVALUATED_SOURCES:
            w(f"- **{e['name']}** ({e['url']}): {e['status']}")
        w("")
    await engine.dispose()
    return "\n".join(out) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=Path("../docs/reports/nasa-data-sources-report.md"))
    parser.add_argument("--database-url", default=None)
    args = parser.parse_args()
    text = asyncio.run(build(args.database_url or get_settings().database_url))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
