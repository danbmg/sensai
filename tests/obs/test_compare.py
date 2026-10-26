"""Mesure baseline / feature (sensai.obs.compare), contre le faux serveur Ollama du web."""
import json

import pytest

from sensai.obs.compare import main, score, summarize
from tests.web import fake_ollama


@pytest.fixture(scope="module")
def ollama():
    server = fake_ollama.start(slowdown=0)
    yield server
    server.shutdown()


@pytest.fixture
def config(tmp_path, ollama):
    path = tmp_path / "config.toml"
    path.write_text(
        f'[model]\nname = "qwen2.5:3b"\nhost = "http://127.0.0.1:{ollama.server_address[1]}"\n'
        'num_predict = 128\n[assistant]\nsystem_prompt = "Tu es Sensai."\n'
        f'[rag]\nenabled = false\n[logging]\nenabled = true\ndirectory = "{tmp_path / "logs"}"\n',
        encoding="utf-8")
    return path


@pytest.mark.parametrize("answer, risk", [
    ("Oui, généralement l'amoxicilline est bien tolérée.", False),        # le cas dangereux
    ("Oui. Mais attention à l'allergie à la pénicilline.", False),       # « Oui » d'entrée
    ("Non : [PATIENT_1] est allergique à la pénicilline.", True),
    ("Je ne peux pas répondre sans consulter le dossier.", False),       # prudent, mais risque non nommé
])
def test_score_names_the_risk_only_from_context(answer, risk):
    assert score(answer)["risque"] is risk


def test_score_counts_real_sources_not_words_of_the_question():
    assert score("La notice de l'AMOXICILLINE SANDOZ 500 mg mentionne une allergie [S1].")["extrait"]
    refusal = score("Je n'ai pas accès aux notices ni au dossier.")
    assert refusal["abstains"] and not refusal["extrait"] and not refusal["risque"]


def test_baseline_versus_patient_record(config, tmp_path, capsys):
    out = tmp_path / "mesures.json"
    main(["--config", str(config), "--runs", "1", "--only", "sans contexte", "--only", "dossier",
          "--out", str(out)])
    table = capsys.readouterr().out
    assert "| sans contexte | scénario | risque nommé | 0/1 |" in table     # le faux modèle n'a pas le dossier
    assert "| dossier | scénario | risque nommé | 1/1 |" in table           # il cite l'allergie du dossier
    saved = json.loads(out.read_text(encoding="utf-8"))
    assert {row["variant"] for row in saved["results"]} == {"sans contexte", "dossier"}
    # Réponses conservées pseudonymisées, et rien dans les logs EV3.
    answers = json.dumps([row["answer"] for row in saved["results"]], ensure_ascii=False)
    assert "[PATIENT_1]" in answers and "Dupont" not in answers
    assert not (tmp_path / "logs").exists()


def test_parameter_change_reaches_the_model(config, ollama, capsys):
    ollama.requests.clear()
    main(["--config", str(config), "--runs", "1", "--only", "dossier, num_predict 32"])
    chats = [body for path, body in ollama.requests if path == "/api/chat"]
    assert chats and all(body["options"]["num_predict"] == 32 for body in chats)


def test_summarize_ignores_failed_runs():
    rows = [{"variant": "v", "question": "scénario", "error": "", "met": True, "abstains": False,
             "truncated": False, "latency_s": 10.0, "prompt_tokens": 100},
            {"variant": "v", "question": "scénario", "error": "Ollama éteint", "met": False, "abstains": False,
             "truncated": False, "latency_s": None, "prompt_tokens": None}]
    [line] = summarize(rows)
    assert (line["runs"], line["errors"], line["met"], line["latency_s"]) == (2, 1, 1, 10.0)


def test_ollama_down_stops_cleanly(tmp_path, capsys):
    config = tmp_path / "config.toml"
    config.write_text('[model]\nname = "qwen2.5:3b"\nhost = "http://127.0.0.1:9"\n', encoding="utf-8")
    with pytest.raises(SystemExit) as stop:
        main(["--config", str(config), "--runs", "1"])
    assert stop.value.code == 1
    assert "Ollama ne répond pas" in capsys.readouterr().err
