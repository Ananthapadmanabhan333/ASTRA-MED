# ASTRA-MED API image. Build from the repository root (the assistant cites files in docs/):
#   docker build -f backend/Dockerfile -t astra-med-api .
#   docker build -f backend/Dockerfile --build-arg TRAIN_MODELS=0 -t astra-med-api .   # faster; trains on first start
#
# TRAIN_MODELS=1 (default) trains and verifies the AI model version during the build, so the image
# is self-contained and every container starts with the same, hash-verified models.
# INSTALL_TORCH=0 leaves PyTorch out (smaller image): the autoencoder and neural forecasters are then
# skipped and the remaining detectors and XGBoost serve.
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

ARG INSTALL_TORCH=1
COPY backend/requirements.txt backend/requirements-torch.txt backend/constraints.txt ./
# constraints.txt pins the exact versions the test suite passed with.
RUN pip install -r requirements.txt -c constraints.txt
# PyTorch comes from its own CPU index; installed separately so that index applies to torch only.
RUN if [ "$INSTALL_TORCH" = "1" ]; then pip install -r requirements-torch.txt -c constraints.txt; fi

COPY backend/app ./app
COPY backend/scripts ./scripts
COPY backend/knowledge ./knowledge
COPY backend/migrations ./migrations
COPY backend/alembic.ini ./alembic.ini
COPY docs ./docs

ENV ASTRA_AI_ARTIFACTS_DIR=/app/artifacts \
    ASTRA_ASSISTANT_DOCS_DIR=/app/docs \
    ASTRA_ASSISTANT_KNOWLEDGE_DIR=/app/knowledge

ARG TRAIN_MODELS=1
RUN mkdir -p /app/artifacts && if [ "$TRAIN_MODELS" = "1" ]; then python -m app.ai.train --no-publish; fi

RUN useradd --create-home --uid 10001 astra && chown -R astra /app/artifacts
USER astra

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=4s --start-period=120s --retries=5 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/readyz', timeout=3).status==200 else 1)"

CMD ["sh", "scripts/docker-entrypoint.sh"]
