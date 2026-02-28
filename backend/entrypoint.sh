#!/bin/sh
# Run migrations then exec the main command (uvicorn or worker).
set -e
echo "Waiting for database..."
sleep 5
for i in 1 2 3 4 5 6 7 8 9 10; do
  if alembic upgrade head 2>/dev/null; then
    echo "Migrations done."
    break
  fi
  if [ "$i" = 10 ]; then echo "Migrations failed (DB not ready?)."; exit 1; fi
  echo "Retry $i/10..."
  sleep 3
done
echo "Starting: $*"
exec "$@"
