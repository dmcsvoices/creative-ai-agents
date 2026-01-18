"""
Database transaction utilities for atomic operations with automatic rollback.

This module provides:
- Context manager for atomic transactions with IMMEDIATE isolation level
- Automatic commit on success, rollback on exception
- Connection lifecycle management (always closed)
- WAL checkpoint utilities for flushing writes to main database

Usage:
    from db_utils import db_transaction, force_wal_checkpoint

    # Atomic transaction with automatic rollback
    with db_transaction(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE ...")
        # Automatic commit on success, rollback on exception

    # Force WAL checkpoint to flush writes
    force_wal_checkpoint(db_path, mode="RESTART")
"""

import sqlite3
import logging
from contextlib import contextmanager
from typing import Generator

logger = logging.getLogger(__name__)


@contextmanager
def db_transaction(
    db_path: str,
    isolation_level: str = "IMMEDIATE",
    timeout: int = 30
) -> Generator[sqlite3.Connection, None, None]:
    """
    Context manager for atomic database transactions.

    Ensures:
    - Automatic commit on success
    - Automatic rollback on exception
    - Connection always closed
    - WAL mode enabled with proper PRAGMA settings

    Args:
        db_path: Path to SQLite database
        isolation_level: Transaction isolation level
            - IMMEDIATE (default): Acquires write lock at BEGIN, prevents "locked" errors
            - DEFERRED: Acquires lock on first write (can cause conflicts)
            - EXCLUSIVE: Prevents all other connections (use sparingly)
        timeout: Busy timeout in seconds (default: 30)

    Yields:
        sqlite3.Connection: Database connection configured for WAL mode

    Raises:
        sqlite3.Error: On database errors (after rollback)
        Exception: On other errors (after rollback)

    Example:
        with db_transaction('/path/to/db.db') as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO table VALUES (?)", (value,))
            cursor.execute("UPDATE other_table SET x = ?", (y,))
            # Both succeed or both fail (atomic)
    """
    conn = None
    try:
        # Connect with manual transaction control (isolation_level=None)
        # This allows us to explicitly control BEGIN/COMMIT/ROLLBACK
        conn = sqlite3.connect(db_path, timeout=timeout, isolation_level=None)

        # Configure for WAL mode with optimal settings
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=30000")  # 30 second timeout
        conn.execute("PRAGMA cache_size=10000")     # 10MB cache
        conn.execute("PRAGMA temp_store=memory")    # Temp tables in RAM

        # Begin transaction with explicit isolation level
        if isolation_level:
            conn.execute(f"BEGIN {isolation_level}")
            logger.debug(f"Transaction started with {isolation_level} isolation")

        # Yield connection to caller
        yield conn

        # Commit if no exception occurred
        conn.commit()
        logger.debug("Transaction committed successfully")

    except sqlite3.Error as e:
        # Database-specific error (constraint violation, etc.)
        logger.error(f"Database error in transaction: {e}")
        if conn:
            try:
                conn.rollback()
                logger.info("Transaction rolled back due to database error")
            except Exception as rollback_error:
                logger.error(f"Rollback failed: {rollback_error}")
        raise

    except Exception as e:
        # Non-database error (Python exception, etc.)
        logger.error(f"Non-database error in transaction: {e}")
        if conn:
            try:
                conn.rollback()
                logger.info("Transaction rolled back due to non-database error")
            except Exception as rollback_error:
                logger.error(f"Rollback failed: {rollback_error}")
        raise

    finally:
        # Always close the connection
        if conn:
            try:
                conn.close()
                logger.debug("Database connection closed")
            except Exception as e:
                logger.error(f"Error closing connection: {e}")


def force_wal_checkpoint(db_path: str, mode: str = "RESTART") -> bool:
    """
    Force WAL checkpoint to flush transactions to main database file.

    This ensures that writes trapped in the WAL file are flushed to the main
    database, making them visible to all processes (including Docker containers).

    Args:
        db_path: Path to SQLite database
        mode: Checkpoint mode
            - PASSIVE: Checkpoint as much as possible without blocking writers
            - FULL: Wait for writers to finish, then checkpoint all frames
            - RESTART: FULL + mark WAL for reuse (recommended - safe and effective)
            - TRUNCATE: FULL + truncate WAL to 0 bytes (aggressive, can cause corruption)

    Returns:
        bool: True if checkpoint fully successful, False if blocked/partial

    Example:
        # After writing important data
        if force_wal_checkpoint(db_path, mode="RESTART"):
            print("Data flushed successfully")
        else:
            print("Checkpoint partially blocked by readers")
    """
    try:
        # Use short timeout - checkpoint should be quick
        conn = sqlite3.connect(db_path, timeout=5)
        try:
            cursor = conn.execute(f"PRAGMA wal_checkpoint({mode})")
            result = cursor.fetchone()

            if result:
                busy, log_size, checkpointed = result
                # busy=0 means fully successful
                # busy=1 means some frames couldn't be checkpointed (readers blocking)
                if busy == 0:
                    logger.info(
                        f"WAL checkpoint successful: {checkpointed} frames flushed, "
                        f"log size: {log_size}"
                    )
                    return True
                else:
                    logger.warning(
                        f"WAL checkpoint partially blocked: {checkpointed}/{log_size} frames"
                    )
                    return False

            return True

        finally:
            conn.close()

    except Exception as e:
        logger.error(f"WAL checkpoint failed: {e}")
        return False


def get_transaction_stats(db_path: str) -> dict:
    """
    Get WAL transaction statistics for monitoring and debugging.

    Useful for diagnosing database issues like WAL growth, checkpoint failures,
    or visibility problems.

    Args:
        db_path: Path to SQLite database

    Returns:
        dict: Transaction statistics including:
            - journal_mode: Current journal mode (should be 'wal')
            - db_size_bytes: Main database file size
            - wal_size_bytes: WAL file size
            - wal_frames: Number of uncommitted WAL frames
            - wal_ratio: Ratio of WAL size to database size
            - error: Error message if stats unavailable

    Example:
        stats = get_transaction_stats(db_path)
        if stats.get('wal_ratio', 0) > 0.5:
            print("⚠️ WAL file is growing too large - checkpoint needed!")
            force_wal_checkpoint(db_path)
    """
    try:
        conn = sqlite3.connect(db_path, timeout=5)
        try:
            cursor = conn.cursor()

            # Get WAL status
            cursor.execute("PRAGMA wal_checkpoint")
            wal_info = cursor.fetchone()

            # Get database size info
            cursor.execute("PRAGMA page_count")
            page_count = cursor.fetchone()[0]

            cursor.execute("PRAGMA page_size")
            page_size = cursor.fetchone()[0]

            cursor.execute("PRAGMA journal_mode")
            journal_mode = cursor.fetchone()[0]

            # Check for WAL file
            import os
            wal_file = f"{db_path}-wal"
            wal_size = os.path.getsize(wal_file) if os.path.exists(wal_file) else 0

            db_size = page_count * page_size
            wal_ratio = wal_size / db_size if db_size > 0 else 0

            return {
                "journal_mode": journal_mode,
                "db_size_bytes": db_size,
                "wal_size_bytes": wal_size,
                "wal_frames": wal_info[1] if wal_info else 0,
                "wal_busy": bool(wal_info[0]) if wal_info else False,
                "wal_ratio": wal_ratio
            }

        finally:
            conn.close()

    except Exception as e:
        return {"error": str(e)}


# Example usage and testing
if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(level=logging.DEBUG)

    # This is just for documentation - don't run against real database
    print("db_utils.py - Database Transaction Utilities")
    print("=" * 60)
    print("\nThis module provides:")
    print("  1. db_transaction() - Atomic transaction context manager")
    print("  2. force_wal_checkpoint() - WAL checkpoint utility")
    print("  3. get_transaction_stats() - Transaction monitoring")
    print("\nImport this module in your code:")
    print("  from db_utils import db_transaction, force_wal_checkpoint")
    print("")
