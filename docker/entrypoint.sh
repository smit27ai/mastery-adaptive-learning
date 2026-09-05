#!/bin/sh
# Container entrypoint.
#
# Migrations run here, not in the application lifespan: schema changes must happen once
# per deploy, before any worker starts serving, rather than racing across replicas.
set -e

echo "Applying database migrations..."
alembic upgrade head

# Optional one-shot demo content. The seed is idempotent - it exits immediately if any
# concept already exists - so leaving this on across restarts is safe.
if [ "${SEED_DEMO_DATA:-false}" = "true" ]; then
  echo "Seeding demo curriculum..."
  python -m mastery.data.seed
fi

# Railway, Render and Fly all inject $PORT. Defaulting to 8000 keeps local runs working.
exec uvicorn mastery.api.main:app \
  --host 0.0.0.0 \
  --port "${PORT:-8000}" \
  --workers "${WEB_CONCURRENCY:-2}" \
  --proxy-headers \
  --forwarded-allow-ips '*'
