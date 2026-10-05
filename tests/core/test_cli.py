import pytest

from sensai import cli
from sensai.core.ollama_client import ChatChunk


class FakeClient:
    chunks: list[ChatChunk] = []

    def __init__(self, model, *args, **kwargs):
        FakeClient.model = model

    def chat_stream(self, messages, tools=None):
        FakeClient.messages = messages
        yield from FakeClient.chunks


@pytest.fixture
def run_cli(monkeypatch, capsys):
    monkeypatch.setattr(cli, "OllamaClient", FakeClient)
    monkeypatch.setattr("builtins.input", lambda prompt="": "Salut")

    def run(chunks, argv=()):
        FakeClient.chunks = chunks
        cli.main(list(argv))
        return capsys.readouterr().out
    return run


def test_prints_streamed_answer(run_cli):
    out = run_cli([ChatChunk(content="Bon"), ChatChunk(content="jour", done=True)],
                  ["--model", "llama3.2:3b"])

    assert out == "Bonjour\n"
    assert FakeClient.model == "llama3.2:3b"
    assert FakeClient.messages == [{"role": "user", "content": "Salut"}]


def test_thinking_printed_dimmed_before_answer(run_cli):
    out = run_cli([ChatChunk(thinking="hmm"), ChatChunk(content="Bonjour", done=True)])

    assert out == f"{cli.DIM}hmm{cli.RESET}Bonjour\n"
