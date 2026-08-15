#!/bin/bash
set -e

echo "=== Starting Backend ==="

cd /app/server

# Wait for PostgreSQL to be ready
echo "Waiting for PostgreSQL..."
MAX_RETRIES=30
RETRY_COUNT=0

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    if pg_isready -h localhost -p 5432 > /dev/null 2>&1; then
        echo "PostgreSQL is ready"
        break
    fi
    RETRY_COUNT=$((RETRY_COUNT + 1))
    echo "Waiting for PostgreSQL... ($RETRY_COUNT/$MAX_RETRIES)"
    sleep 2
done

if [ $RETRY_COUNT -eq $MAX_RETRIES ]; then
    echo "ERROR: PostgreSQL did not become ready in time"
    exit 1
fi

# Record current revision before upgrading
CURRENT_REV=$(uv run --frozen --no-sync alembic current 2>/dev/null | grep -oE '^[a-f0-9]+' | head -1)

# Run database migrations
echo "Running database migrations..."
uv run --frozen --no-sync alembic upgrade head

MIGRATION_EXIT_CODE=$?
if [ $MIGRATION_EXIT_CODE -eq 0 ]; then
    echo "Migrations completed successfully"
else
    echo "ERROR: Migration failed with exit code: $MIGRATION_EXIT_CODE"
    if [ -n "$CURRENT_REV" ]; then
        echo "Attempting to rollback to previous revision: $CURRENT_REV"
        uv run --frozen --no-sync alembic downgrade "$CURRENT_REV"
        if [ $? -eq 0 ]; then
            echo "Database rolled back successfully."
            echo "Please run: ./start.sh rollback"
        else
            echo "WARNING: Rollback also failed. Manual intervention may be required."
        fi
    fi
    exit 1
fi

# Skip startup migrations since we already ran them above
export SKIP_STARTUP_MIGRATIONS=true

# Start uvicorn
echo "Starting uvicorn..."
exec uv run --frozen --no-sync uvicorn server.main:app --host 0.0.0.0 --port 8000 --no-server-header --workers 2
