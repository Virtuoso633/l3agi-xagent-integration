#!/bin/bash
host=${DB_HOST:-db}
port=${DB_PORT:-5432}
echo "Waiting for database $host:$port..."
# wait for TCP port to be open
while ! bash -c ">/dev/tcp/$host/$port" >/dev/null 2>&1; do
  sleep 1
done
echo "Database is available at $host:$port"

# run migrations then start app
alembic upgrade head

exec uvicorn main:app --host 0.0.0.0 --port 4000 --reload