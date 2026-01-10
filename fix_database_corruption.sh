#!/bin/bash
#
# Database Corruption Recovery Script
# This fixes the index corruption issue that causes 500 errors in the API
#
# Usage: ./fix_database_corruption.sh
#

set -e  # Exit on error

DB_PATH="/Volumes/Tikbalang2TB/Users/tikbalang/Desktop/anthonys_musings.db"
DOCKER_CONTAINER="anthonys-musings-api-api-1"

echo "=================================================="
echo "Database Corruption Recovery Script"
echo "=================================================="
echo ""

# Check if database exists
if [ ! -f "$DB_PATH" ]; then
    echo "❌ ERROR: Database not found at $DB_PATH"
    exit 1
fi

echo "Step 1: Checking database integrity (outside container)..."
INTEGRITY=$(sqlite3 "$DB_PATH" "PRAGMA integrity_check;" 2>&1 | head -1)
echo "   Result: $INTEGRITY"
echo ""

if [ "$INTEGRITY" = "ok" ]; then
    echo "✅ Database is already healthy (outside container)"
else
    echo "⚠️  Database has corruption, fixing..."
    echo ""

    echo "Step 2: Reindexing database (outside container)..."
    sqlite3 "$DB_PATH" "REINDEX;" 2>&1
    echo "   ✅ Reindex complete"
    echo ""

    echo "Step 3: Checkpointing WAL (outside container)..."
    sqlite3 "$DB_PATH" "PRAGMA wal_checkpoint(TRUNCATE);" 2>&1
    echo "   ✅ WAL checkpoint complete"
    echo ""

    echo "Step 4: Verifying integrity (outside container)..."
    INTEGRITY_AFTER=$(sqlite3 "$DB_PATH" "PRAGMA integrity_check;" 2>&1 | head -1)
    echo "   Result: $INTEGRITY_AFTER"
    echo ""
fi

# Check if Docker container is running
if ! docker ps --format '{{.Names}}' | grep -q "^${DOCKER_CONTAINER}$"; then
    echo "⚠️  Docker container $DOCKER_CONTAINER is not running"
    echo "   Skipping Docker container fix"
    echo ""
    echo "=================================================="
    echo "✅ Recovery complete (host only)"
    echo "=================================================="
    exit 0
fi

echo "Step 5: Checking database integrity (inside Docker container)..."
DOCKER_INTEGRITY=$(docker exec "$DOCKER_CONTAINER" python3 -c "import sqlite3; conn = sqlite3.connect('/app/database/anthonys_musings.db'); cursor = conn.cursor(); cursor.execute('PRAGMA integrity_check'); print(cursor.fetchone()[0])" 2>&1)
echo "   Result: $DOCKER_INTEGRITY"
echo ""

if [ "$DOCKER_INTEGRITY" = "ok" ]; then
    echo "✅ Database is already healthy (inside Docker)"
else
    echo "⚠️  Database has corruption in Docker, fixing..."
    echo ""

    echo "Step 6: Reindexing database (inside Docker container)..."
    docker exec "$DOCKER_CONTAINER" python3 -c "import sqlite3; conn = sqlite3.connect('/app/database/anthonys_musings.db'); conn.execute('REINDEX'); conn.close(); print('Reindex complete')" 2>&1
    echo "   ✅ Reindex complete"
    echo ""

    echo "Step 7: Checkpointing WAL (inside Docker container)..."
    docker exec "$DOCKER_CONTAINER" python3 -c "import sqlite3; conn = sqlite3.connect('/app/database/anthonys_musings.db'); conn.execute('PRAGMA wal_checkpoint(RESTART)'); conn.close(); print('WAL checkpoint complete')" 2>&1
    echo "   ✅ WAL checkpoint complete"
    echo ""

    echo "Step 8: Verifying integrity (inside Docker container)..."
    DOCKER_INTEGRITY_AFTER=$(docker exec "$DOCKER_CONTAINER" python3 -c "import sqlite3; conn = sqlite3.connect('/app/database/anthonys_musings.db'); cursor = conn.cursor(); cursor.execute('PRAGMA integrity_check'); print(cursor.fetchone()[0])" 2>&1)
    echo "   Result: $DOCKER_INTEGRITY_AFTER"
    echo ""
fi

echo "=================================================="
echo "✅ Database recovery complete!"
echo "=================================================="
echo ""
echo "Summary:"
echo "  - Host database: $INTEGRITY_AFTER"
echo "  - Docker database: $DOCKER_INTEGRITY_AFTER"
echo ""
echo "Your API should now work without 500 errors."
