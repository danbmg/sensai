"""API Python CRUD des dossiers patients ; données en clair, exclusivement locales.

La validation du médecin doit être effectuée par le pipeline avant une écriture
déclenchée par un outil. Cette couche de stockage ne demande aucune confirmation.
"""
import json
from pathlib import Path
import uuid

from sensai.memory.database import SQLiteDatabase


class PatientNotFoundError(LookupError):
    """Aucun patient ne correspond à l'identifiant ou au nom exact."""


class AmbiguousPatientError(LookupError):
    """Plusieurs patients portent ce nom : un identifiant est nécessaire."""


class PatientStore(SQLiteDatabase):
    FIELDS = {"name", "birth_date", "allergies", "treatments", "medical_history", "notes"}
    LIST_FIELDS = {"allergies", "treatments", "medical_history", "notes"}

    def __init__(self, path: str | Path):
        super().__init__(path)
        with self.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS patients (
                patient_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                birth_date TEXT NOT NULL,
                allergies TEXT NOT NULL,
                treatments TEXT NOT NULL,
                medical_history TEXT NOT NULL,
                notes TEXT NOT NULL
            )""")

    @classmethod
    def _validate(cls, fields: dict) -> None:
        unknown = fields.keys() - cls.FIELDS
        if unknown:
            raise ValueError(f"Champs inconnus : {', '.join(sorted(unknown))}")
        for key, value in fields.items():
            if key in cls.LIST_FIELDS:
                if not isinstance(value, list) or any(
                    not isinstance(item, str) or not item.strip() for item in value
                ):
                    raise ValueError(f"{key} doit être une liste de textes non vides.")
            elif not isinstance(value, str) or (key == "name" and not value.strip()):
                raise ValueError(f"{key} doit être un texte" + (" non vide." if key == "name" else "."))

    @classmethod
    def _decode(cls, row) -> dict:
        patient = dict(row)
        for key in cls.LIST_FIELDS:
            patient[key] = json.loads(patient[key])
        return patient

    def create_patient(self, name: str, birth_date: str = "", *,
                       allergies: list[str] | None = None,
                       treatments: list[str] | None = None,
                       medical_history: list[str] | None = None,
                       notes: list[str] | None = None,
                       patient_id: str | None = None) -> dict:
        fields = dict(name=name, birth_date=birth_date,
                      allergies=[] if allergies is None else allergies,
                      treatments=[] if treatments is None else treatments,
                      medical_history=[] if medical_history is None else medical_history,
                      notes=[] if notes is None else notes)
        self._validate(fields)
        patient_id = uuid.uuid4().hex if patient_id is None else patient_id
        if not isinstance(patient_id, str) or not patient_id.strip():
            raise ValueError("patient_id doit être un texte non vide.")
        with self.connect() as db:
            db.execute("INSERT INTO patients VALUES (?, ?, ?, ?, ?, ?, ?)",
                       [patient_id, name.strip(), birth_date,
                        *[json.dumps(fields[key], ensure_ascii=False)
                          for key in ("allergies", "treatments", "medical_history", "notes")]])
        return self.get_patient(patient_id)

    def get_patient(self, patient_id: str) -> dict:
        with self.connect() as db:
            row = db.execute("SELECT * FROM patients WHERE patient_id = ?", (patient_id,)).fetchone()
        if row is None:
            raise PatientNotFoundError(patient_id)
        return self._decode(row)

    def list_patients(self) -> list[dict]:
        with self.connect() as db:
            rows = db.execute("SELECT * FROM patients ORDER BY name, patient_id").fetchall()
        return [self._decode(row) for row in rows]

    def find_patients(self, name: str) -> list[dict]:
        """Recherche partielle insensible à la casse, sans choisir un patient à la place du médecin."""
        if not isinstance(name, str) or not name.strip():
            raise ValueError("La recherche doit être un texte non vide.")
        query = name.strip().casefold()
        return [patient for patient in self.list_patients() if query in patient["name"].casefold()]

    def resolve_patient(self, reference: str) -> dict:
        """Identifiant ou nom complet exact. Les homonymes déclenchent une erreur."""
        try:
            return self.get_patient(reference)
        except PatientNotFoundError:
            matches = [patient for patient in self.find_patients(reference)
                       if patient["name"].casefold() == reference.strip().casefold()]
        if not matches:
            raise PatientNotFoundError(reference)
        if len(matches) > 1:
            raise AmbiguousPatientError(reference)
        return matches[0]

    def update_patient(self, patient_id: str, **fields) -> dict:
        self._validate(fields)
        if not fields:
            return self.get_patient(patient_id)
        values = [json.dumps(value, ensure_ascii=False) if key in self.LIST_FIELDS
                  else value.strip() if key == "name" else value for key, value in fields.items()]
        # Les noms de colonnes proviennent exclusivement de FIELDS, après validation.
        assignments = ", ".join(f"{key} = ?" for key in fields)
        with self.connect() as db:
            result = db.execute(f"UPDATE patients SET {assignments} WHERE patient_id = ?",
                                [*values, patient_id])
            if result.rowcount == 0:
                raise PatientNotFoundError(patient_id)
        return self.get_patient(patient_id)

    def add_patient_note(self, reference: str, note: str) -> dict:
        self._validate({"notes": [note]})
        patient_id = self.resolve_patient(reference)["patient_id"]
        with self.connect() as db:
            # Verrou avant lecture pour ne pas perdre une note ajoutée simultanément.
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT notes FROM patients WHERE patient_id = ?", (patient_id,)).fetchone()
            if row is None:
                raise PatientNotFoundError(patient_id)
            notes = json.loads(row["notes"])
            notes.append(note.strip())
            db.execute("UPDATE patients SET notes = ? WHERE patient_id = ?",
                       (json.dumps(notes, ensure_ascii=False), patient_id))
        return self.get_patient(patient_id)

    def delete_patient(self, patient_id: str) -> None:
        with self.connect() as db:
            result = db.execute("DELETE FROM patients WHERE patient_id = ?", (patient_id,))
            if result.rowcount == 0:
                raise PatientNotFoundError(patient_id)
