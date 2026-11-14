# Contributing to ASTRA-MED

## Ground rules

1. **No fabricated data or results.** Crew data come from the simulator and are labelled `simulated`;
   self-check entries are `self_reported`; NASA data keep their category. Every reported number must
   come from an executed run.
2. **No clinical claims.** ASTRA-MED is not a medical device. Guidance is process guidance ("tell the
   flight surgeon"), never a diagnosis or a treatment.
3. **No secrets in the repository.** Configuration comes from `ASTRA_*` environment variables. Demo
   credentials live only in the git-ignored `backend/.dev-users.json`.
4. **Don't break earlier phases.** The full test suite must pass before a change is merged.

## Workflow

```bash
# backend (Python 3.11)
cd backend && python -m venv .venv && .venv/Scripts/activate && pip install -r requirements-dev.txt -c constraints.txt
python -m pytest -q && python -m ruff check app tests scripts
# after changing app/db/models.py
alembic revision --autogenerate -m "describe the change"   # review the file, then
alembic upgrade head && alembic check
# after changing API schemas
python scripts/export_openapi.py && (cd ../frontend && npm run gen:api)
# frontend
cd frontend && npm install && npm test && npm run typecheck && npm run lint && npm run build
```

- Keep the API contract-first: Pydantic schema → OpenAPI → generated TypeScript types.
- Model changes: train with `python -m app.ai.train`, keep the registered version's report, and update
  [SCIENTIFIC_VALIDATION.md](docs/SCIENTIFIC_VALIDATION.md) with the new numbers only.
- Write commit messages in the imperative mood ("Add …", "Fix …"), and say in the body why.
- Disclose AI assistance: commits co-written by an AI assistant carry a `Co-Authored-By` trailer.

## Where things are

See [README.md](README.md#repository-layout) and the
[architecture](docs/ARCHITECTURE.md). Open work is tracked in
[MASTER_COMPLETION_TRACKER.md](MASTER_COMPLETION_TRACKER.md).
