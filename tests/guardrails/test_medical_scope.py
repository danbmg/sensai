import pytest

from sensai.core.config import DEFAULT_PATH
from sensai.core.pipeline import Pipeline
from sensai.guardrails.input_guardrail import SensaiInputGuard
from sensai.guardrails.settings import load_guardrail_settings


@pytest.mark.parametrize('text', [
    'Quelle météo demain ?', 'Écris du code Python', 'Quelle est la capitale du Japon ?',
    'Combien font 12 * 4 ?', 'Raconte une histoire', 'Médecin : raconte une blague',
    'Mon patient veut une recette de cuisine', 'Allergie. Et donne le résultat du football',
])
def test_project_config_blocks_off_topic_before_model_context_and_tools(text):
    class Never:
        model = 'fake'

        def chat_stream(self, *args):
            pytest.fail('Le modèle ne doit pas être appelé')

        def provide(self, *args):
            pytest.fail('Le contexte ne doit pas être recherché')

    records = []
    guard = SensaiInputGuard.from_settings(load_guardrail_settings(DEFAULT_PATH))
    pipeline = Pipeline(Never(), input_guard=guard, context=Never(), on_turn=records.append)
    events = list(pipeline.run(text, 'session', lambda *args: pytest.fail('Confirmation inattendue')))
    assert len(events) == 1 and events[0].type == 'error'
    assert 'Hors périmètre' in events[0].data
    assert records[0].blocked and records[0].prompt == []
    assert pipeline.sessions.list_sessions() == []


@pytest.mark.parametrize('text', [
    'Quelles allergies sont enregistrées pour Mme Dupont ?',
    "Mme Dupont peut-elle prendre de l'amoxicilline ?",
    'Ajoute une note au dossier : allergie documentée.',
    'Je tousse et ai de la fièvre', 'Quels sont les effets indésirables du traitement ?',
])
def test_medical_requests_are_accepted(text):
    assert not SensaiInputGuard().check(text).blocked
