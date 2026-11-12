FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt requirements-torch.txt ./
RUN pip install -r requirements.txt -r requirements-torch.txt

COPY app ./app
COPY scripts ./scripts

ENV ASTRA_AI_ARTIFACTS_DIR=/app/artifacts
RUN useradd --create-home --uid 10001 astra && mkdir -p /app/artifacts && chown -R astra /app
USER astra

EXPOSE 8000
# First start trains the AI models into the artifacts volume (~6 min on CPU); later starts reuse them.
HEALTHCHECK --interval=15s --timeout=3s --start-period=600s --retries=5 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/system/health').status==200 else 1)"

CMD ["sh", "-c", "python -m app.ai.train --if-missing --no-publish && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers"]
