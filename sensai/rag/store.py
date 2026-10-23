"""Index vectoriel SQLite : documents publics et vecteurs normalisés float32."""
from dataclasses import dataclass
from datetime import date, datetime, timezone
import json
from pathlib import Path

import numpy as np

from sensai.memory.database import SQLiteDatabase
from sensai.rag.documents import Chunk, PublicDocument


class IndexError(RuntimeError):
    """Index absent, incompatible ou corrompu."""


@dataclass(frozen=True)
class Filters:
    publisher: str | None = None
    tags: tuple[str, ...] = ()
    since: str = ""
    until: str = ""

    def validate(self):
        if not isinstance(self.tags, (list, tuple)):
            raise ValueError("Les étiquettes doivent être une liste de textes.")
        if self.publisher is not None and self.publisher not in {"ANSM", "HAS"}:
            raise ValueError("Éditeur attendu : ANSM ou HAS.")
        for value in (self.since, self.until):
            if value:
                if date.fromisoformat(value).isoformat() != value:
                    raise ValueError("Date attendue : YYYY-MM-DD.")
        if self.since and self.until and self.since > self.until:
            raise ValueError("La date de début dépasse la date de fin.")
        if any(not isinstance(tag, str) or not tag.strip() for tag in self.tags):
            raise ValueError("Étiquettes invalides.")


class VectorStore(SQLiteDatabase):
    def __init__(self, path: str | Path):
        super().__init__(path)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS rag_documents (
                    document_id TEXT PRIMARY KEY, title TEXT NOT NULL,
                    source TEXT NOT NULL, publisher TEXT NOT NULL, document_date TEXT NOT NULL,
                    tags TEXT NOT NULL, fingerprint TEXT NOT NULL, model TEXT NOT NULL,
                    dimension INTEGER NOT NULL, indexed_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS rag_chunks (
                    chunk_id TEXT PRIMARY KEY, document_id TEXT NOT NULL,
                    page INTEGER NOT NULL, position INTEGER NOT NULL,
                    start INTEGER NOT NULL, end INTEGER NOT NULL,
                    text TEXT NOT NULL, vector BLOB NOT NULL,
                    FOREIGN KEY(document_id) REFERENCES rag_documents(document_id));
                CREATE INDEX IF NOT EXISTS rag_chunks_document ON rag_chunks(document_id);
            """)

    def is_current(self, document_id: str, fingerprint: str) -> bool:
        with self.connect() as db:
            row = db.execute("SELECT fingerprint FROM rag_documents WHERE document_id=?", (document_id,)).fetchone()
        return bool(row and row[0] == fingerprint)

    def replace_document(self, document: PublicDocument, chunks: list[Chunk], vectors, model: str, fingerprint: str):
        document.validate()
        array = np.asarray(vectors, dtype=np.float32)
        if not chunks or array.ndim != 2 or len(array) != len(chunks) or array.shape[1] == 0:
            raise ValueError("Un vecteur de même dimension est attendu pour chaque extrait.")
        norms = np.linalg.norm(array, axis=1)
        if not np.isfinite(array).all() or not np.isfinite(norms).all() or np.any(norms == 0):
            raise ValueError("Les vecteurs doivent être non nuls et finis.")
        if any(chunk.document_id != document.document_id for chunk in chunks):
            raise ValueError("Extrait associé à un autre document.")
        array = array / norms[:, None]
        with self.connect() as db:
            other = db.execute("SELECT model, dimension FROM rag_documents WHERE document_id != ? LIMIT 1",
                               (document.document_id,)).fetchone()
            if other and (other["model"] != model or other["dimension"] != array.shape[1]):
                raise IndexError("Modèle ou dimension différents : utilisez un autre index ou réindexez tout le corpus.")
            # Les anciennes données ne sont supprimées qu'une fois les nouveaux vecteurs disponibles.
            db.execute("DELETE FROM rag_chunks WHERE document_id=?", (document.document_id,))
            db.execute("DELETE FROM rag_documents WHERE document_id=?", (document.document_id,))
            db.execute("INSERT INTO rag_documents VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                       (document.document_id, document.title, document.source, document.publisher,
                        document.document_date, json.dumps(document.tags, ensure_ascii=False), fingerprint,
                        model, array.shape[1], datetime.now(timezone.utc).isoformat()))
            db.executemany("INSERT INTO rag_chunks VALUES (?, ?, ?, ?, ?, ?, ?, ?)", [
                (chunk.chunk_id, chunk.document_id, chunk.page, chunk.position, chunk.start, chunk.end,
                 chunk.text, vector.astype("<f4").tobytes()) for chunk, vector in zip(chunks, array)
            ])

    def list_documents(self) -> list[dict]:
        with self.connect() as db:
            rows = db.execute("""SELECT d.*, count(c.chunk_id) AS chunks FROM rag_documents d
                LEFT JOIN rag_chunks c USING(document_id) GROUP BY d.document_id ORDER BY title""").fetchall()
        documents = []
        for row in rows:
            value = dict(row)
            value["tags"] = json.loads(value["tags"])
            documents.append(value)
        return documents

    def remove_document(self, document_id: str):
        with self.connect() as db:
            db.execute("DELETE FROM rag_chunks WHERE document_id=?", (document_id,))
            result = db.execute("DELETE FROM rag_documents WHERE document_id=?", (document_id,))
            if not result.rowcount:
                raise IndexError(f"Document inconnu : {document_id}")

    def candidates(self, filters: Filters | None = None) -> list[dict]:
        filters = filters or Filters()
        filters.validate()
        clauses, parameters = [], []
        if filters.publisher:
            clauses.append("d.publisher=?")
            parameters.append(filters.publisher)
        if filters.since:
            clauses.append("d.document_date>=?")
            parameters.append(filters.since)
        if filters.until:
            clauses.append("d.document_date!='' AND d.document_date<=?")
            parameters.append(filters.until)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self.connect() as db:
            rows = db.execute("""SELECT c.*, d.title, d.source, d.publisher, d.document_date,
                d.tags, d.model, d.dimension FROM rag_chunks c JOIN rag_documents d USING(document_id)"""
                              + where + " ORDER BY chunk_id", parameters).fetchall()
        candidates = []
        for row in rows:
            value = dict(row)
            value["tags"] = json.loads(value["tags"])
            if not set(tag.casefold() for tag in filters.tags).issubset(tag.casefold() for tag in value["tags"]):
                continue
            value["vector"] = np.frombuffer(value["vector"], dtype="<f4")
            if len(value["vector"]) != value["dimension"] or not np.isfinite(value["vector"]).all():
                raise IndexError("Vecteur corrompu dans l'index ; réindexez le document.")
            candidates.append(value)
        return candidates
