"""Assistant: retrieval accuracy, citation correctness, safety, missing information and Claude mode."""

from __future__ import annotations

import json
import sys
import types

import pytest

from app.assistant import corpus
from app.assistant.corpus import doc_passages, reference_passages
from app.assistant.retrieval import PassageIndex, stem
from app.assistant.safety import screen

# (question, acceptable (document, word in its section heading) pairs)
RETRIEVAL_CASES = [
    ("How is the personal baseline computed?", [("docs/AI_ENGINE.md", "baseline")]),
    ("What happens when the api.nasa.gov DONKI proxy fails?", [("docs/NASA_DATA_SOURCES.md", "donki")]),
    ("Does correlation between solar activity and heart rate show causation?",
     [("docs/SPACE_ENVIRONMENT.md", "correlation"), ("docs/SPACE_ENVIRONMENT.md", "")]),
    ("How are anomaly detector thresholds calibrated?", [("docs/AI_ENGINE.md", "anomaly")]),
    ("How is radiation dose shown and why are categories never summed?",
     [("docs/SPACE_ENVIRONMENT.md", "radiation"), ("docs/NASA_DATA_SOURCES.md", "categor")]),
    ("What does the EDA environmental data app provide from the ISS?", [("docs/NASA_DATA_SOURCES.md", "eda")]),
    ("How are forecast intervals produced?", [("docs/AI_ENGINE.md", "forecast")]),
    ("How does the WebSocket stream live vitals?", [("docs/API.md", "websocket"), ("docs/ARCHITECTURE.md", "")]),
]


@pytest.fixture(scope="module")
def index() -> PassageIndex:
    return PassageIndex(doc_passages())


def test_stemmer():
    assert stem("baselines") == stem("baseline") == "baselin"
    assert stem("computed") == stem("compute") and stem("flares") == stem("flare")


def test_retrieval_top3_accuracy(index):
    hits_ok = 0
    for question, accepted in RETRIEVAL_CASES:
        top = index.search(question, k=3)
        if any(h.passage.path == path and word in (h.passage.section or "").lower()
               for h in top for path, word in accepted):
            hits_ok += 1
    assert hits_ok / len(RETRIEVAL_CASES) >= 0.75, hits_ok


def test_passages_come_from_real_files_and_skip_tables():
    passages = doc_passages()
    assert passages and all(p.source_type == "astra_docs" and p.path.startswith("docs/") for p in passages)
    assert not any(" ; Method ; Path" in p.text for p in passages)
    assert len({p.id for p in passages}) == len(passages)


def test_reference_library_loads_only_approved_existing_files(tmp_path, monkeypatch):
    (tmp_path / "ok.txt").write_text("Approved text about crew sleep schedules in long missions. " * 5, encoding="utf-8")
    (tmp_path / "draft.txt").write_text("Not yet reviewed. " * 20, encoding="utf-8")
    (tmp_path / "manifest.json").write_text(json.dumps({"documents": [
        {"file": "ok.txt", "title": "Approved doc", "publisher": "Test", "approved": True},
        {"file": "draft.txt", "title": "Draft doc", "approved": False},
        {"file": "missing.txt", "title": "Missing doc", "approved": True},
    ]}), encoding="utf-8")
    passages, entries = reference_passages(tmp_path)
    assert {p.title for p in passages} == {"Approved doc"}
    assert [e["loaded"] for e in entries] == [True, False, False]
    assert reference_passages(tmp_path / "nowhere") == ([], [])


@pytest.mark.parametrize(("question", "declined", "escalate"), [
    ("Does AST-02 have pneumonia?", 1, False),
    ("What medication should Lukas take for this?", 1, False),
    ("Diagnose the commander and suggest a treatment", 2, False),
    ("The commander collapsed and is not breathing", 0, True),
    ("Show heart rate for AST-01 over the last 24 hours", 0, False),
    ("What was the radiation dose of AST-03 yesterday?", 0, False),
    ("Does AST-02 have any open alerts?", 0, False),
])
def test_safety_screen(question, declined, escalate):
    r = screen(question)
    assert len(r.declined) == declined and r.escalate is escalate


def _check_citations(ans: dict) -> None:
    ids = {s["id"] for s in ans["sources"]}
    for st in ans["statements"]:
        assert set(st["citations"]) <= ids
        if st["kind"] not in ("safety",):
            assert st["citations"], st
    passages = {p.id: p for p in doc_passages()}
    for s in ans["sources"]:
        if s["id"].startswith("S") and s["source_type"] == "astra_docs":
            text = " ".join(p.text for p in passages.values() if p.path == s["path"])
            assert s["excerpt"] in text  # quotes are verbatim, never paraphrased into a fake citation


async def test_answers_cite_every_statement(p5):
    await p5.client.post("/api/simulation/events", json={"scenario": "desaturation", "astronaut_id": "AST-02",
                                                         "intensity": 1.3, "duration_seconds": 900})
    await p5.tick(240)
    for q in ("Why did the desaturation alert fire for Lukas?", "How is the personal baseline computed?",
              "Summarize heart rate trends for Maya over the last 14 days", "How is AST-03 doing right now?"):
        r = await p5.client.post("/api/assistant/ask", json={"question": q})
        assert r.status_code == 200, r.text
        ans = r.json()
        assert ans["statements"] and ans["mode"] == "extractive"
        _check_citations(ans)
    kinds = {s["kind"] for s in ans["statements"]}
    assert kinds & {"data", "derived"}


async def test_alert_question_separates_data_model_and_escalates(p5):
    await p5.client.post("/api/simulation/events", json={"scenario": "desaturation", "astronaut_id": "AST-02",
                                                         "intensity": 1.3, "duration_seconds": 900})
    await p5.tick(240)
    ans = (await p5.client.post("/api/assistant/ask", json={"question": "Explain the alert for AST-02"})).json()
    kinds = [s["kind"] for s in ans["statements"]]
    assert "data" in kinds and "derived" in kinds
    assert any("simulated test scenario" in s["text"] for s in ans["statements"])
    assert ans["escalation"]["required"] and ans["escalation"]["who"] == "Flight surgeon on duty"
    assert any(src["link"] and src["link"].startswith("/medical") for src in ans["sources"])


async def test_diagnosis_and_treatment_are_declined_but_data_still_shown(p5):
    ans = (await p5.client.post("/api/assistant/ask", json={
        "question": "Does Lukas have pneumonia and what medication should he take?"})).json()
    assert len(ans["declined"]) == 2
    data = [s for s in ans["statements"] if s["kind"] != "safety"]
    assert data and not any(w in s["text"].lower() for s in data for w in ("pneumonia", "antibiotic", "medication"))


async def test_knowledge_question_reports_missing_reference_material(p5):
    ans = (await p5.client.post("/api/assistant/ask", json={"question": "Is a heart rate of 110 dangerous?"})).json()
    assert any("no approved reference documents" in m for m in ans["missing_information"])
    limits = [s for s in ans["statements"] if s["kind"] == "configured"]
    assert limits and "not clinical criteria" in limits[0]["text"]
    assert not any(s["kind"] == "reference" for s in ans["sources"])


async def test_emergency_description_escalates_and_names_the_gap(p5):
    ans = (await p5.client.post("/api/assistant/ask", json={
        "question": "Maya has chest pain and collapsed"})).json()
    assert ans["escalation"]["required"] and ans["statements"][-1]["kind"] == "safety"
    assert any("no symptom reports" in m for m in ans["missing_information"])


async def test_incident_report_request_proposes_an_action(p5):
    await p5.client.post("/api/simulation/events", json={"scenario": "desaturation", "astronaut_id": "AST-02",
                                                         "intensity": 1.3, "duration_seconds": 900})
    await p5.tick(200)
    ans = (await p5.client.post("/api/assistant/ask", json={
        "question": "Generate an incident report for Lukas Brandt's latest alert"})).json()
    assert ans["actions"] and ans["actions"][0]["type"] == "create_report"
    reports = (await p5.client.get("/api/reports")).json()
    assert reports == []  # asking never creates anything by itself


async def test_claude_mode_without_package_or_key_falls_back(p5, monkeypatch):
    p5.app.state.settings.assistant_mode = "claude"
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    ans = (await p5.client.post("/api/assistant/ask", json={"question": "How is AST-01 doing?"})).json()
    assert ans["mode"] == "extractive" and "unavailable" in ans["model_note"]


async def test_claude_mode_maps_citations_to_sources(p5, monkeypatch):
    """Exercise the Claude path with a stub client: no network, no key leaves the process."""
    captured = {}

    class Block:
        def __init__(self, text, cites=None):
            self.type, self.text, self.citations = "text", text, cites

    class Cite:
        def __init__(self, i):
            self.type, self.document_index, self.cited_text = "char_location", i, "x"

    class Messages:
        async def create(self, **kw):
            captured.update(kw)
            return types.SimpleNamespace(stop_reason="end_turn", content=[
                types.SimpleNamespace(type="thinking", thinking="..."),
                Block("Latest values come from the simulated reading.", [Cite(0)]),
                Block("Uncited aside."),
            ])

    fake = types.ModuleType("anthropic")
    fake.AsyncAnthropic = lambda: types.SimpleNamespace(messages=Messages())
    monkeypatch.setitem(sys.modules, "anthropic", fake)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-not-a-real-key")
    p5.app.state.settings.assistant_mode = "claude"
    ans = (await p5.client.post("/api/assistant/ask", json={"question": "How is AST-01 doing?"})).json()
    assert ans["mode"] == "claude"
    docs = [b for b in captured["messages"][0]["content"] if b["type"] == "document"]
    assert docs and all(d["citations"] == {"enabled": True} and d["source"]["type"] == "text" for d in docs)
    assert captured["model"] == "claude-opus-5-5" and "Never diagnose" in captured["system"]
    first = ans["statements"][0]
    assert first["citations"] == ["D1"] and {s["id"] for s in ans["sources"]} == {"D1"}
    assert ans["statements"][1]["kind"] == "uncited"


async def test_claude_refusal_falls_back_to_extractive(p5, monkeypatch):
    class Messages:
        async def create(self, **kw):
            return types.SimpleNamespace(stop_reason="refusal", content=[])

    fake = types.ModuleType("anthropic")
    fake.AsyncAnthropic = lambda: types.SimpleNamespace(messages=Messages())
    monkeypatch.setitem(sys.modules, "anthropic", fake)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-not-a-real-key")
    p5.app.state.settings.assistant_mode = "claude"
    ans = (await p5.client.post("/api/assistant/ask", json={"question": "How is AST-01 doing?"})).json()
    assert ans["mode"] == "extractive" and "failed" in ans["model_note"]


async def test_status_lists_sources_and_empty_reference_library(p5):
    st = (await p5.client.get("/api/assistant/status")).json()
    assert st["by_source"]["astra_docs"] > 50 and st["mode"]["mode"] == "extractive"
    assert "No approved reference documents" in st["reference_note"]
    assert corpus.KNOWLEDGE_DIR.name == "knowledge"
