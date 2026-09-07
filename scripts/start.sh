#!/usr/bin/env bash
set -euo pipefail

echo "Applying database migrations..."
alembic upgrade head

echo "Verifying application schema..."
python -c "from sqlalchemy import inspect; from app.core.database import engine; tables = inspect(engine).get_table_names(); assert 'users' in tables, 'users table is missing after migrations'; print(f'Database schema ready: {len(tables)} tables')"

echo "Starting application..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
