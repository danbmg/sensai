"""Implémentation persistante du contrat SessionStore, sans dépendance à Ollama."""
import json
from pathlib import Path

from sensai.core.interfaces import SessionState
from sensai.memory.database import SQLiteDatabase


class SQLiteSessionStore(SQLiteDatabase):
    def __init__(self, path: str | Path):
        super().__init__(path)
        with self.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                history TEXT NOT NULL,
                pii_map TEXT NOT NULL
            )""")

    def load(self, session_id: str) -> SessionState:
        with self.connect() as db:
            row = db.execute("SELECT history, pii_map FROM sessions WHERE session_id = ?",
                             (session_id,)).fetchone()
        if row is None:
            return SessionState()
        return SessionState(history=json.loads(row["history"]), pii_map=json.loads(row["pii_map"]))

    def save(self, session_id: str, state: SessionState) -> None:
        if not isinstance(session_id, str) or not session_id.strip():
            raise ValueError("session_id doit être un texte non vide.")
        with self.connect() as db:
            db.execute("""INSERT INTO sessions VALUES (?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET history = excluded.history,
                pii_map = excluded.pii_map""",
                       (session_id, json.dumps(state.history, ensure_ascii=False),
                        json.dumps(state.pii_map, ensure_ascii=False)))

    def list_sessions(self) -> list[str]:
        with self.connect() as db:
            return [row["session_id"] for row in db.execute(
                "SELECT session_id FROM sessions ORDER BY session_id")]
