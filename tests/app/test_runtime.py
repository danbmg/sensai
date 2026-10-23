"""Couche commune CLI/web : assemblage des modules et consultations, avec un faux modèle."""
import json
from pathlib import Path

import pytest

from sensai.app import runtime as app_runtime
from sensai.app.runtime import (ModelUnusable, RuntimeOptions, Settings, StartupError, build_retriever,
                                open_runtime)
from sensai.core.config import ConfigError
from sensai.core.ollama_client import ChatChunk, ModelNotFoundError
from sensai.memory.profiles import DoctorProfile
from sensai.rag.documents import PublicDocument, chunk_pages
from sensai.rag.store import Filters, VectorStore


class FakeClient:
    capabilities_by_model = {"qwen2.5:3b": ["completion", "tools"], "qwen3:4b": ["tools", "thinking"],
                             "tiny": ["completion"]}
    replies: list = []

    def __init__(self, model, host, options=None, **kwargs):
        self.model, self.host, self.options, self.timeout = model, host, options or {}, 120
        self.calls = []

    def capabilities(self):
        if self.model not in self.capabilities_by_model:
            raise ModelNotFoundError(self.model)
        return self.capabilities_by_model[self.model]

    def chat_stream(self, messages, tools=None):
        self.calls.append((messages, tools))
        yield from FakeClient.replies.pop(0)


@pytest.fixture
def options(tmp_path, monkeypatch):
    monkeypatch.setattr(app_runtime, "OllamaClient", FakeClient)
    config = tmp_path / "config.toml"
    config.write_text('[model]\nname = "qwen2.5:3b"\n[assistant]\nsystem_prompt = "Tu es Sensai."\n'
                      f'[logging]\nenabled = true\ndirectory = "{tmp_path / "logs"}"\n', encoding="utf-8")
    return RuntimeOptions(config=str(config), db=tmp_path / "memory.sqlite3", demo=True)


@pytest.fixture
def runtime(options):
    with open_runtime(options) as runtime:
        yield runtime


def answer(text, prompt_tokens=100, completion_tokens=10):
    return [ChatChunk(content=text), ChatChunk(done=True, prompt_tokens=prompt_tokens,
                                               completion_tokens=completion_tokens)]


def confirm_with(answer):
    calls = []

    def confirm(call_id, tool, args):
        calls.append((tool, args))
        return answer
    confirm.calls = calls
    return confirm


# --- Assemblage ---

def test_options_from_environment():
    options = RuntimeOptions.from_env({"SENSAI_DB": "/tmp/x.sqlite3", "SENSAI_DEMO": "1", "SENSAI_MCP": "oui",
                                       "SENSAI_MODEL": "llama3.2:3b"})
    assert (options.db, options.demo, options.mcp, options.model) == (Path("/tmp/x.sqlite3"), True, True, "llama3.2:3b")
    assert RuntimeOptions.from_env({}) == RuntimeOptions()


def test_invalid_config_is_reported(tmp_path):
    with pytest.raises(ConfigError):
        Settings.load(RuntimeOptions(config=str(tmp_path / "absent.toml")))


def test_rag_index_must_be_separate_and_non_empty(options, tmp_path):
    settings = Settings.load(options)
    assert build_retriever(settings, options) == (None, 0)          # index vide : RAG inactif
    with pytest.raises(StartupError, match="séparé"):
        build_retriever(settings, RuntimeOptions(db=options.db, rag_index=options.db))
    path = tmp_path / "notice.txt"
    path.write_text("Amoxicilline : contre-indiquée en cas d'allergie aux pénicillines.", encoding="utf-8")
    document = PublicDocument(path, "Notice", "https://ansm.sante.fr/n", "ANSM", public=True)
    VectorStore(tmp_path / "rag.sqlite3").replace_document(
        document, chunk_pages(document.document_id, [(1, path.read_text())]), [[1, 0]], "nomic-embed-text", "x")
    retriever, documents = build_retriever(settings, options)
    assert retriever is not None and documents == 1
    assert build_retriever(settings, RuntimeOptions(db=options.db, no_rag=True)) == (None, 0)


def test_model_check(runtime):
    assert runtime.check_model() == ""
    runtime.client = FakeClient("tiny", "h")
    with pytest.raises(ModelUnusable, match="« tools » absente"):
        runtime.check_model()


def test_configure_switches_model_and_parameters_live(runtime):
    assert "thinking" in runtime.configure(model="qwen3:4b")
    runtime.configure(temperature=0.6, max_history_turns=2)

    assert runtime.pipeline.client is runtime.client and runtime.client.model == "qwen3:4b"
    assert runtime.client.options["temperature"] == 0.6 and runtime.pipeline.max_history_turns == 2
    assert runtime.describe()["model"] == "qwen3:4b"


@pytest.mark.parametrize("changes, error", [
    ({"model": "tiny"}, ModelUnusable), ({"model": "absent"}, ModelUnusable),
    ({"temperature": -1}, ConfigError), ({"system_prompt": "x"}, ValueError),
])
def test_configure_refuses_without_changing_anything(runtime, changes, error):
    with pytest.raises(error):
        runtime.configure(**changes)
    assert runtime.client.model == "qwen2.5:3b" and runtime.settings.model.temperature == 0.2


# --- Consultations ---

def test_new_consultation_and_restore_after_restart(options):
    with open_runtime(options) as runtime:
        first = runtime.open_consultation("c1", patient="Jeanne Dupont")
        first.set_filters(Filters(publisher="HAS"))
    with open_runtime(options) as runtime:
        again = runtime.consultation("c1")
        assert again.patient_id == "demo-dupont" and again.context.filters.publisher == "HAS"
        with pytest.raises(KeyError):
            runtime.consultation("inconnue")


def test_a_session_keeps_its_patient_and_profile(runtime):
    runtime.stores.profiles.save(DoctorProfile("cardio", "Cardiologie"))
    runtime.open_consultation("c1", patient="demo-dupont")

    with pytest.raises(ValueError, match="autre patient"):
        runtime.open_consultation("c1", patient="demo-bernard")
    with pytest.raises(ValueError, match="autre profil"):
        runtime.open_consultation("c1", profile="cardio")
    assert runtime.open_consultation("c1", patient="Jeanne Dupont").patient_id == "demo-dupont"


def test_fork_keeps_patient_and_filters_and_reloads_profile(runtime):
    consultation = runtime.open_consultation(patient="demo-dupont")
    consultation.set_filters(Filters(publisher="ANSM"))
    runtime.stores.profiles.save(DoctorProfile("default", "Médecine générale"))

    fork = runtime.fork(consultation)

    assert fork.session_id != consultation.session_id
    assert (fork.patient_id, fork.context.filters.publisher) == ("demo-dupont", "ANSM")
    assert fork.context.profile.specialty == "Médecine générale"
    assert runtime.fork(consultation, patient="demo-bernard").patient_id == "demo-bernard"


def test_list_consultations_most_recent_first(runtime):
    runtime.open_consultation("a", patient="demo-dupont")
    runtime.open_consultation("b")
    runtime.stores.sessions.save_context("a", {**runtime.stores.sessions.load_context("a"),
                                               "updated_at": "2099-01-01T00:00:00"})

    listed = runtime.list_consultations()

    assert [item["session_id"] for item in listed] == ["a", "b"]
    assert {item["session_id"]: item["patient_name"] for item in listed} == {"a": "Jeanne Dupont", "b": None}


def test_ask_reveals_for_display_and_records_the_prompt(runtime):
    consultation = runtime.open_consultation(patient="demo-dupont")
    FakeClient.replies = [answer("Non : [PATIENT_1] est allergique.")]

    events = list(consultation.ask("Mme Dupont peut-elle prendre de l'amoxicilline ?", confirm_with(True)))

    assert "".join(e.data for e in events if e.type == "token") == "Non : Jeanne Dupont est allergique."
    assert consultation.history()[0]["content"] == "[PATIENT_1] peut-elle prendre de l'amoxicilline ?"
    assert consultation.history(revealed=True)[1]["content"] == "Non : Jeanne Dupont est allergique."
    prompt = consultation.last_prompt()
    assert prompt["messages"][-1]["content"].startswith("[PATIENT_1]") and prompt["context_window"] == 2048
    log = next((runtime.logger.directory).glob("*.jsonl")).read_text()
    assert "Dupont" not in log and json.loads(log)["response"] == "Non : [PATIENT_1] est allergique."


def test_reading_turn_offers_no_tool_but_note_request_does(runtime):
    consultation = runtime.open_consultation(patient="demo-dupont")
    FakeClient.replies = [answer("Pénicilline."), answer("D'accord.")]

    list(consultation.ask("Quelles allergies sont enregistrées ?", confirm_with(True)))
    list(consultation.ask("Ajoute une note au dossier : revu ce jour", confirm_with(True)))

    offered = [tools for _, tools in runtime.client.calls]
    assert offered[0] is None
    assert [tool["function"]["name"] for tool in offered[1]] == ["add_patient_note"]


def test_model_updates_record_after_doctor_approval(runtime):
    consultation = runtime.open_consultation(patient="demo-dupont")
    call = {"function": {"name": "add_patient_entry",
                         "arguments": {"patient": "[PATIENT_1]", "field": "allergies", "value": "Latex"}}}
    FakeClient.replies = [[ChatChunk(tool_calls=[call])], answer("Allergie ajoutée.")]
    confirm = confirm_with(True)

    events = list(consultation.ask("Ajoute une allergie au latex", confirm))

    assert confirm.calls == [("add_patient_entry", {"patient": "Jeanne Dupont", "field": "allergies", "value": "Latex"})]
    assert "Latex" in consultation.patient_record()["allergies"]
    assert [e.type for e in events][-1] == "done"


def test_manual_note_goes_through_confirmation(runtime):
    consultation = runtime.open_consultation(patient="demo-dupont")
    before = consultation.patient_record()["notes"]

    assert consultation.add_note("Refusée", confirm_with(False)) is None
    assert consultation.patient_record()["notes"] == before
    assert not consultation.add_note("Acceptée", confirm_with(True)).is_error
    assert consultation.patient_record()["notes"] == before + ["Acceptée"]
    with pytest.raises(ValueError, match="Sélectionnez un patient"):
        runtime.open_consultation().add_note("x", confirm_with(True))
