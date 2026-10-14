from types import SimpleNamespace

import pytest
import requests

from sensai import cli
from sensai.core.ollama_client import ChatChunk, ModelNotFoundError, OllamaError

TOOLS = ["completion", "tools"]


class FakeClient:
    capabilities_result: list[str] | Exception = TOOLS     # réponse de /api/show, ou erreur
    replies: list[list] = []                # une liste de fragments par appel ; une exception y est levée
    calls: list[list[dict]] = []            # messages reçus, un élément par appel

    def __init__(self, model, host, options=None, **kwargs):
        FakeClient.model, FakeClient.host, FakeClient.options = model, host, options
        self.model, self.host, self.timeout = model, host, 120.0

    def capabilities(self):
        if isinstance(FakeClient.capabilities_result, Exception):
            raise FakeClient.capabilities_result
        return FakeClient.capabilities_result

    def chat_stream(self, messages, tools=None):
        FakeClient.calls.append(messages)
        for item in FakeClient.replies[len(FakeClient.calls) - 1]:
            if isinstance(item, BaseException):
                raise item
            yield item


def reply(text):
    return [ChatChunk(content=text, done=True)]


@pytest.fixture
def config_file(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[model]\nname = "llama3.2:3b"\nhost = "http://h:1"\ntemperature = 0.1\n'
                    '[assistant]\nsystem_prompt = "Tu es Sensai."\n', encoding="utf-8")
    return path


@pytest.fixture
def run_cli(monkeypatch, capsys, config_file):
    """Lance la CLI sur `inputs` (puis Ctrl+D) ; renvoie stdout sans la bannière, et stderr.

    Une exception dans `inputs` est levée par input() (ex. KeyboardInterrupt = Ctrl+C).
    """
    monkeypatch.setattr(cli, "OllamaClient", FakeClient)

    def run(inputs, replies=(), argv=(), capabilities=TOOLS):
        FakeClient.capabilities_result = capabilities
        FakeClient.replies, FakeClient.calls = list(replies), []
        lines = iter(inputs)

        def fake_input(prompt=""):
            line = next(lines, EOFError())
            if isinstance(line, BaseException):
                raise line
            return line
        monkeypatch.setattr("builtins.input", fake_input)
        cli.main(["--config", str(config_file), "--db", str(config_file.parent / "test.sqlite3"), *argv])
        captured = capsys.readouterr()
        return SimpleNamespace(out=captured.out.split("\n", 1)[1], err=captured.err)
    return run


SYSTEM = {"role": "system", "content": "Tu es Sensai."}


def test_prints_streamed_answer(run_cli):
    out = run_cli(["Salut"],
                  [[ChatChunk(content="Bon"), ChatChunk(content="jour", done=True)]]).out

    assert out == "Bonjour\n\n"         # réponse, puis saut de ligne du Ctrl+D


def test_uses_config_file(run_cli):
    run_cli(["Salut"], [[]])

    assert (FakeClient.model, FakeClient.host) == ("llama3.2:3b", "http://h:1")
    assert FakeClient.options == {"temperature": 0.1, "num_ctx": 2048, "num_predict": 128,
                                 "num_thread": 2, "num_batch": 64}
    assert FakeClient.calls == [[SYSTEM, {"role": "user", "content": "Salut"}]]


def test_model_flag_overrides_config(run_cli):
    run_cli([], argv=["--model", "qwen2.5:3b"])

    assert FakeClient.model == "qwen2.5:3b"


def test_banner_shows_model_and_commands(monkeypatch, capsys, config_file):
    monkeypatch.setattr(cli, "OllamaClient", FakeClient)
    monkeypatch.setattr(FakeClient, "capabilities_result", TOOLS)
    monkeypatch.setattr("builtins.input", lambda prompt="": "/quit")
    cli.main(["--config", str(config_file)])

    banner = capsys.readouterr().out
    assert "llama3.2:3b" in banner and "/reset" in banner and "/quit" in banner


def test_thinking_not_displayed(run_cli):
    # Event n'a pas de type « thinking » : seul le contenu de la réponse s'affiche.
    out = run_cli(["Salut"],
                  [[ChatChunk(thinking="hmm"), ChatChunk(content="Bonjour", done=True)]]).out

    assert out == "Bonjour\n\n"


def test_tool_call_and_result_displayed_on_their_own_lines(run_cli):
    call = {"function": {"name": "add_patient_note", "arguments": {"patient": "Paul"}}}
    out = run_cli(["Note"], [[ChatChunk(content="Je note."), ChatChunk(tool_calls=[call])]]).out

    assert out == (f"Je note.\n{cli.DIM}→ add_patient_note(patient='Paul'){cli.RESET}\n"
                   'Action proposée : add_patient_note({"patient": "Paul"})\n'
                   f"{cli.DIM}← Action refusée par le médecin{cli.RESET}\n"
                   "Action annulée à votre demande. Non exécuté : add_patient_note.\n\n")


def test_previous_turns_sent_to_model(run_cli):
    run_cli(["Je m'appelle Paul", "Comment je m'appelle ?"],
            [reply("Enchanté, Paul."), reply("Paul.")])

    assert FakeClient.calls[1] == [
        SYSTEM,
        {"role": "user", "content": "Je m'appelle Paul"},
        {"role": "assistant", "content": "Enchanté, Paul."},
        {"role": "user", "content": "Comment je m'appelle ?"},
    ]


def test_history_keeps_full_answer_without_thinking(run_cli):
    run_cli(["a", "b"], [[ChatChunk(thinking="hmm"), ChatChunk(content="Bon"),
                          ChatChunk(content="jour", done=True)], reply("")])

    assert FakeClient.calls[1][2] == {"role": "assistant", "content": "Bonjour"}


def test_reset_clears_history_but_keeps_system_prompt(run_cli):
    out = run_cli(["Je m'appelle Paul", "/reset", "Comment je m'appelle ?"],
                  [reply("Enchanté."), reply("Je ne sais pas.")]).out

    assert FakeClient.calls[1] == [SYSTEM, {"role": "user", "content": "Comment je m'appelle ?"}]
    assert "Conversation effacée." in out


def test_quit_stops_without_calling_model(run_cli):
    run_cli(["/quit", "Salut"])

    assert FakeClient.calls == []


def test_ctrl_d_quits(run_cli):
    run_cli(["Salut"], [reply("Bonjour")])     # l'entrée s'épuise → EOFError

    assert len(FakeClient.calls) == 1


def test_commands_ignore_surrounding_spaces(run_cli):
    run_cli(["  /quit  ", "Salut"])

    assert FakeClient.calls == []


def test_unknown_command_not_sent_to_model(run_cli):
    out = run_cli(["/reste"]).out

    assert FakeClient.calls == []
    assert "Commande inconnue : /reste" in out


# --- Erreurs au démarrage (/api/show) ---

def test_ollama_down_at_startup_exits_with_message(run_cli):
    with pytest.raises(SystemExit, match=r"Ollama ne répond pas sur http://h:1.*ollama serve"):
        run_cli(["Salut"], capabilities=requests.ConnectionError("refused"))
    assert FakeClient.calls == []


def test_connect_timeout_reported_as_unreachable(run_cli):
    with pytest.raises(SystemExit, match="Ollama ne répond pas sur"):
        run_cli([], capabilities=requests.ConnectTimeout("timed out"))


def test_missing_model_suggests_pull(run_cli):
    with pytest.raises(SystemExit, match="ollama pull llama3.2:3b"):
        run_cli(["Salut"], capabilities=ModelNotFoundError("llama3.2:3b"))
    assert FakeClient.calls == []


def test_model_without_tools_refused(run_cli):
    with pytest.raises(SystemExit, match="« tools » absente"):
        run_cli(["Salut"], capabilities=["completion"])
    assert FakeClient.calls == []


def test_thinking_model_warns_but_runs(run_cli):
    result = run_cli(["Salut"], [reply("Bonjour")], capabilities=TOOLS + ["thinking"])

    assert "⚠ llama3.2:3b est un modèle « thinking »" in result.err
    assert len(FakeClient.calls) == 1


def test_other_http_error_at_startup_exits_with_message(run_cli):
    with pytest.raises(SystemExit, match="Erreur d'Ollama : 500"):
        run_cli([], capabilities=requests.HTTPError("500 Server Error"))


# --- Erreurs en cours de session : message, et la session continue ---

def test_empty_input_ignored(run_cli):
    run_cli(["", "   ", "Salut"], [reply("Bonjour")])

    assert len(FakeClient.calls) == 1


def test_ctrl_c_at_prompt_keeps_session(run_cli):
    result = run_cli(["Je m'appelle Paul", KeyboardInterrupt(), "Comment je m'appelle ?"],
                     [reply("Enchanté."), reply("Paul.")])

    assert len(FakeClient.calls[1]) == 4        # système + tour 1 + question
    assert "/quit pour quitter" in result.out


def test_ctrl_c_during_generation_drops_turn_and_keeps_session(run_cli):
    result = run_cli(["Je m'appelle Paul", "Raconte une histoire", "Comment je m'appelle ?"],
                     [reply("Enchanté."), [ChatChunk(content="Il était"), KeyboardInterrupt()],
                      reply("Paul.")])

    assert f"Il était\n{cli.DIM}Génération interrompue." in result.out
    assert FakeClient.calls[2] == [
        SYSTEM,
        {"role": "user", "content": "Je m'appelle Paul"},
        {"role": "assistant", "content": "Enchanté."},
        {"role": "user", "content": "Comment je m'appelle ?"},
    ]


@pytest.mark.parametrize("error, message", [
    (requests.ReadTimeout("read timed out"), "aucun fragment reçu en 120 s"),
    (requests.ConnectionError("refused"), "ollama serve"),
    (ModelNotFoundError("llama3.2:3b"), "ollama pull llama3.2:3b"),
    (OllamaError("model runner crashed"), "Erreur d'Ollama : model runner crashed"),
])
def test_error_during_generation_reported_and_session_kept(run_cli, error, message):
    result = run_cli(["Je m'appelle Paul", "Raconte", "Comment je m'appelle ?"],
                     [reply("Enchanté."), [ChatChunk(content="Il était"), error],
                      reply("Paul.")])

    assert message in result.err
    assert "Traceback" not in result.err
    assert [m["content"] for m in FakeClient.calls[2]] == [
        "Tu es Sensai.", "Je m'appelle Paul", "Enchanté.", "Comment je m'appelle ?"]


def test_missing_config_exits_with_message(tmp_path):
    with pytest.raises(SystemExit, match="Configuration invalide.*introuvable"):
        cli.main(["--config", str(tmp_path / "absent.toml")])
