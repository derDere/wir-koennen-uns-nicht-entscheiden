"""
SQLite database module for session persistence.
"""

import sqlite3
import json
import time
import threading
from pathlib import Path
from typing import Optional
from contextlib import contextmanager

DATABASE_PATH = Path("sessions.db")
SESSION_EXPIRY_DAYS = 7
SESSION_EXPIRY_SECONDS = SESSION_EXPIRY_DAYS * 24 * 60 * 60

_local = threading.local()


def get_connection() -> sqlite3.Connection:
    """Get a thread-local database connection."""
    if not hasattr(_local, "connection"):
        _local.connection = sqlite3.connect(str(DATABASE_PATH), check_same_thread=False)
        _local.connection.row_factory = sqlite3.Row
    return _local.connection


@contextmanager
def get_cursor():
    """Context manager for database cursor with auto-commit."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        yield cursor
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()


def init_database():
    """Initialize the database schema."""
    with get_cursor() as cursor:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                creator_id TEXT NOT NULL,
                phase TEXT NOT NULL DEFAULT 'adding',
                created_at REAL NOT NULL,
                last_activity REAL NOT NULL,
                excluded_items TEXT DEFAULT '[]',
                restart_votes TEXT DEFAULT '[]'
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                member_id TEXT NOT NULL,
                items TEXT DEFAULT '[]',
                is_ready INTEGER DEFAULT 0,
                accepted_items TEXT DEFAULT '[]',
                is_observer INTEGER DEFAULT 0,
                last_seen REAL NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE,
                UNIQUE(session_id, member_id)
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_members_session ON members(session_id)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_sessions_activity ON sessions(last_activity)
        """)


def cleanup_expired_sessions():
    """Remove sessions that have been inactive for more than 7 days."""
    cutoff = time.time() - SESSION_EXPIRY_SECONDS
    with get_cursor() as cursor:
        cursor.execute("DELETE FROM members WHERE session_id IN (SELECT session_id FROM sessions WHERE last_activity < ?)", (cutoff,))
        cursor.execute("DELETE FROM sessions WHERE last_activity < ?", (cutoff,))


def session_exists(session_id: str) -> bool:
    """Check if a session exists."""
    with get_cursor() as cursor:
        cursor.execute("SELECT 1 FROM sessions WHERE session_id = ?", (session_id,))
        return cursor.fetchone() is not None


def create_session(session_id: str, creator_id: str) -> bool:
    """Create a new session. Returns True if successful."""
    now = time.time()
    try:
        with get_cursor() as cursor:
            cursor.execute(
                "INSERT INTO sessions (session_id, creator_id, phase, created_at, last_activity) VALUES (?, ?, 'adding', ?, ?)",
                (session_id, creator_id, now, now)
            )
            cursor.execute(
                "INSERT INTO members (session_id, member_id, last_seen) VALUES (?, ?, ?)",
                (session_id, creator_id, now)
            )
        return True
    except sqlite3.IntegrityError:
        return False


def get_session(session_id: str) -> Optional[dict]:
    """Get session data."""
    with get_cursor() as cursor:
        cursor.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,))
        row = cursor.fetchone()
        if row:
            return {
                "session_id": row["session_id"],
                "creator_id": row["creator_id"],
                "phase": row["phase"],
                "created_at": row["created_at"],
                "last_activity": row["last_activity"],
                "excluded_items": json.loads(row["excluded_items"]),
                "restart_votes": json.loads(row["restart_votes"])
            }
    return None


def update_session_activity(session_id: str):
    """Update the last activity timestamp."""
    with get_cursor() as cursor:
        cursor.execute(
            "UPDATE sessions SET last_activity = ? WHERE session_id = ?",
            (time.time(), session_id)
        )


def set_session_phase(session_id: str, phase: str):
    """Set the session phase."""
    with get_cursor() as cursor:
        cursor.execute(
            "UPDATE sessions SET phase = ?, last_activity = ? WHERE session_id = ?",
            (phase, time.time(), session_id)
        )


def get_session_creator(session_id: str) -> Optional[str]:
    """Get the creator ID of a session."""
    with get_cursor() as cursor:
        cursor.execute("SELECT creator_id FROM sessions WHERE session_id = ?", (session_id,))
        row = cursor.fetchone()
        return row["creator_id"] if row else None


def add_member(session_id: str, member_id: str, is_observer: bool = False) -> bool:
    """Add a member to a session. Returns True if successful."""
    now = time.time()
    try:
        with get_cursor() as cursor:
            cursor.execute(
                "INSERT INTO members (session_id, member_id, is_observer, last_seen) VALUES (?, ?, ?, ?)",
                (session_id, member_id, 1 if is_observer else 0, now)
            )
            cursor.execute(
                "UPDATE sessions SET last_activity = ? WHERE session_id = ?",
                (now, session_id)
            )
        return True
    except sqlite3.IntegrityError:
        return False


def get_member(session_id: str, member_id: str) -> Optional[dict]:
    """Get member data."""
    with get_cursor() as cursor:
        cursor.execute(
            "SELECT * FROM members WHERE session_id = ? AND member_id = ?",
            (session_id, member_id)
        )
        row = cursor.fetchone()
        if row:
            return {
                "member_id": row["member_id"],
                "items": json.loads(row["items"]),
                "is_ready": bool(row["is_ready"]),
                "accepted_items": json.loads(row["accepted_items"]),
                "is_observer": bool(row["is_observer"]),
                "last_seen": row["last_seen"]
            }
    return None


def get_all_members(session_id: str) -> list:
    """Get all members in a session."""
    with get_cursor() as cursor:
        cursor.execute("SELECT * FROM members WHERE session_id = ?", (session_id,))
        rows = cursor.fetchall()
        return [
            {
                "member_id": row["member_id"],
                "items": json.loads(row["items"]),
                "is_ready": bool(row["is_ready"]),
                "accepted_items": json.loads(row["accepted_items"]),
                "is_observer": bool(row["is_observer"]),
                "last_seen": row["last_seen"]
            }
            for row in rows
        ]


def get_active_members(session_id: str) -> list:
    """Get all non-observer members in a session."""
    members = get_all_members(session_id)
    return [m for m in members if not m["is_observer"]]


def update_member_items(session_id: str, member_id: str, items: list):
    """Update a member's items."""
    with get_cursor() as cursor:
        cursor.execute(
            "UPDATE members SET items = ?, last_seen = ? WHERE session_id = ? AND member_id = ?",
            (json.dumps(items), time.time(), session_id, member_id)
        )
        cursor.execute(
            "UPDATE sessions SET last_activity = ? WHERE session_id = ?",
            (time.time(), session_id)
        )


def set_member_ready(session_id: str, member_id: str, is_ready: bool):
    """Set a member's ready status."""
    with get_cursor() as cursor:
        cursor.execute(
            "UPDATE members SET is_ready = ?, last_seen = ? WHERE session_id = ? AND member_id = ?",
            (1 if is_ready else 0, time.time(), session_id, member_id)
        )
        cursor.execute(
            "UPDATE sessions SET last_activity = ? WHERE session_id = ?",
            (time.time(), session_id)
        )


def update_member_accepted_items(session_id: str, member_id: str, accepted_items: list):
    """Update a member's accepted items."""
    with get_cursor() as cursor:
        cursor.execute(
            "UPDATE members SET accepted_items = ?, last_seen = ? WHERE session_id = ? AND member_id = ?",
            (json.dumps(accepted_items), time.time(), session_id, member_id)
        )
        cursor.execute(
            "UPDATE sessions SET last_activity = ? WHERE session_id = ?",
            (time.time(), session_id)
        )


def update_member_last_seen(session_id: str, member_id: str):
    """Update a member's last seen timestamp."""
    with get_cursor() as cursor:
        cursor.execute(
            "UPDATE members SET last_seen = ? WHERE session_id = ? AND member_id = ?",
            (time.time(), session_id, member_id)
        )


def reset_all_ready_status(session_id: str):
    """Reset all members' ready status to False."""
    with get_cursor() as cursor:
        cursor.execute(
            "UPDATE members SET is_ready = 0 WHERE session_id = ?",
            (session_id,)
        )


def reset_all_accepted_items(session_id: str):
    """Reset all members' accepted items."""
    with get_cursor() as cursor:
        cursor.execute(
            "UPDATE members SET accepted_items = '[]' WHERE session_id = ?",
            (session_id,)
        )


def clear_all_items(session_id: str):
    """Clear all members' items."""
    with get_cursor() as cursor:
        cursor.execute(
            "UPDATE members SET items = '[]' WHERE session_id = ?",
            (session_id,)
        )


def promote_observers(session_id: str):
    """Promote all observers to active members."""
    with get_cursor() as cursor:
        cursor.execute(
            "UPDATE members SET is_observer = 0 WHERE session_id = ?",
            (session_id,)
        )


def remove_member(session_id: str, member_id: str):
    """Remove a member from a session."""
    with get_cursor() as cursor:
        cursor.execute(
            "DELETE FROM members WHERE session_id = ? AND member_id = ?",
            (session_id, member_id)
        )


def get_excluded_items(session_id: str) -> list:
    """Get the list of excluded items (for roll-next)."""
    with get_cursor() as cursor:
        cursor.execute("SELECT excluded_items FROM sessions WHERE session_id = ?", (session_id,))
        row = cursor.fetchone()
        return json.loads(row["excluded_items"]) if row else []


def set_excluded_items(session_id: str, excluded_items: list):
    """Set the list of excluded items."""
    with get_cursor() as cursor:
        cursor.execute(
            "UPDATE sessions SET excluded_items = ? WHERE session_id = ?",
            (json.dumps(excluded_items), session_id)
        )


def clear_excluded_items(session_id: str):
    """Clear the excluded items list."""
    set_excluded_items(session_id, [])


def get_restart_votes(session_id: str) -> list:
    """Get the list of member IDs who voted to restart."""
    with get_cursor() as cursor:
        cursor.execute("SELECT restart_votes FROM sessions WHERE session_id = ?", (session_id,))
        row = cursor.fetchone()
        return json.loads(row["restart_votes"]) if row else []


def add_restart_vote(session_id: str, member_id: str):
    """Add a restart vote from a member."""
    votes = get_restart_votes(session_id)
    if member_id not in votes:
        votes.append(member_id)
        with get_cursor() as cursor:
            cursor.execute(
                "UPDATE sessions SET restart_votes = ? WHERE session_id = ?",
                (json.dumps(votes), session_id)
            )


def clear_restart_votes(session_id: str):
    """Clear all restart votes."""
    with get_cursor() as cursor:
        cursor.execute(
            "UPDATE sessions SET restart_votes = '[]' WHERE session_id = ?",
            (session_id,)
        )


def delete_session(session_id: str):
    """Delete a session and all its members."""
    with get_cursor() as cursor:
        cursor.execute("DELETE FROM members WHERE session_id = ?", (session_id,))
        cursor.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))


# Initialize database on module load
init_database()
