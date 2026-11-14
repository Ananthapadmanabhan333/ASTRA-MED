"""Crew self-check: orientation bands, prompts, persistence and permissions."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.selfcheck.service import glucose_band, mood_assessment, prompt_status, symptom_assessment


def test_glucose_bands_follow_ada_orientation_ranges():
    assert glucose_band(50, "fasting").status == "contact"
    assert glucose_band(65, "random").status == "attention"
    assert glucose_band(92, "fasting").status == "normal"
    assert glucose_band(110, "fasting").status == "attention"
    assert glucose_band(130, "fasting").status == "contact"
    assert glucose_band(130, "after_meal").status == "normal"
    assert glucose_band(170, "after_meal").status == "attention"
    assert glucose_band(240, "random").status == "contact"


def test_mood_uses_personal_baseline_and_low_streak():
    now = datetime(2026, 11, 14, tzinfo=UTC)
    assert mood_assessment([])["status"] == "no_data"
    usual = [(now - timedelta(days=i), 4) for i in range(1, 8)]
    assert mood_assessment([(now, 4), *usual])["status"] == "normal"
    assert mood_assessment([(now, 2), *usual])["status"] == "attention"
    streak = [(now - timedelta(days=i), 2) for i in range(3)]
    assert mood_assessment(streak + usual)["status"] == "contact"


def test_symptoms_escalate_only_for_contact_symptoms():
    assert symptom_assessment([])["status"] == "normal"
    assert symptom_assessment(["headache"])["status"] == "attention"
    assert symptom_assessment(["headache", "chest_pain"])["status"] == "contact"


def test_prompt_status():
    now = datetime(2026, 11, 14, 12, tzinfo=UTC)
    assert prompt_status(None, 24, now)["status"] == "due"
    assert prompt_status(now - timedelta(hours=2), 24, now)["status"] == "done"
    assert prompt_status(now - timedelta(hours=30), 24, now)["status"] == "due"
    assert prompt_status(now - timedelta(hours=40), 24, now)["status"] == "overdue"


async def test_self_check_round_trip_and_validation(api):
    client, _ = api
    empty = (await client.get("/api/crew/AST-01/self-check")).json()
    assert {i["key"]: i["status"] for i in empty["indicators"]} == {"glucose": "no_data", "mood": "no_data",
                                                                     "symptoms": "no_data"}
    assert {p["key"]: p["status"] for p in empty["prompts"] if not p["automatic"]} == {
        "glucose": "due", "mood": "due", "symptoms": "due"}

    r = await client.post("/api/crew/AST-01/self-check", json={"glucose_mg_dl": 112, "glucose_context": "fasting",
                                                               "mood": 4, "symptoms": [], "note": "Good sleep"})
    assert r.status_code == 201, r.text
    assert r.json()["data_source"] == "self_reported" and r.json()["symptoms_checked"] is True

    summary = (await client.get("/api/crew/AST-01/self-check")).json()
    ind = {i["key"]: i for i in summary["indicators"]}
    assert ind["glucose"]["status"] == "attention" and ind["glucose"]["value"] == 112
    assert ind["mood"]["status"] == "normal" and ind["symptoms"]["status"] == "normal"
    assert {p["key"]: p["status"] for p in summary["prompts"] if not p["automatic"]} == {
        "glucose": "done", "mood": "done", "symptoms": "done"}

    assert (await client.post("/api/crew/AST-01/self-check", json={})).status_code == 422
    assert (await client.post("/api/crew/AST-01/self-check", json={"glucose_mg_dl": 90})).status_code == 422
    assert (await client.post("/api/crew/AST-01/self-check", json={"symptoms": ["telepathy"]})).status_code == 422
    assert (await client.post("/api/crew/AST-01/self-check", json={"mood": 9})).status_code == 422
    assert (await client.get("/api/crew/AST-99/self-check")).status_code == 404


async def test_self_check_write_needs_permission(secure):
    async with secure.signed_in("analyst") as c:
        assert (await c.get("/api/crew/AST-02/self-check")).status_code == 200
        assert (await c.post("/api/crew/AST-02/self-check", json={"mood": 3})).status_code == 403
    async with secure.signed_in("flight_surgeon") as c:
        r = await c.post("/api/crew/AST-02/self-check", json={"mood": 3})
        assert r.status_code == 201 and r.json()["created_by"] == secure.users["flight_surgeon"][0]
    async with secure.signed_in("admin") as c:  # no crew health access at all
        assert (await c.get("/api/crew/AST-02/self-check")).status_code == 403
