"""Démonstration M3/M1 autonome : python3 -m sensai.memory.demo."""
import argparse
from pathlib import Path
from tempfile import TemporaryDirectory

from sensai.core.interfaces import SessionState
from sensai.memory.fixtures import seed_demo_patients
from sensai.memory.patients import PatientStore
from sensai.memory.sessions import SQLiteSessionStore


def demonstrate(path: Path) -> None:
    patients = PatientStore(path)
    seed_demo_patients(patients)
    print("DÉMO LOCALE — patients entièrement fictifs, sans appel au modèle")
    print(f"SQLite : {path}")
    print(f"Patients disponibles : {len(patients.list_patients())}")
    patient = patients.find_patients("Dupont")[0]
    print(f"Dossier : {patient['name']} ({patient['patient_id']})")
    print(f"Allergies : {'; '.join(patient['allergies'])}")
    print(f"Traitements : {'; '.join(patient['treatments'])}")

    # Appel direct au stockage, pour montrer le CRUD ; aucune validation LLM simulée.
    note = "Démonstration M3 : allergie à la pénicilline consignée dans le dossier fictif."
    patients.add_patient_note(patient["patient_id"], note)
    reopened = PatientStore(path)
    print(f"Note relue après réouverture : {reopened.get_patient(patient['patient_id'])['notes'][-1]}")

    sessions = SQLiteSessionStore(path)
    state = SessionState(
        history=[{"role": "user", "content": "Quelles allergies pour [PATIENT_1] ?"},
                 {"role": "assistant", "content": "Dossier fictif : allergie à la pénicilline."}],
        pii_map={"[PATIENT_1]": "Jeanne Dupont"})
    sessions.save("demo-session", state)
    restored = SQLiteSessionStore(path).load("demo-session")
    print(f"Session reprise : {len(restored.history)} messages, coffre PII conservé : {restored.pii_map == state.pii_map}")
    print("Cette démo vérifie le stockage. Pour le chatbot intégré : python -m sensai --demo --mcp")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, help="conserver la base fictive dans ce fichier")
    args = parser.parse_args()
    if args.db:
        demonstrate(args.db)
    else:
        with TemporaryDirectory(prefix="sensai-demo-") as directory:
            demonstrate(Path(directory) / "demo.sqlite3")


if __name__ == "__main__":
    main()
