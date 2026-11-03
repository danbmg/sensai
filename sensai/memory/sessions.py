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
            db.execute("""CREATE TABLE IF NOT EXISTS session_context (
                session_id TEXT PRIMARY KEY, payload TEXT NOT NULL)""")

    def load_context(self, session_id: str) -> dict:
        """Métadonnées CLI, séparées du contrat SessionState du pipeline."""
        with self.connect() as db:
            row = db.execute("SELECT payload FROM session_context WHERE session_id=?", (session_id,)).fetchone()
        return json.loads(row[0]) if row else {}

    def save_context(self, session_id: str, metadata: dict) -> None:
        if not isinstance(session_id, str) or not session_id.strip():
            raise ValueError("session_id doit être un texte non vide.")
        with self.connect() as db:
            db.execute("""INSERT INTO session_context VALUES (?, ?)
                ON CONFLICT(session_id) DO UPDATE SET payload=excluded.payload""",
                       (session_id, json.dumps(metadata, ensure_ascii=False)))

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

    def forget_patient(self, patient: dict, *, apply: bool = True) -> tuple[list[str], list[str]]:
        """Traces d'un patient : (sessions liées à son dossier, autres sessions dont le coffre le connaît).

        Avec `apply`, les premières sont supprimées et son identité est retirée du coffre des
        autres : leur historique, déjà pseudonymisé, garde [PATIENT_n] sans pouvoir le ré-identifier.
        """
        identity = _identity(patient)
        with self.connect() as db:
            linked = {row["session_id"] for row in db.execute("SELECT session_id, payload FROM session_context")
                      if json.loads(row["payload"]).get("patient_id") == patient["patient_id"]}
            others = {}
            for row in db.execute("SELECT session_id, pii_map FROM sessions"):
                if row["session_id"] in linked:
                    continue
                pii_map = json.loads(row["pii_map"])
                kept = {placeholder: value for placeholder, value in pii_map.items()
                        if not isinstance(value, str) or " ".join(value.split()).casefold() not in identity}
                if len(kept) < len(pii_map):
                    others[row["session_id"]] = kept
            if apply:
                for session_id in linked:
                    db.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
                    db.execute("DELETE FROM session_context WHERE session_id = ?", (session_id,))
                for session_id, kept in others.items():
                    db.execute("UPDATE sessions SET pii_map = ? WHERE session_id = ?",
                               (json.dumps(kept, ensure_ascii=False), session_id))
        return sorted(linked), sorted(others)


CIVILITIES = ("", "mme ", "mme. ", "madame ", "monsieur ", "m. ")


def _identity(patient: dict) -> set[str]:
    """Valeurs sous lesquelles le coffre a pu enregistrer ce patient, casse ignorée.

    Le coffre enregistre le nom complet, la date de naissance, ou « civilité + nom » tel que
    tapé avant la création du dossier. En cas d'homonyme, « Mme Dupont » d'un autre patient est
    aussi retiré : on efface plutôt trop que pas assez.
    """
    name = " ".join(patient["name"].split()).casefold()
    values = {prefix + name for prefix in CIVILITIES}
    values |= {prefix + name.split()[-1] for prefix in CIVILITIES if prefix}
    if date := patient.get("birth_date"):
        values.add(date)
        if len(date) == 10 and date[4] == date[7] == "-":
            values.add(f"{date[8:10]}/{date[5:7]}/{date[:4]}")
    return values
