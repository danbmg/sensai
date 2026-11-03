"""Commande python -m sensai.memory.patients : création et suppression hors de l'agent."""
import json

import pytest

from sensai.app import runtime as app_runtime
from sensai.app.runtime import RuntimeOptions, open_runtime
from sensai.core.interfaces import SessionState
from sensai.core.ollama_client import ChatChunk
from sensai.memory.fixtures import seed_demo_patients
from sensai.memory.patients import PatientStore, main
from sensai.memory.sessions import SQLiteSessionStore


def answers(*values):
    """Réponses successives du médecin ; une réponse manquante équivaut à Ctrl+D."""
    queue = list(values)

    def ask(prompt):
        if not queue:
            raise EOFError
        return queue.pop(0)
    return ask


LEFORT = ("Jean Lefort", "12/03/1980", "Aspirine : bronchospasme ; Latex", "", "Diabète de type 2", "")


def test_add_asks_one_field_at_a_time_and_creates_the_record(tmp_path, capsys):
    db = tmp_path / "memory.sqlite3"
    main(["--db", str(db), "add"], ask=answers(*LEFORT, "o"))

    [patient] = PatientStore(db).list_patients()
    assert patient["name"] == "Jean Lefort" and patient["birth_date"] == "1980-03-12"
    assert patient["allergies"] == ["Aspirine : bronchospasme", "Latex"]
    assert patient["medical_history"] == ["Diabète de type 2"] and patient["notes"] == []
    out = capsys.readouterr().out
    assert "pas en arguments" in out and f"Dossier créé : {patient['patient_id']}" in out
    main(["--db", str(db), "list"])
    assert capsys.readouterr().out.split() == [patient["patient_id"], "Jean", "Lefort", "1980-03-12"]


def test_invalid_date_is_asked_again(tmp_path, capsys):
    db = tmp_path / "memory.sqlite3"
    main(["--db", str(db), "add"], ask=answers("Jean Lefort", "1980-13-45", "", "", "", "", "", "o"))
    assert "Date invalide." in capsys.readouterr().out
    assert PatientStore(db).list_patients()[0]["birth_date"] == ""


def test_refusal_or_interruption_creates_nothing(tmp_path, capsys):
    db = tmp_path / "memory.sqlite3"
    main(["--db", str(db), "add"], ask=answers(*LEFORT, "n"))
    assert "aucun dossier créé" in capsys.readouterr().out
    with pytest.raises(SystemExit) as stop:
        main(["--db", str(db), "add"], ask=answers("Jean Lefort", ""))
    assert stop.value.code == 1 and "rien n'a été modifié" in capsys.readouterr().err
    assert PatientStore(db).list_patients() == []


def test_patient_data_cannot_be_passed_as_arguments(tmp_path):
    with pytest.raises(SystemExit):
        main(["--db", str(tmp_path / "memory.sqlite3"), "add", "Jean Lefort"], ask=answers())


def test_homonyms_are_announced_before_creation(tmp_path, capsys):
    db = tmp_path / "memory.sqlite3"
    seed_demo_patients(PatientStore(db))          # contient Camille Martin
    main(["--db", str(db), "add"], ask=answers("Paul Martin", "", "", "", "", "", "o"))
    out = capsys.readouterr().out
    assert "« Martin » seul ne sera plus pseudonymisé" in out and "exactement" not in out
    main(["--db", str(db), "add"], ask=answers("Camille Martin", "", "", "", "", "", "n"))
    assert "exactement ce nom" in capsys.readouterr().out


class FakeClient:
    replies: list = []

    def __init__(self, model, host, options=None, **kwargs):
        self.model, self.host, self.options, self.timeout = model, host, options or {}, 120
        self.calls = []

    def capabilities(self):
        return ["completion", "tools"]

    def chat_stream(self, messages, tools=None):
        self.calls.append(json.dumps([messages, tools], ensure_ascii=False))
        yield ChatChunk(content=FakeClient.replies.pop(0))
        yield ChatChunk(done=True, prompt_tokens=100, completion_tokens=5)


def test_new_patient_never_reaches_the_model_in_clear(tmp_path, monkeypatch):
    monkeypatch.setattr(app_runtime, "OllamaClient", FakeClient)
    config = tmp_path / "config.toml"
    config.write_text('[model]\nname = "qwen2.5:3b"\n[assistant]\nsystem_prompt = "Tu es Sensai."\n'
                      f'[logging]\nenabled = true\ndirectory = "{tmp_path / "logs"}"\n', encoding="utf-8")
    db = tmp_path / "memory.sqlite3"
    options = RuntimeOptions(config=str(config), db=db, demo=True)
    FakeClient.replies = ["Je n'ai pas ce dossier.", "[PATIENT_1] est allergique à l'aspirine."]
    with open_runtime(options) as runtime:
        # Consultation ouverte AVANT la création : le coffre est relu à chaque tour.
        dupont = runtime.open_consultation(patient="demo-dupont")
        main(["--db", str(db), "add"], ask=answers(*LEFORT, "o"))
        list(dupont.ask("Jean Lefort, né le 12/03/1980, tousse. Lefort peut-il prendre de l'aspirine ?",
                        lambda *args: False))
        lefort = runtime.open_consultation(patient="Jean Lefort")
        events = list(lefort.ask("Quelles allergies sont enregistrées ?", lambda *args: False))

        sent = "\n".join(runtime.client.calls)
        assert "Lefort" not in sent and "1980" not in sent
        assert "Patient : [PATIENT_1]" in sent and "Date de naissance : [NAISSANCE_1]" in sent
        assert "Aspirine : bronchospasme" in sent            # le contenu médical reste lisible
        shown = "".join(event.data for event in events if event.type == "token")
        assert shown == "Jean Lefort est allergique à l'aspirine."   # le médecin lit le vrai nom
        logs = "".join(path.read_text() for path in (tmp_path / "logs").glob("*.jsonl"))
        assert "Lefort" not in logs and "1980" not in logs


def test_delete_removes_record_conversations_and_identity_everywhere(tmp_path, capsys):
    db = tmp_path / "memory.sqlite3"
    patients, sessions = PatientStore(db), SQLiteSessionStore(db)
    seed_demo_patients(patients)
    lefort = patients.create_patient("Jean Lefort", "1980-03-12", allergies=["Aspirine"])
    sessions.save("consultation-lefort", SessionState(history=[{"role": "user", "content": "[PATIENT_1] ?"}],
                                                      pii_map={"[PATIENT_1]": "Jean Lefort"}))
    sessions.save_context("consultation-lefort", {"patient_id": lefort["patient_id"]})
    dupont_history = [{"role": "user", "content": "[PATIENT_1] connaît [PATIENT_2], né le [NAISSANCE_1]."}]
    sessions.save("consultation-dupont", SessionState(history=dupont_history, pii_map={
        "[PATIENT_1]": "Jeanne Dupont", "[PATIENT_2]": "M. Lefort", "[NAISSANCE_1]": "12/03/1980"}))
    sessions.save_context("consultation-dupont", {"patient_id": "demo-dupont"})

    main(["--db", str(db), "delete"], ask=answers("Jean Lefort", "o"))

    out = capsys.readouterr().out
    assert "supprimées aussi : 1" in out and "Autres conversations" in out and "Dossier supprimé" in out
    assert "Jean Lefort" not in [patient["name"] for patient in patients.list_patients()]
    assert sessions.list_sessions() == ["consultation-dupont"]
    assert sessions.load_context("consultation-lefort") == {}
    dupont = sessions.load("consultation-dupont")
    assert dupont.pii_map == {"[PATIENT_1]": "Jeanne Dupont"} and dupont.history == dupont_history


def test_delete_refused_unknown_or_ambiguous_changes_nothing(tmp_path, capsys):
    db = tmp_path / "memory.sqlite3"
    patients = PatientStore(db)
    patients.create_patient("Jean Lefort")
    main(["--db", str(db), "delete"], ask=answers("Jean Lefort", "n"))
    assert "rien n'a été modifié" in capsys.readouterr().out
    with pytest.raises(SystemExit) as stop:
        main(["--db", str(db), "delete"], ask=answers("Paul Inconnu"))
    assert stop.value.code == 1 and "aucun dossier ne correspond" in capsys.readouterr().err
    patients.create_patient("Jean Lefort")
    with pytest.raises(SystemExit):
        main(["--db", str(db), "delete"], ask=answers("Jean Lefort"))
    assert "plusieurs dossiers portent ce nom" in capsys.readouterr().err
    assert len(patients.list_patients()) == 2
