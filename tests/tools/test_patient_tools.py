"""Outils patients (M3) : l'agent lit, cherche et met à jour les dossiers, en local comme en MCP."""
import json

import pytest

from sensai.memory.fixtures import seed_demo_patients
from sensai.memory.patients import PatientStore
from sensai.tools.patient_tools import DANGEROUS_TOOLS
from sensai.tools.runtime import medical_tools


@pytest.fixture
def patients(tmp_path):
    store = PatientStore(tmp_path / "memory.sqlite3")
    seed_demo_patients(store)
    return store


def test_store_adds_and_removes_record_entries(patients):
    patients.add_entry("Jeanne Dupont", "allergies", "Latex")
    patients.add_entry("demo-dupont", "allergies", "latex")             # doublon ignoré
    assert patients.get_patient("demo-dupont")["allergies"][-1] == "Latex"
    assert len(patients.get_patient("demo-dupont")["allergies"]) == 2

    patients.remove_entry("demo-dupont", "treatments", "AMLODIPINE 5 mg/j")
    assert patients.get_patient("demo-dupont")["treatments"] == []
    with pytest.raises(LookupError, match="absent"):
        patients.remove_entry("demo-dupont", "treatments", "Metformine")
    with pytest.raises(ValueError, match="Liste attendue"):
        patients.add_entry("demo-dupont", "name", "Autre nom")
    patients.add_patient_note("demo-dupont", "Revue")
    patients.add_patient_note("demo-dupont", "Revue")                     # le journal garde les deux
    assert patients.get_patient("demo-dupont")["notes"][-2:] == ["Revue", "Revue"]


@pytest.mark.parametrize("use_mcp", [False, True], ids=["local", "mcp-stdio"])
def test_agent_tools_read_search_and_update(patients, use_mcp):
    with medical_tools(patients, use_mcp) as registry:
        names = {schema["function"]["name"]: schema["function"] for schema in registry.schemas()}
        assert {"get_patient", "find_patients", "add_patient_entry", "remove_patient_entry"} <= set(names)
        assert all(registry.is_dangerous(name) for name in DANGEROUS_TOOLS)
        assert not registry.is_dangerous("find_patients")
        field = names["add_patient_entry"]["parameters"]["properties"]["field"]
        assert set(field["enum"]) == {"allergies", "treatments", "medical_history"}

        found = json.loads(registry.call("find_patients", {"query": "dupont"}).content)
        added = registry.call("add_patient_entry", {"patient": "Jeanne Dupont", "field": "allergies", "value": "Latex"})
        removed = registry.call("remove_patient_entry", {"patient": "demo-dupont", "field": "treatments",
                                                         "value": "Amlodipine 5 mg/j"})
        refused = registry.call("add_patient_entry", {"patient": "demo-dupont", "field": "allergies",
                                                      "value": '{"type": "string"}'})
        unknown = registry.call("remove_patient_entry", {"patient": "demo-dupont", "field": "allergies",
                                                         "value": "Arachide"})

    assert found == {"patients": [{"patient_id": "demo-dupont", "name": "Jeanne Dupont"}]}
    assert not added.is_error and "Latex" in added.content
    assert not removed.is_error
    assert refused.is_error and unknown.is_error and "absent" in unknown.content
    record = patients.get_patient("demo-dupont")
    assert record["allergies"][-1] == "Latex" and record["treatments"] == []


@pytest.mark.parametrize('tool', ['create_patient', 'delete_patient'])
@pytest.mark.parametrize('approved', [False, True])
@pytest.mark.parametrize('use_mcp', [False, True], ids=['local', 'mcp'])
def test_patient_lifecycle_requires_confirmation(patients, tool, approved, use_mcp):
    from sensai.core.ollama_client import ChatChunk
    from sensai.core.pipeline import Pipeline
    from sensai.guardrails.pii_vault import SensaiPIIVault

    args = {'name': 'Jean Rivière'} if tool == 'create_patient' else {'patient': '[PATIENT_1]'}

    class Model:
        model = 'fake'
        calls = 0

        def chat_stream(self, messages, tools=None):
            self.calls += 1
            if self.calls == 1:
                yield ChatChunk(tool_calls=[{'function': {'name': tool, 'arguments': args}}])
            else:
                yield ChatChunk(content='Action terminée.', done=True)

    confirmations = []

    def confirm(call_id, name, arguments):
        confirmations.append((name, arguments))
        return approved

    with medical_tools(patients, use_mcp) as registry:
        pipeline = Pipeline(Model(), tools=registry, vault_factory=lambda mapping: SensaiPIIVault(
            {'[PATIENT_1]': 'Jeanne Dupont'}, patients=patients.list_patients()))
        events = list(pipeline.run('Gestion du dossier patient', 'test', confirm))
    assert events[-1].type == 'done'
    assert len(confirmations) == 1 and confirmations[0][0] == tool
    if tool == 'create_patient':
        assert bool(patients.find_patients('Jean Rivière')) is approved
    else:
        assert bool(patients.find_patients('Jeanne Dupont')) is not approved
        assert confirmations[0][1]['patient'] == 'Jeanne Dupont'


@pytest.mark.parametrize('use_mcp', [False, True], ids=['local', 'mcp'])
def test_create_delete_validation(patients, use_mcp):
    with medical_tools(patients, use_mcp) as registry:
        result = registry.call('create_patient', {'name': 'Jean Rivière', 'birth_date': '1980-03-12'})
        assert not result.is_error
        created = json.loads(result.content)
        assert registry.call('create_patient', {'name': 'Jean Rivière', 'birth_date': '1980-03-12'}).is_error
        assert registry.call('create_patient', {'name': 'Test', 'birth_date': '1980-02-31'}).is_error
        assert registry.call('create_patient', {'name': ' '}).is_error
        other = patients.create_patient('Jean Rivière', '1990-01-01')
        assert registry.call('delete_patient', {'patient': 'Jean Rivière'}).is_error
        assert patients.get_patient(created['patient_id'])
        assert not registry.call('delete_patient', {'patient': created['patient_id']}).is_error
        assert patients.get_patient(other['patient_id'])
        assert registry.call('delete_patient', {'patient': created['patient_id']}).is_error
