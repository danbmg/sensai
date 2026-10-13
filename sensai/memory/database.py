"""Connexions SQLite locales, fermées après chaque opération."""
import sqlite3
from contextlib import contextmanager
from pathlib import Path


class SQLiteDatabase:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        if str(path) == ":memory:":
            raise ValueError("Utilisez un fichier SQLite pour assurer la persistance.")
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()
