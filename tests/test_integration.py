"""Parcours intégré avec SQLite, protections, outils et un vrai serveur MCP local."""
import copy

import pytest

from sensai import cli
from sensai.core.interfaces import PSEUDONYM_RE, SessionState
from sensai.core.ollama_client import ChatChunk, OllamaClient, OllamaError
from sensai.core.pipeline import Pipeline, _DisplayBuffer
from sensai.guardrails.input_guardrail import SensaiInputGuard
from sensai.guardrails.output_guardrail import SensaiOutputGuard
from sensai.guardrails.pii_vault import SensaiPIIVault
from sensai.memory.context import PatientContext
from sensai.memory.fixtures import seed_demo_patients
from sensai.memory.patients import PatientStore
from sensai.memory.sessions import SQLiteSessionStore
from sensai.runtime import medical_tools


@pytest.fixture
def stores(tmp_path):
    path = tmp_path / "demo.sqlite3"
    patients, sessions = PatientStore(path), SQLiteSessionStore(path)
    seed_demo_patients(patients)
    return patients, sessions


def test_patient_aliases_dates_addresses_and_phone_stream(stores):
    patients, _ = stores
    vault = SensaiPIIVault(patients=patients.list_patients())
    text = "Mme Dupont, Jeanne Dupont, née le 1958-03-12. Adresse : 3 rue des Lilas. Tél : 0612345678"
    masked = vault.mask(text)
    assert "Dupont" not in masked and "1958" not in masked and "Lilas" not in masked
    assert masked.count("[PATIENT_1]") == 2
    assert "[TEL_1]" in masked
    assert all(PSEUDONYM_RE.fullmatch(value) for value in vault.export())
    assert vault.mask(masked) == masked
    assert vault.mask("PATIENT_1") == "[PATIENT_1]"
    assert vault.reveal_args({"patient": vault.mask("PATIENT_1")}) == {"patient": "Jeanne Dupont"}
    buffer = _DisplayBuffer(vault.reveal)
    assert buffer.feed("[TE") == ""
    assert buffer.feed("L_1]") == "0612345678"
    restored = SensaiPIIVault(vault.export())
    assert restored.reveal("[PATIENT_1]") == "Jeanne Dupont"


def test_context_reads_current_patient_without_exposing_others(stores):
    patients, _ = stores
    context = PatientContext(patients)
    assert context.provide("", "", "s") == []
    context.select("demo-dupont")
    patients.add_patient_note("demo-dupont", "Nouvelle note")
    text = context.provide("", "", "s")[0]["content"]
    assert "Nouvelle note" in text and "Pénicilline" in text and "SQLite" in text
    assert "Bernard" not in text


class FakeModel:
    model, host, timeout = "fake", "http://localhost:11434", 120

    def __init__(self):
        self.calls = []

    def chat_stream(self, messages, tools=None):
        self.calls.append(copy.deepcopy(messages))
        if len(self.calls) == 1:
            yield ChatChunk(tool_calls=[{"function": {"name": "add_patient_note", "arguments": {
                "patient": "[PATIENT_1]", "note": "Allergie à la pénicilline consignée."}}}])
        else:
            yield ChatChunk(content="Note ajoutée pour [PATIENT_1].", done=True)


@pytest.mark.parametrize("use_mcp", [False, True], ids=["local", "mcp-stdio"])
@pytest.mark.parametrize("approved", [False, True], ids=["refused", "approved"])
def test_pipeline_patient_note_confirmation_and_persistence(stores, use_mcp, approved):
    patients, sessions = stores
    context = PatientContext(patients)
    context.select("demo-dupont")
    model, confirmations = FakeModel(), []
    original_notes = patients.get_patient("demo-dupont")["notes"]
    with medical_tools(patients, use_mcp) as registry:
        assert registry.is_dangerous("add_patient_note")
        assert not registry.is_dangerous("get_patient")
        schema = next(item for item in registry.schemas() if item["function"]["name"] == "add_patient_note")
        assert set(schema["function"]["parameters"]["required"]) == {"patient", "note"}
        error = registry.call("add_patient_note", {"patient": "Jeanne Dupont", "note": '{"type":"string"}'})
        assert error.is_error
        result = registry.call("get_patient", {"patient": "Jeanne Dupont"})
        assert not result.is_error and "Pénicilline" in result.content
        pipeline = Pipeline(model, context=context, sessions=sessions, tools=registry,
                            input_guard=SensaiInputGuard(), output_guard=SensaiOutputGuard(),
                            vault_factory=lambda mapping: SensaiPIIVault(mapping, patients=patients.list_patients()))
        def confirm(call_id, tool, args):
            confirmations.append(args)
            return approved
        events = list(pipeline.run("Ajoute une note pour Mme Dupont", "test", confirm))
    assert events[-1].type == "done"
    assert confirmations[0]["patient"] == "Jeanne Dupont"
    assert "Jeanne Dupont" not in str(model.calls)
    state = SQLiteSessionStore(sessions.path).load("test")
    assert "Dupont" not in str(state.history)
    assert state.pii_map["[PATIENT_1]"] == "Jeanne Dupont"
    notes = patients.get_patient("demo-dupont")["notes"]
    assert len(notes) == len(original_notes) + int(approved)


def test_malformed_tool_and_storage_failure_do_not_crash(stores):
    patients, sessions = stores
    model = FakeModel()
    def malformed(messages, tools=None):
        if not model.calls:
            model.calls.append(messages)
            yield ChatChunk(tool_calls=[{"function": {"name": "add_patient_note", "arguments": "bad"}}])
        else:
            yield ChatChunk(content="Arguments invalides", done=True)
    model.chat_stream = malformed
    with medical_tools(patients) as registry:
        events = list(Pipeline(model, sessions=sessions, tools=registry).run("Note", "s", lambda *args: True))
    assert any(event.type == "error" for event in events)
    assert len(patients.get_patient("demo-dupont")["notes"]) == 1
    class BrokenContext:
        def provide(self, *args):
            raise ValueError("Patient indisponible")
    events = list(Pipeline(model, context=BrokenContext()).run("Question", "s", lambda *args: True))
    assert events[-1].type == "error"


def test_note_schema_is_rejected(stores):
    patients, _ = stores
    with medical_tools(patients) as registry:
        result = registry.call("add_patient_note", {"patient": "demo-dupont", "note": '{"type":"string"}'})
    assert result.is_error
    assert len(patients.get_patient("demo-dupont")["notes"]) == 1


def test_resume_cli_session_and_manual_note(stores, monkeypatch, capsys):
    patients, sessions = stores
    sessions.save("reprise", SessionState(history=[{"role": "user", "content": "Premier tour"}]))
    calls = []
    class Client:
        model, host, timeout = "fake", "local", 120
        def __init__(self, *args, **kwargs): pass
        def capabilities(self): return ["tools"]
        def chat_stream(self, messages, tools=None):
            calls.append(messages)
            yield ChatChunk(content="Allergie à la pénicilline.", done=True)
    monkeypatch.setattr(cli, "OllamaClient", Client)
    lines = iter(["Quelles allergies ?", "/note Note manuelle fictive", "o", "/dossier", "/quit"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(lines))
    cli.main(["--db", str(patients.path), "--session", "reprise", "--patient", "demo-dupont"])
    assert any(message["content"] == "Premier tour" for message in calls[0])
    assert patients.get_patient("demo-dupont")["notes"][-1] == "Note manuelle fictive"
    assert len(sessions.load("reprise").history) == 3
    assert "Note manuelle fictive" in capsys.readouterr().out


def test_list_sessions_does_not_require_ollama(stores, capsys):
    _, sessions = stores
    sessions.save("offline", SessionState())
    cli.main(["--db", str(sessions.path), "--list-sessions"])
    assert "offline" in capsys.readouterr().out


def test_reading_context_does_not_request_unnecessary_tools(stores):
    patients, sessions = stores
    context = PatientContext(patients)
    context.select("demo-dupont")
    captured = []
    class Model:
        model = "fake"
        def chat_stream(self, messages, tools=None):
            captured.append(tools)
            yield ChatChunk(content="Allergie à la pénicilline.", done=True)
    with medical_tools(patients) as registry:
        pipeline = Pipeline(Model(), context=context, sessions=sessions, tools=registry)
        events = list(pipeline.run("Quelles allergies ?", "s", lambda *args: False,
                                   tool_names=cli._requested_tools("Quelles allergies ?")))
    assert captured == [None] and events[-1].type == "done"
    assert cli._requested_tools("Ajoute une note au dossier") == {"add_patient_note"}


def test_invalid_or_incomplete_ollama_stream_is_reported(monkeypatch):
    class Response:
        status_code = 200
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def raise_for_status(self): pass
        def iter_lines(self):
            yield b'{"message":{"content":"partial"},"done":false}'
    monkeypatch.setattr("sensai.core.ollama_client.requests.post", lambda *args, **kwargs: Response())
    with pytest.raises(OllamaError, match="interrompu"):
        list(OllamaClient("fake").chat_stream([]))
