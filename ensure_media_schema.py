#!/usr/bin/env python3
"""
Ensure the SQLite schema has media artifact support.

This script creates the `prompt_artifacts` table and adds the
`artifact_status` / `artifact_metadata` columns to the `prompts` table
if they do not already exist.
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


def ensure_schema(db_path: Path) -> None:
    connection = sqlite3.connect(str(db_path))
    cursor = connection.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS prompt_artifacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prompt_id INTEGER NOT NULL,
            artifact_type TEXT NOT NULL,
            file_path TEXT NOT NULL,
            preview_path TEXT,
            metadata TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(prompt_id) REFERENCES prompts(id) ON DELETE CASCADE
        )
        """
    )

    cursor.execute("PRAGMA table_info('prompts')")
    columns = {row[1] for row in cursor.fetchall()}

    if "artifact_status" not in columns:
        cursor.execute(
            "ALTER TABLE prompts ADD COLUMN artifact_status TEXT DEFAULT 'pending'"
        )

    if "artifact_metadata" not in columns:
        cursor.execute(
            "ALTER TABLE prompts ADD COLUMN artifact_metadata TEXT"
        )

    connection.commit()
    connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ensure media artifact schema is present in the SQLite database."
    )
    parser.add_argument(
        "--db",
        default="/Volumes/Tikbalang2TB/Users/tikbalang/Desktop/anthonys_musings.db",
        help="Path to the SQLite database (default: %(default)s)",
    )
    args = parser.parse_args()

    db_path = Path(args.db).expanduser().resolve()
    if not db_path.exists():
        raise SystemExit(f"Database not found at {db_path}")

    ensure_schema(db_path)
    print(f"✅ Media schema ensured for {db_path}")


if __name__ == "__main__":
    main()
