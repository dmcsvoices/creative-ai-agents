# Database Corruption Recovery Guide

## Problem

When you see **500 errors** in the web GUI trying to view prompts, it's usually caused by corrupted database indexes. This happens when:
- The poets service crashes mid-write
- Multiple processes access the database simultaneously
- WAL (Write-Ahead Log) files aren't properly checkpointed

## Symptoms

- Web GUI shows: "Failed to load queue details: Failed to fetch prompts: 500"
- Poets service can't see queued prompts
- API endpoint `/api/prompts` returns 500 Internal Server Error

## Quick Fix - One Command

From the `poets-service-clean` directory, run:

```bash
./fix_database_corruption.sh
```

That's it! The script will:
1. Check database integrity on the host
2. Reindex if needed
3. Checkpoint WAL files
4. Check database integrity inside Docker container
5. Fix Docker container's view of the database
6. Verify everything is healthy

## Manual Commands (if you want to understand what's happening)

### Fix Database on Host (Outside Container)

```bash
# Check integrity
sqlite3 /Volumes/Tikbalang2TB/Users/tikbalang/Desktop/anthonys_musings.db "PRAGMA integrity_check;"

# Fix if corrupted
sqlite3 /Volumes/Tikbalang2TB/Users/tikbalang/Desktop/anthonys_musings.db "REINDEX;"

# Checkpoint WAL
sqlite3 /Volumes/Tikbalang2TB/Users/tikbalang/Desktop/anthonys_musings.db "PRAGMA wal_checkpoint(TRUNCATE);"
```

### Fix Database Inside Docker Container

```bash
# Check integrity
docker exec anthonys-musings-api-api-1 python3 -c "import sqlite3; conn = sqlite3.connect('/app/database/anthonys_musings.db'); cursor = conn.cursor(); cursor.execute('PRAGMA integrity_check'); print(cursor.fetchone()[0])"

# Reindex
docker exec anthonys-musings-api-api-1 python3 -c "import sqlite3; conn = sqlite3.connect('/app/database/anthonys_musings.db'); conn.execute('REINDEX'); conn.close()"

# Checkpoint WAL
docker exec anthonys-musings-api-api-1 python3 -c "import sqlite3; conn = sqlite3.connect('/app/database/anthonys_musings.db'); conn.execute('PRAGMA wal_checkpoint(RESTART)'); conn.close()"
```

### Restart API Container (if needed)

```bash
docker restart anthonys-musings-api-api-1
```

## Prevention

The recent git commits added automatic WAL checkpointing to prevent this issue:
- After processing prompts, the service now runs `PRAGMA wal_checkpoint(TRUNCATE)`
- Both the API and poets service use WAL mode for consistency
- This should reduce corruption significantly

## Related Issues

See git commits:
- `f8581fa` - Long-term fix: Eliminate database index corruption
- `9a4a477` - Auto-checkpoint WAL after processing for Docker API visibility
- `f541c77` - Add WAL mode to Poets Service main database connection

## Troubleshooting

**Q: The script says "Database is already healthy" but I still get 500 errors**

A: Try restarting the API container:
```bash
docker restart anthonys-musings-api-api-1
```

**Q: Docker container is not running**

A: Start it with:
```bash
cd /Users/tikbalang/anthonys-musings-api
docker-compose up -d
```

**Q: Prompts are stuck in "processing" status**

A: Reset them manually:
```bash
sqlite3 /Volumes/Tikbalang2TB/Users/tikbalang/Desktop/anthonys_musings.db \
  "UPDATE prompts SET status = 'unprocessed', processed_at = NULL, error_message = NULL WHERE status = 'processing' AND id = YOUR_PROMPT_ID;"
```
