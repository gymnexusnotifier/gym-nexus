#!/usr/bin/env bash
set -euo pipefail

echo "Applying database migrations..."
alembic upgrade head

echo "Verifying application schema..."
python -c "from sqlalchemy import inspect; from app.core.database import engine; tables = set(inspect(engine).get_table_names()); required = {'users', 'expenses', 'payroll_records', 'staff_leaves'}; missing = required - tables; assert not missing, f'Missing required tables after migrations: {sorted(missing)}'; print(f'Database schema ready: {len(tables)} tables')"

echo "Starting application..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
