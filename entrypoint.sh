#!/usr/bin/env bash
set -euo pipefail

# Wait for MySQL using Python's stdlib socket
python - <<'PY'
import os, socket, time
host = os.environ.get("DB_HOST", "db")
port = int(os.environ.get("DB_PORT", "3306"))
deadline = time.time() + 120
while True:
    try:
        with socket.create_connection((host, port), timeout=2):
            break
    except OSError:
        if time.time() > deadline:
            raise SystemExit("MySQL wait timeout")
        time.sleep(1)
print("MySQL is reachable.")
PY

# Migration mode:
# - Normal (default): run migrations
# - Stamp: ONLY when schema already exists but alembic_version is missing
if [ "${ALEMBIC_STAMP_HEAD:-false}" = "true" ]; then
  echo "Stamping Alembic at HEAD (no SQL executed)..."
  alembic stamp head
else
  echo "Applying Alembic migrations (upgrade head)..."
  alembic upgrade head
fi

exec uvicorn app.main:app --host 0.0.0.0 --port 8000
