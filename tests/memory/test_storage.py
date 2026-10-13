"""Tests du stockage réel, exécutables avec unittest ou pytest, sans serveur Ollama."""
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from sensai.core.interfaces import SessionState
from sensai.memory.fixtures import seed_demo_patients
from sensai.memory.patients import AmbiguousPatientError, PatientNotFoundError, PatientStore
from sensai.memory.sessions import SQLiteSessionStore


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "nested" / "memory.sqlite3"
        self.patients = PatientStore(self.path)

    def test_crud_survives_reopening(self):
        patient = self.patients.create_patient("Patient fictif", allergies=["Latex"])
        patient_id = patient["patient_id"]
        self.patients.update_patient(patient_id, treatments=["Traitement fictif"],
                                     medical_history=["Antécédent fictif"])
        self.patients.add_patient_note(patient_id, "Première note")
        self.patients.add_patient_note(patient_id, "Deuxième note")
        reopened = PatientStore(self.path)
        restored = reopened.get_patient(patient_id)
        self.assertEqual(restored["allergies"], ["Latex"])
        self.assertEqual(restored["treatments"], ["Traitement fictif"])
        self.assertEqual(restored["medical_history"], ["Antécédent fictif"])
        self.assertEqual(restored["notes"], ["Première note", "Deuxième note"])
        reopened.delete_patient(patient_id)
        with self.assertRaises(PatientNotFoundError):
            self.patients.get_patient(patient_id)

    def test_missing_patients_raise_on_every_mutation(self):
        operations = [lambda: self.patients.get_patient("missing"),
                      lambda: self.patients.update_patient("missing", notes=[]),
                      lambda: self.patients.delete_patient("missing"),
                      lambda: self.patients.add_patient_note("missing", "Note")]
        for operation in operations:
            with self.subTest(operation=operation), self.assertRaises(PatientNotFoundError):
                operation()

    def test_validation_rejects_invalid_updates_without_modifying_record(self):
        patient = self.patients.create_patient("Patient fictif")
        for fields in ({"name": " "}, {"notes": "texte"}, {"allergies": [1]},
                       {"notes": [""]},
                       {"name = 'malicious'": "value"}):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                self.patients.update_patient(patient["patient_id"], **fields)
        self.assertEqual(self.patients.get_patient(patient["patient_id"]), patient)
        with self.assertRaises(ValueError):
            self.patients.create_patient("Patient fictif", allergies="latex")

    def test_concurrent_note_additions_are_preserved(self):
        patient = self.patients.create_patient("Patient fictif")
        notes = [f"Note {index}" for index in range(8)]
        def add(note):
            PatientStore(self.path).add_patient_note(patient["patient_id"], note)
        with ThreadPoolExecutor(max_workers=4) as executor:
            list(executor.map(add, notes))
        self.assertCountEqual(self.patients.get_patient(patient["patient_id"])["notes"], notes)

    def test_homonyms_require_id_and_partial_name_cannot_modify_record(self):
        first = self.patients.create_patient("Jeanne Dupont")
        self.patients.create_patient("Jeanne Dupont")
        with self.assertRaises(AmbiguousPatientError):
            self.patients.add_patient_note("Jeanne Dupont", "Ne doit pas être écrite")
        with self.assertRaises(PatientNotFoundError):
            self.patients.add_patient_note("Dupont", "Ne doit pas être écrite")
        self.assertEqual(self.patients.get_patient(first["patient_id"])["notes"], [])
        self.patients.add_patient_note(first["patient_id"], "Patient identifié")
        self.assertEqual(self.patients.get_patient(first["patient_id"])["notes"], ["Patient identifié"])

    def test_search_is_case_insensitive_and_sql_metacharacters_are_literal(self):
        self.patients.create_patient("Jeanne Dupont")
        self.assertEqual(len(self.patients.find_patients("DUPONT")), 1)
        self.assertEqual(self.patients.find_patients("' OR 1=1 --"), [])
        with self.assertRaises(PatientNotFoundError):
            self.patients.get_patient("' OR 1=1 --")

    def test_exact_name_resolves_to_id(self):
        patient = self.patients.create_patient("Jeanne Dupont")
        self.assertEqual(self.patients.resolve_patient(" jeanne DUPONT "), patient)

    def test_seed_is_idempotent_and_preserves_changes(self):
        seed_demo_patients(self.patients)
        self.patients.add_patient_note("demo-dupont", "Note conservée")
        seed_demo_patients(self.patients)
        self.assertEqual(len(self.patients.list_patients()), 3)
        dupont = self.patients.get_patient("demo-dupont")
        self.assertIn("Pénicilline", dupont["allergies"][0])
        self.assertEqual(dupont["notes"][-1], "Note conservée")

    def test_duplicate_id_does_not_replace_existing_patient(self):
        original = self.patients.create_patient("Premier patient", patient_id="same-id")
        with self.assertRaises(sqlite3.IntegrityError):
            self.patients.create_patient("Autre patient", patient_id="same-id")
        self.assertEqual(self.patients.get_patient("same-id"), original)

    def test_session_restores_history_tool_calls_and_pii_map(self):
        state = SessionState(
            history=[{"role": "user", "content": "Et [PATIENT_1] ?"},
                     {"role": "assistant", "content": "", "tool_calls": [
                         {"function": {"name": "get_patient", "arguments": {"patient": "[PATIENT_1]"}}}]},
                     {"role": "tool", "tool_name": "get_patient", "content": "Allergie : pénicilline"}],
            pii_map={"[PATIENT_1]": "Jeanne Dupont"})
        SQLiteSessionStore(self.path).save("s1", state)
        self.assertEqual(SQLiteSessionStore(self.path).load("s1"), state)
        self.assertEqual(len(self.patients.list_patients()), 0)

    def test_sessions_are_isolated_and_save_replaces_state(self):
        store = SQLiteSessionStore(self.path)
        self.assertEqual(store.load("unknown"), SessionState())
        store.save("s1", SessionState(history=[{"role": "user", "content": "Premier"}]))
        store.save("s2", SessionState(history=[{"role": "user", "content": "Autre"}]))
        loaded = store.load("s1")
        loaded.history.append({"role": "assistant", "content": "Non sauvegardé"})
        self.assertEqual(len(store.load("s1").history), 1)
        store.save("s1", loaded)
        self.assertEqual(store.load("s1"), loaded)
        self.assertEqual(store.load("s2").history[0]["content"], "Autre")
        self.assertEqual(store.list_sessions(), ["s1", "s2"])

    def test_patient_and_session_survive_a_new_process(self):
        seed_demo_patients(self.patients)
        SQLiteSessionStore(self.path).save("persisted", SessionState(
            history=[{"role": "user", "content": "Question [PATIENT_1]"}],
            pii_map={"[PATIENT_1]": "Jeanne Dupont"}))
        code = """
import sys
from sensai.memory.patients import PatientStore
from sensai.memory.sessions import SQLiteSessionStore
assert PatientStore(sys.argv[1]).get_patient('demo-dupont')['name'] == 'Jeanne Dupont'
state = SQLiteSessionStore(sys.argv[1]).load('persisted')
assert state.history[0]['content'] == 'Question [PATIENT_1]'
assert state.pii_map == {'[PATIENT_1]': 'Jeanne Dupont'}
"""
        result = subprocess.run([sys.executable, "-c", code, str(self.path)],
                                cwd=Path(__file__).resolve().parents[2],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
