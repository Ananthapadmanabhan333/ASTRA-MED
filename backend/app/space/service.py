"""Synchronisation of NASA open data into the local store, plus source health.

The API always answers from the local store. Synchronisation runs in the background (or on an
operator request) and records every run. When NASA services are unreachable the stored data keeps
being served, marked as cached with its retrieval time: that is the fallback mode.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, time, timedelta
from typing import Any

import httpx
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.timeutil import utcnow
from app.space import donki, eda, osdr
from app.space import repository as repo
from app.space.http import ResilientClient, SourceUnavailable
from app.space.provenance import DONKI, EDA, OSDR, SOURCES
from app.space.timeparse import day_param

logger = logging.getLogger("astra.space")

DONKI_TYPES = ("FLR", "CME", "SEP", "GST", "RBE", "IPS", "HSS", "MPC", "WSA")
DONKI_CHUNK_DAYS = 60
OSDR_PAGE_SIZE = 50


class SpaceDataService:
    def __init__(self, settings: Settings, session_factory: async_sessionmaker[AsyncSession],
                 transport: httpx.AsyncBaseTransport | None = None, sleep=asyncio.sleep) -> None:
        self.settings = settings
        self.factory = session_factory
        self.client = ResilientClient(timeout_s=settings.space_http_timeout_s,
                                      min_spacing_s=settings.space_request_spacing_s,
                                      transport=transport, sleep=sleep)
        names = [n.strip() for n in settings.donki_endpoints.split(",") if n.strip()]
        by_name = {e.name: e for e in DONKI.endpoints}
        self.donki_endpoints = [by_name[n] for n in names if n in by_name] or list(DONKI.endpoints)
        self._locks = {sid: asyncio.Lock() for sid in SOURCES}
        self._task: asyncio.Task | None = None
        self._next_due: dict[str, datetime] = {}
        self.running_tasks: dict[str, str] = {}

    # ----------------------------------------------------------------- lifecycle ----
    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop(), name="astra-space-sync")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # pragma: no cover - shutdown path
                pass
            self._task = None
        await self.client.aclose()

    async def _loop(self) -> None:
        await asyncio.sleep(3)
        while True:
            for source_id, interval, job in (
                ("donki", timedelta(minutes=self.settings.donki_sync_minutes), self.sync_donki_recent),
                ("osdr", timedelta(hours=self.settings.osdr_sync_hours), self.sync_osdr),
                ("eda", timedelta(hours=self.settings.eda_sync_hours), self.sync_eda),
            ):
                now = utcnow()
                if self._next_due.get(source_id, now) <= now:
                    try:
                        await job()
                    except Exception:  # keep the loop alive whatever happens
                        logger.exception("%s sync failed", source_id)
                    self._next_due[source_id] = utcnow() + interval
            await asyncio.sleep(60)

    # -------------------------------------------------------------------- helpers ----
    async def _record(self, source_id: str, task: str, started: datetime, status: str, **fields: Any) -> None:
        async with self.factory() as session:
            await repo.record_sync(session, source_id=source_id, task=task[:160], started_at=started,
                                   finished_at=utcnow(), status=status, **fields)
            await session.commit()

    # ---------------------------------------------------------------------- DONKI ----
    async def _fetch_donki(self, path: str, start: datetime, end: datetime):
        params = {"startDate": day_param(start), "endDate": day_param(end)}
        if path == "notifications":
            params["type"] = "all"
        return await self.client.get_json("donki", self.donki_endpoints, path, params,
                                          api_key=self.settings.nasa_api_key_value, cache_ttl_s=600)

    async def sync_donki(self, start: datetime, end: datetime, types: tuple[str, ...] = DONKI_TYPES,
                         task: str = "donki", notifications: bool = True) -> dict[str, Any]:
        """Fetch DONKI types for [start, end] in chunks; returns per-type counts."""
        summary: dict[str, Any] = {}
        async with self._locks["donki"]:
            self.running_tasks["donki"] = task
            try:
                chunk_start = start
                while chunk_start <= end:
                    chunk_end = min(end, chunk_start + timedelta(days=DONKI_CHUNK_DAYS - 1))
                    for t in types:
                        summary[t] = await self._sync_donki_type(t, chunk_start, chunk_end, task, summary.get(t))
                    if notifications:
                        summary["notifications"] = await self._sync_notifications(chunk_start, chunk_end, task,
                                                                                  summary.get("notifications"))
                    chunk_start = chunk_end + timedelta(days=1)
            finally:
                self.running_tasks.pop("donki", None)
        return summary

    async def _sync_donki_type(self, t: str, start: datetime, end: datetime, task: str,
                               acc: dict[str, Any] | None) -> dict[str, Any]:
        acc = acc or {"received": 0, "new": 0, "updated": 0, "duplicates": 0, "invalid": 0, "errors": []}
        started = utcnow()
        label = f"{task}:{t} {day_param(start)}..{day_param(end)}"
        try:
            result = await self._fetch_donki(donki.PATHS[t], start, end)
        except SourceUnavailable as exc:
            acc["errors"].append(str(exc))
            await self._record("donki", label, started, "failed", error=str(exc)[:2000],
                               detail={"attempts": exc.attempts[-6:]})
            return acc
        rows, report = donki.normalise_batch(t, result.data)
        try:
            new, updated, dup = await self._store_events(rows, report, result, started, label, t, start, end)
        except SQLAlchemyError as exc:  # storage problem: record it and carry on with the next type
            logger.exception("storing DONKI %s failed", t)
            acc["errors"].append(f"storage: {exc.__class__.__name__}")
            await self._record("donki", label, started, "failed", error=f"storage: {str(exc)[:1500]}",
                               endpoint=result.endpoint, records_received=report.received)
            return acc
        for k, v in (("received", report.received), ("new", new), ("updated", updated),
                     ("duplicates", dup + report.duplicates_in_response), ("invalid", report.invalid)):
            acc[k] += v
        return acc

    async def _store_events(self, rows, report, result, started, label, t, start, end) -> tuple[int, int, int]:
        async with self.factory() as session:
            new, updated, dup = await repo.upsert_events(session, "donki", result.endpoint, result.retrieved_at, rows)
            await repo.record_sync(
                session, source_id="donki", task=label, started_at=started, finished_at=utcnow(),
                status="ok" if report.invalid == 0 else "partial", endpoint=result.endpoint,
                records_received=report.received, records_new=new, records_updated=updated,
                duplicates=dup + report.duplicates_in_response, invalid=report.invalid,
                error="; ".join(report.errors[:5]) or None,
                detail={"url": result.url, "latency_ms": result.latency_ms, "attempts": result.attempts,
                        "from_cache": result.from_cache, "type": t, "start": day_param(start), "end": day_param(end)},
            )
            await session.commit()
        return new, updated, dup

    async def _sync_notifications(self, start: datetime, end: datetime, task: str,
                                  acc: dict[str, Any] | None) -> dict[str, Any]:
        acc = acc or {"received": 0, "new": 0, "duplicates": 0, "invalid": 0, "errors": []}
        started = utcnow()
        label = f"{task}:notifications {day_param(start)}..{day_param(end)}"
        try:
            result = await self._fetch_donki("notifications", start, end)
        except SourceUnavailable as exc:
            acc["errors"].append(str(exc))
            await self._record("donki", label, started, "failed", error=str(exc)[:2000])
            return acc
        rows, report = donki.normalise_notifications(result.data)
        try:
            return await self._store_notifications(rows, report, result, started, label, acc)
        except SQLAlchemyError as exc:
            logger.exception("storing DONKI notifications failed")
            acc["errors"].append(f"storage: {exc.__class__.__name__}")
            await self._record("donki", label, started, "failed", error=f"storage: {str(exc)[:1500]}")
            return acc

    async def _store_notifications(self, rows, report, result, started, label, acc) -> dict[str, Any]:
        async with self.factory() as session:
            new, _, dup = await repo.upsert_notifications(session, "donki", result.endpoint, result.retrieved_at, rows)
            await repo.record_sync(session, source_id="donki", task=label, started_at=started, finished_at=utcnow(),
                                   status="ok" if report.invalid == 0 else "partial", endpoint=result.endpoint,
                                   records_received=report.received, records_new=new, duplicates=dup,
                                   invalid=report.invalid, detail={"url": result.url})
            await session.commit()
        acc["received"] += report.received
        acc["new"] += new
        acc["duplicates"] += dup
        acc["invalid"] += report.invalid
        return acc

    async def sync_donki_recent(self) -> dict[str, Any]:
        """Incremental sync: from a few days before the newest stored event (DONKI revises recent
        records) or, on an empty store, from the configured backfill window."""
        now = utcnow()
        async with self.factory() as session:
            stats = await repo.event_stats(session, "donki")
        backfill_start = now - timedelta(days=self.settings.donki_backfill_days)
        if stats["last"] is None:
            start = backfill_start
        else:
            start = max(backfill_start, min(stats["last"], now) - timedelta(days=3))
        return await self.sync_donki(start, now, task="donki:recent")

    # ------------------------------------------------------------------------ EDA ----
    async def sync_eda(self, missions: list[str] | None = None, force: bool = False) -> dict[str, Any]:
        started = utcnow()
        summary: dict[str, Any] = {"missions": {}}
        async with self._locks["eda"]:
            self.running_tasks["eda"] = "eda:missions"
            try:
                try:
                    result = await self.client.get_json("eda", list(EDA.endpoints), "missions/", cache_ttl_s=3600)
                    listed = eda.normalise_missions(result.data)
                except (SourceUnavailable, ValueError) as exc:
                    await self._record("eda", "eda:missions", started, "failed", error=str(exc)[:2000])
                    summary["error"] = str(exc)
                    return summary
                async with self.factory() as session:
                    new = await repo.upsert_missions(session, listed, result.retrieved_at)
                    await repo.record_sync(session, source_id="eda", task="eda:missions", started_at=started,
                                           finished_at=utcnow(), status="ok", endpoint=result.endpoint,
                                           records_received=len(listed), records_new=new,
                                           records_updated=len(listed) - new, detail={"url": result.url})
                    await session.commit()
                wanted = missions or self.settings.eda_mission_list or [m["name"] for m in listed]
                for name in wanted:
                    self.running_tasks["eda"] = f"eda:{name}"
                    summary["missions"][name] = await self._sync_eda_mission(name, force)
            finally:
                self.running_tasks.pop("eda", None)
        return summary

    async def _sync_eda_mission(self, name: str, force: bool) -> dict[str, Any]:
        async with self.factory() as session:
            mission = await repo.get_mission(session, name)
        if mission is None:
            return {"error": "unknown mission"}
        fresh_after = utcnow() - timedelta(hours=self.settings.eda_sync_hours)
        out: dict[str, Any] = {}
        quality = dict(mission.quality or {})
        milestones: list[dict[str, str]] = list(mission.milestones or [])
        window: list[datetime] = []

        for kind, path, normaliser, quantities, synced_at in (
            ("telemetry", f"missions/{name}/telemetry_data/", eda.normalise_telemetry, eda.TELEMETRY, mission.telemetry_synced_at),
            ("radiation", f"missions/{name}/radiation_data/", eda.normalise_radiation, eda.DOSIMETRY, mission.radiation_synced_at),
        ):
            if not force and synced_at and synced_at > fresh_after:
                out[kind] = "up to date"
                continue
            started = utcnow()
            try:
                result = await self.client.get_json("eda", list(EDA.endpoints), path)
                rows, qualities, ms = normaliser(result.data)
            except (SourceUnavailable, ValueError) as exc:
                await self._record("eda", f"eda:{name}:{kind}", started, "failed", error=str(exc)[:2000])
                out[kind] = f"failed: {exc}"
                continue
            async with self.factory() as session:
                stored = await repo.replace_measurements(session, name, quantities, rows)
                m = await repo.get_mission(session, name)
                for q in qualities:
                    quality[f"{q.quantity}:{q.platform}"] = q.as_dict()
                milestones = sorted({(x["time"], x["label"]): x for x in milestones + ms}.values(), key=lambda x: x["time"])
                m.quality, m.milestones = quality, milestones
                lo, hi = eda.mission_window(rows)
                if lo:
                    window += [lo, hi]
                    m.start_time = min(filter(None, [m.start_time, lo]))
                    m.end_time = max(filter(None, [m.end_time, hi]))
                if kind == "telemetry":
                    m.telemetry_synced_at = result.retrieved_at
                else:
                    m.radiation_synced_at = result.retrieved_at
                received = sum(q.raw_points for q in qualities)
                invalid = sum(q.out_of_range for q in qualities)
                await repo.record_sync(
                    session, source_id="eda", task=f"eda:{name}:{kind}", started_at=started, finished_at=utcnow(),
                    status="ok" if invalid == 0 else "partial", endpoint=result.endpoint, records_received=received,
                    records_new=stored, duplicates=sum(q.duplicates for q in qualities), invalid=invalid,
                    detail={"url": result.url, "latency_ms": result.latency_ms,
                            "missing": sum(q.missing for q in qualities), "series": len(qualities)},
                )
                await session.commit()
            out[kind] = f"{stored} rows from {received} points"

        # Space weather during the mission (real DONKI history), fetched once per mission.
        async with self.factory() as session:
            m = await repo.get_mission(session, name)
            # Historical DONKI does not change: fetch once per mission, even when EDA is re-ingested.
            need = m and m.start_time and m.space_weather_synced_at is None
            lo, hi = (m.start_time, m.end_time) if m else (None, None)
        if need and lo and hi:
            res = await self.sync_donki(lo - timedelta(days=3), hi + timedelta(days=1), donki.HISTORICAL_TYPES,
                                        task=f"donki:mission {name}", notifications=False)
            if not any(v.get("errors") for v in res.values()):
                async with self.factory() as session:
                    m = await repo.get_mission(session, name)
                    m.space_weather_synced_at = utcnow()
                    await session.commit()
            out["space_weather"] = {t: v["new"] for t, v in res.items()}
        return out

    # ----------------------------------------------------------------------- OSDR ----
    async def sync_osdr(self, topics: list[str] | None = None) -> dict[str, Any]:
        summary: dict[str, Any] = {}
        async with self._locks["osdr"]:
            self.running_tasks["osdr"] = "osdr:catalogue"
            try:
                for key, _label, term in osdr.TOPICS:
                    if topics and key not in topics:
                        continue
                    summary[key] = await self._sync_osdr_term(term, key)
            finally:
                self.running_tasks.pop("osdr", None)
        return summary

    async def _sync_osdr_term(self, term: str, topic: str | None) -> dict[str, Any]:
        started = utcnow()
        params = {"term": term, "type": "cgene", "from": 0, "size": OSDR_PAGE_SIZE}
        try:
            result = await self.client.get_json("osdr", list(OSDR.endpoints), "", params, cache_ttl_s=3600)
            studies, total, invalid = osdr.normalise_search(result.data, topic)
        except (SourceUnavailable, ValueError) as exc:
            await self._record("osdr", f"osdr:{topic or term}"[:160], started, "failed", error=str(exc)[:2000])
            return {"error": str(exc)}
        async with self.factory() as session:
            new, updated = await repo.upsert_studies(session, result.endpoint, result.retrieved_at, studies)
            await repo.record_sync(session, source_id="osdr", task=f"osdr:{topic or term}"[:160], started_at=started,
                                   finished_at=utcnow(), status="ok" if not invalid else "partial",
                                   endpoint=result.endpoint, records_received=len(studies) + invalid,
                                   records_new=new, records_updated=updated, invalid=invalid,
                                   detail={"url": result.url, "total_hits": total, "term": term})
            await session.commit()
        return {"total_hits": total, "stored": len(studies), "new": new}

    async def search_osdr_live(self, q: str) -> dict[str, Any]:
        """Ad hoc catalogue search; results are stored so they stay available offline."""
        async with self._locks["osdr"]:
            return await self._sync_osdr_term(q, None)

    # --------------------------------------------------------------------- status ----
    def mode(self, source_id: str, last_retrieved: datetime | None) -> tuple[str, str]:
        """(mode, message) describing how fresh the served data is."""
        h = self.client.source_health(source_id)
        if not self.settings.space_sync_enabled:
            return "cached", "Background synchronisation is disabled; serving stored data."
        if last_retrieved is None:
            if h.status == "offline":
                return "unavailable", "The NASA source is unreachable and nothing is stored yet."
            return "pending", "Waiting for the first synchronisation."
        if h.status == "offline":
            return "offline-fallback", f"NASA source unreachable ({h.last_error}); serving data stored at {last_retrieved:%Y-%m-%d %H:%M} UTC."
        return "live", "Synchronised with the NASA source."

    async def sources_status(self) -> list[dict[str, Any]]:
        out = []
        async with self.factory() as session:
            stats = {
                "donki": await repo.event_stats(session, "donki"),
                "eda": await repo.measurement_stats(session),
                "osdr": await repo.study_stats(session),
            }
            for sid, info in SOURCES.items():
                runs = await repo.recent_syncs(session, sid, 8)
                totals = await repo.quality_totals(session, sid)
                s = stats[sid]
                mode, message = self.mode(sid, s.get("last_retrieved"))
                out.append({"info": info, "stats": s, "runs": runs, "totals": totals, "mode": mode,
                            "message": message, "health": self.client.source_health(sid).as_dict(),
                            "running": self.running_tasks.get(sid)})
        return out

    async def freshness(self, source_id: str) -> dict[str, Any]:
        async with self.factory() as session:
            if source_id == "donki":
                last = (await repo.event_stats(session, "donki"))["last_retrieved"]
            elif source_id == "eda":
                last = (await repo.measurement_stats(session))["last_retrieved"]
            else:
                last = (await repo.study_stats(session))["last_retrieved"]
        mode, message = self.mode(source_id, last)
        return {"source_id": source_id, "retrieved_at": last, "mode": mode, "message": message}


def day_start(d: datetime) -> datetime:
    return datetime.combine(d.date(), time(0), tzinfo=UTC)
