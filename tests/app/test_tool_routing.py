import pytest

from sensai.app.tool_routing import requested_tools


@pytest.mark.parametrize("text, tools", [
    ("Quelles allergies sont enregistrées pour Mme Dupont ?", set()),       # lecture : aucun outil
    ("Mme Dupont peut-elle prendre de l'amoxicilline ?", set()),
    ("Quelles notes sont enregistrées ?", set()),
    ("Ajoute une note au dossier : allergie documentée.", {"add_patient_note"}),
    ("Enregistre une note : patiente vue ce jour", {"add_patient_note"}),
    ("Peut-elle prendre de l'amoxicilline ? Si non, ajoute une note à son dossier", {"add_patient_note"}),
    ("Ajoute une allergie au latex", {"add_patient_entry"}),
    ("Mets à jour ses traitements : metformine 500 mg", {"add_patient_entry"}),
    ("Retire l'amlodipine de ses traitements", {"remove_patient_entry"}),
    ("Elle ne prend plus d'amlodipine, supprime ce traitement", {"remove_patient_entry"}),
    ("Cherche le patient Bernard", {"find_patients"}),
    ("Combien font 12 * 4 ?", {"calculator"}),
    ("Quelle heure est-il ?", {"get_current_time"}),
])
def test_only_plausible_tools_are_offered(text, tools):
    assert requested_tools(text) == tools


@pytest.mark.parametrize('query', ['Ajoute un patient Jean Rivière', 'Crée une nouvelle patiente Alice', 'Créer un patient'])
def test_patient_creation_routing(query):
    assert 'create_patient' in requested_tools(query)
    assert 'delete_patient' not in requested_tools(query)


@pytest.mark.parametrize('query', ['Supprime le patient Jean Rivière', 'Retire cette patiente', 'Supprime le dossier patient Jean Rivière'])
def test_patient_deletion_routing(query):
    assert {'delete_patient', 'find_patients', 'get_patient'} <= requested_tools(query)
    assert 'create_patient' not in requested_tools(query)
