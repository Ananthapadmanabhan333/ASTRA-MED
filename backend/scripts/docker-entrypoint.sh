#!/bin/sh
# Container start for the ASTRA-MED API.
#
#   ASTRA_MIGRATE_ON_START=true   run `alembic upgrade head` first (single-instance setups such as
#                                 docker compose; on Render/AWS run it as a pre-deploy step instead)
#   ASTRA_TRAIN_ON_START=true     train the AI models if the image/volume has none yet (~4-6 min CPU)
#   FORWARDED_ALLOW_IPS           proxies whose X-Forwarded-For/-Proto headers are trusted. Set it to
#                                 the platform proxy's address range, or "*" only when that proxy is
#                                 the sole way to reach the container (Render, an ALB in a private
#                                 subnet). Without it, every client appears as the proxy's address.
set -eu

if [ "${ASTRA_MIGRATE_ON_START:-false}" = "true" ]; then
  alembic upgrade head
fi

if [ "${ASTRA_TRAIN_ON_START:-true}" = "true" ]; then
  python -m app.ai.train --if-missing --no-publish
fi

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" \
  --proxy-headers --forwarded-allow-ips "${FORWARDED_ALLOW_IPS:-127.0.0.1}" \
  --no-server-header
