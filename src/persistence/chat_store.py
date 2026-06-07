"""SQLite fallback storage for chat messages.
Not used yet – placeholder for future implementation.
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "chat_store.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            timestamp TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()

init_db()
