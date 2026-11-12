"""Normalisation, classification, timestamp and data-quality tests on real NASA excerpts."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.space import classify, donki, eda, osdr
from app.space.timeparse import TimestampError, parse_epoch, parse_utc, parse_utc_optional

from .conftest import fixture


# ------------------------------------------------------------------------ timestamps ----
@pytest.mark.parametrize("text, expected", [
    ("2026-11-11T21:06Z", datetime(2026, 11, 11, 21, 6, tzinfo=UTC)),          # DONKI minute precision
    ("2014-09-20T03:59:00Z", datetime(2014, 9, 20, 3, 59, tzinfo=UTC)),         # EDA
    ("2014-09-20T03:59:00", datetime(2014, 9, 20, 3, 59, tzinfo=UTC)),          # naive = UTC
    ("2026-11-11T23:06:00+02:00", datetime(2026, 11, 11, 21, 6, tzinfo=UTC)),   # offset normalised to UTC
])
def test_timestamps_are_parsed_to_utc(text, expected):
    got = parse_utc(text)
    assert got == expected and got.tzinfo is UTC


@pytest.mark.parametrize("bad", ["", "yesterday", None, 42])
def test_bad_timestamps_are_rejected(bad):
    with pytest.raises(TimestampError):
        parse_utc(bad)


def test_optional_and_epoch_timestamps():
    assert parse_utc_optional(None) is None and parse_utc_optional("") is None
    assert parse_epoch("1553817600.0") == datetime(2019, 3, 29, tzinfo=UTC)
    assert parse_epoch("not a number") is None and parse_epoch(-5) is None


# --------------------------------------------------------------------- classification ----
@pytest.mark.parametrize("cls, flux, level", [
    ("C2.8", 2.8e-6, 0), ("M1.0", 1e-5, 1), ("M1.7", 1.7e-5, 1), ("M5.2", 5.2e-5, 2),
    ("X1.0", 1e-4, 3), ("X10", 1e-3, 4), ("X28", 2.8e-3, 5),
])
def test_flare_class_to_noaa_radio_blackout_scale(cls, flux, level):
    assert classify.flare_flux(cls) == pytest.approx(flux)
    assert classify.radio_blackout_level(classify.flare_flux(cls)) == level


@pytest.mark.parametrize("kp, level", [(4.33, 0), (4.67, 1), (5.0, 1), (6.0, 2), (6.67, 3), (7.67, 4), (8.67, 4), (9.0, 5)])
def test_max_kp_to_noaa_storm_scale_counts_thirds(kp, level):
    # 8- (7.67) is G4 and 9- (8.67) stays G4: NOAA defines G4 as "Kp = 8, including 9-".
    assert classify.storm_level(kp) == level


def test_cme_speed_classes_and_unparseable_flares():
    assert classify.cme_level("C", 850) == ("C", 2)
    assert classify.cme_level(None, 2500) == ("R", 4)
    assert classify.flare_flux("Z9") is None and classify.radio_blackout_level(None) is None


# ---------------------------------------------------------------------------- DONKI ----
def test_flare_records_normalise_with_scale_and_provenance():
    rows, report = donki.normalise_batch("FLR", fixture("donki_FLR.json"))
    assert report.invalid == 0 and report.valid == len(rows) == 4
    m = next(r for r in rows if r["raw"]["classType"].startswith("M"))
    assert m["category"] == "indicator" and m["scale"] == "R1" and m["magnitude_unit"] == "W/m²"
    assert m["peak_time"].tzinfo is UTC and m["start_time"] <= m["peak_time"] <= m["end_time"]
    assert m["raw"]["flrID"] == m["external_id"]  # original record preserved unchanged
    c = next(r for r in rows if r["raw"]["classType"].startswith("C"))
    assert c["severity"] == 0 and c["scale"] is None


def test_may_2024_storm_is_g5_and_sep_model_detections_are_flagged():
    storms, _ = donki.normalise_batch("GST", fixture("donki_GST.json"))
    assert {s["scale"] for s in storms} >= {"G5"}
    g5 = next(s for s in storms if s["scale"] == "G5")
    assert g5["magnitude"] == 9.0 and g5["peak_time"] is not None
    seps, _ = donki.normalise_batch("SEP", fixture("donki_SEP.json"))
    assert all(s["severity"] is None and s["scale"] is None for s in seps)  # no flux in DONKI -> unclassified
    assert any(s["model_derived"] for s in seps)


def test_cme_wsa_and_other_types_normalise():
    for t, name in (("CME", "donki_CME.json"), ("WSA", "donki_WSA.json"), ("RBE", "donki_RBE.json"),
                    ("IPS", "donki_IPS.json"), ("HSS", "donki_HSS.json")):
        rows, report = donki.normalise_batch(t, fixture(name))
        assert report.invalid == 0 and rows, t
        assert all(r["start_time"].tzinfo is UTC for r in rows)
    wsa, _ = donki.normalise_batch("WSA", fixture("donki_WSA.json"))
    assert all(w["category"] == "model" for w in wsa)  # model output, not an observation


def test_invalid_and_duplicate_records_are_counted_not_guessed():
    good = fixture("donki_FLR.json")[0]
    older = dict(good, versionId=1)
    newer = dict(good, versionId=3)
    broken = {"flrID": "x", "beginTime": "not a time"}
    rows, report = donki.normalise_batch("FLR", [older, newer, broken, {"no": "id"}, "junk"])
    assert report.received == 5 and report.invalid == 3 and report.duplicates_in_response == 1
    assert len(rows) == 1 and rows[0]["version"] == 3
    rows, report = donki.normalise_batch("FLR", {"not": "a list"})
    assert rows == [] and report.invalid == 1


def test_notifications_keep_id_time_and_summary():
    rows, report = donki.normalise_notifications(fixture("donki_notifications.json"))
    assert report.invalid == 0 and len(rows) == 2
    assert all(r["issue_time"].tzinfo is UTC and r["message_id"] for r in rows)


# ------------------------------------------------------------------------------ EDA ----
def test_eda_telemetry_quality_checks_catch_injected_problems():
    rows, qualities, milestones = eda.normalise_telemetry(fixture("eda_telemetry_RR-1.json"))
    q = {(x.quantity, x.platform): x for x in qualities}
    temp, rh = q[("temperature_c", "iss")], q[("humidity_pct", "iss")]
    assert temp.out_of_range == 1 and temp.duplicates == 1 and temp.raw_rows == 301 and temp.raw_points == 300
    assert rh.missing == 1 and temp.conflicts == 0
    assert temp.median_interval_min == pytest.approx(5.0)
    assert all(r["unit"] == "°C" for r in rows if r["quantity"] == "temperature_c")
    assert all(r["category"] == "measured" and r["resolution"] == "1h" for r in rows)
    assert max(r["value"] for r in rows if r["quantity"] == "temperature_c") < 45  # the 999 never reaches storage
    assert isinstance(milestones, list)  # this excerpt ends before launch, so it holds none


def test_eda_dosimetry_units_consistency_and_approximate_launch_days():
    rows, qualities, milestones = eda.normalise_radiation(fixture("eda_radiation_RR-1.json"))
    total = [r for r in rows if r["quantity"] == "dose_total_mgy_day"]
    assert all(r["unit"] == "mGy/day" and r["resolution"] == "1d" for r in rows)
    assert next(q for q in qualities if q.quantity == "dose_total_mgy_day").consistency_failures == 0
    # Days up to and including the ISS transfer include launch-vehicle time (approximated by EDA).
    approx = [r["ts"].date().isoformat() for r in total if r["approximate"]]
    assert approx == ["2014-09-21", "2014-09-22", "2014-09-23", "2014-09-24", "2014-09-25"]
    assert 0.1 < min(r["value"] for r in total) and max(r["value"] for r in total) < 1.0
    assert [m["label"] for m in milestones][:2] == ["Launch", "Transfer to ISS"]


def test_eda_rejects_malformed_payloads():
    with pytest.raises(ValueError):
        eda.normalise_telemetry({"data": []})
    with pytest.raises(ValueError):
        eda.normalise_missions("nope")


# ----------------------------------------------------------------------------- OSDR ----
def test_osdr_hits_normalise_with_links_dates_and_mission_codes():
    studies, total, invalid = osdr.normalise_search(fixture("osdr_search.json"), "rodent")
    assert total == 147 and invalid == 0 and len(studies) == 3
    s = studies[0]
    assert s["link"] == f"https://osdr.nasa.gov/bio/repo/data/studies/{s['accession']}"
    assert s["mission_start"] == datetime(2014, 9, 21, tzinfo=UTC)  # "09/21/2014"
    assert "rodent" in s["topics"] and "mission:RR-1" in s["topics"]
    assert osdr.parse_us_date("9/21/14") == datetime(2014, 9, 21, tzinfo=UTC)
    assert osdr.mission_codes("RR-9 and rr-1_BSP") == ["RR-9", "RR-1"]
    assert osdr.mission_codes("RR-10", "VEG-01A", "APEX-03-1") == ["RR-10", "VEG-01A", "APEX-03-1"]


def test_overlapping_eda_milestones_merge_to_the_precise_time():
    from app.api.space_routes import merge_milestones

    merged = merge_milestones([
        {"time": "2014-09-21T00:00:00+00:00", "label": "Launch"},
        {"time": "2014-09-21T09:49:00+00:00", "label": "Launch"},
        {"time": "2014-10-12T00:00:00+00:00", "label": "Sac 1"},
        {"time": "2014-10-11T23:30:00+00:00", "label": "Sac1"},
        {"time": "2014-09-25T00:00:00+00:00", "label": "Transfer to ISS"},
    ])
    assert [(m["label"], m["time"][11:16]) for m in merged] == [
        ("Launch", "09:49"), ("Transfer to ISS", "00:00"), ("Sac1", "23:30")]


def test_split_rows_at_one_timestamp_are_merged_not_counted_missing():
    # Seen in EDA RR-7, RR-10, RR-18: a timestamp's fields are spread over two rows.
    rows = [
        {"time": "2020-12-04T07:30:00Z", "temperature_iss": 23.7, "humidity_iss": 34.0},
        {"time": "2020-12-04T07:30:00Z", "temperature_iss": 23.7, "humidity_iss": None},
        {"time": "2020-12-04T07:31:00Z", "temperature_iss": 23.9, "humidity_iss": None},
        {"time": "2020-12-04T07:31:00Z", "temperature_iss": 24.1, "humidity_iss": 35.0},
        {"time": "2020-12-04T07:32:00Z", "temperature_iss": None, "humidity_iss": 125.8},  # impossible RH
    ]
    _, qualities, _ = eda.normalise_telemetry(rows)
    q = {x.quantity: x for x in qualities if x.platform == "iss"}
    t, h = q["temperature_c"], q["humidity_pct"]
    assert (t.raw_rows, t.raw_points, t.valid, t.duplicates, t.conflicts, t.missing) == (5, 3, 2, 2, 1, 1)
    assert (h.valid, h.missing, h.out_of_range) == (2, 0, 1)
    assert h.completeness == pytest.approx(2 / 3)


def test_placeholder_milestones_and_all_null_missions():
    # APEX-04 on EDA: every telemetry field null, milestones "NA".
    rows = [{"time": "2017-02-26T00:00:00Z", "temperature_iss": None, "humidity_iss": None, "co2_iss": None,
             "milestones": "NA"} for _ in range(3)]
    stored, qualities, milestones = eda.normalise_telemetry(rows)
    assert stored == [] and milestones == []
    assert qualities and all(q.valid == 0 and q.missing == q.raw_points == 1 for q in qualities)
