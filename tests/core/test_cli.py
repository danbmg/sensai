import pytest

from sensai import cli
from sensai.core.ollama_client import ChatChunk


class FakeClient:
    replies: list[list[ChatChunk]] = []     # une liste de fragments par appel au modèle
    calls: list[list[dict]] = []            # messages reçus, un élément par appel

    def __init__(self, model, host, options=None, **kwargs):
        FakeClient.model, FakeClient.host, FakeClient.options = model, host, options

    def chat_stream(self, messages, tools=None):
        FakeClient.calls.append(messages)
        yield from FakeClient.replies[len(FakeClient.calls) - 1]


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
    """Lance la CLI sur `inputs` (puis Ctrl+D) ; renvoie la sortie, sans la bannière."""
    monkeypatch.setattr(cli, "OllamaClient", FakeClient)

    def run(inputs, replies=(), argv=()):
        FakeClient.replies, FakeClient.calls = list(replies), []
        lines = iter(inputs)

        def fake_input(prompt=""):
            try:
                return next(lines)
            except StopIteration:
                raise EOFError from None
        monkeypatch.setattr("builtins.input", fake_input)
        cli.main(["--config", str(config_file), *argv])
        return capsys.readouterr().out.split("\n", 1)[1]
    return run


SYSTEM = {"role": "system", "content": "Tu es Sensai."}


def test_prints_streamed_answer(run_cli):
    out = run_cli(["Salut"], [[ChatChunk(content="Bon"), ChatChunk(content="jour", done=True)]])

    assert out == "Bonjour\n\n"         # réponse, puis saut de ligne du Ctrl+D


def test_uses_config_file(run_cli):
    run_cli(["Salut"], [[]])

    assert (FakeClient.model, FakeClient.host) == ("llama3.2:3b", "http://h:1")
    assert FakeClient.options == {"temperature": 0.1}
    assert FakeClient.calls == [[SYSTEM, {"role": "user", "content": "Salut"}]]


def test_model_flag_overrides_config(run_cli):
    run_cli([], argv=["--model", "qwen2.5:3b"])

    assert FakeClient.model == "qwen2.5:3b"


def test_banner_shows_model_and_commands(monkeypatch, capsys, config_file):
    monkeypatch.setattr(cli, "OllamaClient", FakeClient)
    monkeypatch.setattr("builtins.input", lambda prompt="": "/quit")
    cli.main(["--config", str(config_file)])

    banner = capsys.readouterr().out
    assert "llama3.2:3b" in banner and "/reset" in banner and "/quit" in banner


def test_thinking_printed_dimmed_before_answer(run_cli):
    out = run_cli(["Salut"], [[ChatChunk(thinking="hmm"), ChatChunk(content="Bonjour", done=True)]])

    assert out == f"{cli.DIM}hmm{cli.RESET}Bonjour\n\n"


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
                  [reply("Enchanté."), reply("Je ne sais pas.")])

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
    out = run_cli(["/reste"])

    assert FakeClient.calls == []
    assert "Commande inconnue : /reste" in out


def test_missing_config_exits_with_message(tmp_path):
    with pytest.raises(SystemExit, match="Configuration invalide.*introuvable"):
        cli.main(["--config", str(tmp_path / "absent.toml")])
