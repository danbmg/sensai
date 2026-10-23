import copy

import pytest

from sensai.core.ollama_client import ChatChunk
from sensai.core.pipeline import Pipeline
from sensai.guardrails.pii_vault import SensaiPIIVault
from sensai.memory.context import PatientContext
from sensai.memory.fixtures import seed_demo_patients
from sensai.memory.patients import PatientStore
from sensai.memory.profiles import DoctorProfile
from sensai.rag.embeddings import EmbeddingError
from sensai.rag.retrieval import Hit
from sensai.rag.routing import is_record_lookup


class Search:
    def __init__(self, hits=None, error=None):
        self.calls, self.hits, self.error = [], hits or [], error
    def search(self, query, filters=None):
        self.calls.append(query)
        if self.error:
            raise self.error
        return self.hits


def test_pipeline_injects_profile_and_sources_but_embeds_only_masked_question(tmp_path):
    patients = PatientStore(tmp_path / "patients.sqlite3")
    seed_demo_patients(patients)
    hit = Hit("chunk", "doc", "Notice publique", "https://ansm.sante.fr/notice", "ANSM", "2026-01-01",
              2, "Passage documentaire de test.", 0.9, 0.8, 1)
    search = Search([hit])
    context = PatientContext(patients, profile=DoctorProfile("p", "Généraliste", ["Concis"]), retriever=search)
    context.select("demo-dupont")
    calls = []
    class Model:
        model = "fake"
        def chat_stream(self, messages, tools=None):
            calls.append(copy.deepcopy(messages))
            yield ChatChunk(content="Réponse sourcée [S1].", done=True)
    pipeline = Pipeline(Model(), context=context,
                        vault_factory=lambda mapping: SensaiPIIVault(mapping, patients=patients.list_patients()))
    events = list(pipeline.run("Mme Dupont est née le 12/03/1958 : que dit la notice ?", "s", lambda *args: False))
    assert events[-1].type == "done"
    assert "Dupont" not in search.calls[0] and "1958" not in search.calls[0]
    assert "Généraliste" not in search.calls[0] and "Amlodipine" not in search.calls[0]
    assert "[PATIENT_1]" in search.calls[0]
    sent = str(calls[0])
    assert "Généraliste" in sent and "Amlodipine" in sent and "[S1]" in sent
    assert "https://ansm.sante.fr/notice" in sent and "page 2" in sent
    assert "Dupont" not in sent
    assert context.last_hits == [hit]


def test_no_results_or_embedding_failure_clears_sources_without_losing_patient(tmp_path):
    patients = PatientStore(tmp_path / "patients.sqlite3")
    seed_demo_patients(patients)
    search = Search()
    context = PatientContext(patients, retriever=search)
    context.select("demo-dupont")
    messages = context.provide("clear", "masked", "s")
    assert "Aucun extrait" in messages[-1]["content"] and context.last_hits == []
    search.error = EmbeddingError("Ollama down")
    messages = context.provide("clear", "masked", "s")
    assert "Jeanne Dupont" in messages[0]["content"]
    assert "indisponible" in messages[-1]["content"] and context.rag_error == "Ollama down"
    assert context.last_hits == []


@pytest.mark.parametrize("query", [
    "Quelles allergies sont enregistrées pour [PATIENT_1] ? Cite la source.",
    "Quels sont les traitements enregistrés ?",
    "Montre le dossier de [PATIENT_2].",
    "Résume le dossier local.",
])
def test_explicit_record_lookups_do_not_need_documents(query):
    assert is_record_lookup(query)


@pytest.mark.parametrize("query", [
    "[PATIENT_1] peut-elle prendre de l’amoxicilline ?",
    "Quelles allergies enregistrées justifient d'éviter l'amoxicilline ?",
    "Compare le dossier avec la notice.",
    "Quels traitements sont enregistrés et recommandés par la HAS ?",
    "Résume le dossier et explique le risque.",
    "Quelles sont les allergies à la pénicilline ?",
])
def test_ambiguous_or_document_questions_keep_rag(query):
    assert not is_record_lookup(query)


def test_auto_mode_skips_only_record_lookups_with_a_selected_patient(tmp_path):
    patients = PatientStore(tmp_path / "patients.sqlite3")
    seed_demo_patients(patients)
    search = Search()
    context = PatientContext(patients, retriever=search)
    question = "Quelles allergies sont enregistrées ?"
    context.provide(question, question, "s")
    assert len(search.calls) == 1  # sans dossier sélectionné, la recherche est conservée
    context.select("demo-dupont")
    search.calls.clear()
    messages = context.provide(question, question, "s")
    assert not search.calls
    assert "dossier patient local SQLite" in messages[0]["content"]
    assert context.last_hits == []
    context.search_mode = "always"
    context.provide(question, question, "s")
    assert len(search.calls) == 1
