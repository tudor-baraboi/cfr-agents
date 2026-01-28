"""
SQLite database layer for trial access code management.
Tracks code usage counts and dynamically generated codes.
"""

import aiosqlite
import logging
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

# Database file location (in backend directory)
DB_PATH = Path(__file__).parent.parent / "trial_codes.db"


async def init_db() -> None:
    """Initialize database tables if they don't exist."""
    async with aiosqlite.connect(DB_PATH) as db:
        # Table for tracking usage of all codes (env + generated)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS code_usage (
                code TEXT PRIMARY KEY,
                request_count INTEGER DEFAULT 0,
                first_used_at TIMESTAMP,
                last_used_at TIMESTAMP
            )
        """)
        
        # Table for dynamically generated codes (via admin API)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS generated_codes (
                code TEXT PRIMARY KEY,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_by TEXT
            )
        """)
        
        await db.commit()
        logger.info(f"Database initialized at {DB_PATH}")


async def get_usage(code: str) -> int:
    """Get the current request count for a code. Returns 0 if not tracked yet."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT request_count FROM code_usage WHERE code = ?",
            (code,)
        )
        row = await cursor.fetchone()
        return row[0] if row else 0


async def increment_usage(code: str) -> int:
    """
    Increment the request count for a code.
    Creates the record if it doesn't exist.
    Returns the new count.
    """
    now = datetime.utcnow().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        # Upsert: insert or update
        await db.execute("""
            INSERT INTO code_usage (code, request_count, first_used_at, last_used_at)
            VALUES (?, 1, ?, ?)
            ON CONFLICT(code) DO UPDATE SET
                request_count = request_count + 1,
                last_used_at = ?
        """, (code, now, now, now))
        await db.commit()
        
        # Fetch the new count
        cursor = await db.execute(
            "SELECT request_count FROM code_usage WHERE code = ?",
            (code,)
        )
        row = await cursor.fetchone()
        new_count = row[0] if row else 1
        logger.info(f"Code {code[:8]}... usage incremented to {new_count}")
        return new_count


async def add_generated_code(code: str, created_by: str = "admin") -> None:
    """Add a new dynamically generated code to the database."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO generated_codes (code, created_by) VALUES (?, ?)",
            (code, created_by)
        )
        await db.commit()
        logger.info(f"Generated new code: {code}")


async def is_generated_code(code: str) -> bool:
    """Check if a code was dynamically generated (vs from env vars)."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT 1 FROM generated_codes WHERE code = ?",
            (code,)
        )
        row = await cursor.fetchone()
        return row is not None


async def list_generated_codes() -> list[dict]:
    """List all dynamically generated codes with their usage stats."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT 
                g.code,
                g.created_at,
                g.created_by,
                COALESCE(u.request_count, 0) as request_count,
                u.first_used_at,
                u.last_used_at
            FROM generated_codes g
            LEFT JOIN code_usage u ON g.code = u.code
            ORDER BY g.created_at DESC
        """)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
