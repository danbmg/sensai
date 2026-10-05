import pytest

from sensai import cli
from sensai.core.ollama_client import ChatChunk


class FakeClient:
    chunks: list[ChatChunk] = []

    def __init__(self, model, host, options=None, **kwargs):
        FakeClient.model, FakeClient.host, FakeClient.options = model, host, options

    def chat_stream(self, messages, tools=None):
        FakeClient.messages = messages
        yield from FakeClient.chunks


@pytest.fixture
def config_file(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[model]\nname = "llama3.2:3b"\nhost = "http://h:1"\ntemperature = 0.1\n'
                    '[assistant]\nsystem_prompt = "Tu es Sensai."\n', encoding="utf-8")
    return path


@pytest.fixture
def run_cli(monkeypatch, capsys, config_file):
    monkeypatch.setattr(cli, "OllamaClient", FakeClient)
    monkeypatch.setattr("builtins.input", lambda prompt="": "Salut")

    def run(chunks, argv=()):
        FakeClient.chunks = chunks
        cli.main(["--config", str(config_file), *argv])
        return capsys.readouterr().out
    return run


def test_prints_streamed_answer(run_cli):
    out = run_cli([ChatChunk(content="Bon"), ChatChunk(content="jour", done=True)])

    assert out == "Bonjour\n"


def test_uses_config_file(run_cli):
    run_cli([])

    assert (FakeClient.model, FakeClient.host) == ("llama3.2:3b", "http://h:1")
    assert FakeClient.options == {"temperature": 0.1}
    assert FakeClient.messages == [{"role": "system", "content": "Tu es Sensai."},
                                   {"role": "user", "content": "Salut"}]


def test_model_flag_overrides_config(run_cli):
    run_cli([], ["--model", "qwen2.5:3b"])

    assert FakeClient.model == "qwen2.5:3b"


def test_thinking_printed_dimmed_before_answer(run_cli):
    out = run_cli([ChatChunk(thinking="hmm"), ChatChunk(content="Bonjour", done=True)])

    assert out == f"{cli.DIM}hmm{cli.RESET}Bonjour\n"


def test_missing_config_exits_with_message(tmp_path):
    with pytest.raises(SystemExit, match="Configuration invalide.*introuvable"):
        cli.main(["--config", str(tmp_path / "absent.toml")])
