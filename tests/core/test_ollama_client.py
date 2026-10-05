import json

import pytest
import requests

from sensai.core import ollama_client
from sensai.core.ollama_client import OllamaClient, OllamaError


class FakeResponse:
    def __init__(self, lines, status=200):
        self.lines = lines
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def raise_for_status(self):
        if self.status >= 400:
            raise requests.HTTPError(f"{self.status}")

    def iter_lines(self):
        yield from self.lines


def ndjson(*objects):
    return [json.dumps(o).encode() for o in objects]


@pytest.fixture
def fake_post(monkeypatch):
    """Remplace requests.post ; renvoie la liste des appels capturés."""
    calls = []

    def install(lines, status=200):
        def post(url, **kwargs):
            calls.append({"url": url, **kwargs})
            return FakeResponse(lines, status)
        monkeypatch.setattr(ollama_client.requests, "post", post)
        return calls
    return install


def test_streams_fragments_in_order(fake_post):
    fake_post(ndjson(
        {"message": {"role": "assistant", "content": "Bon"}, "done": False},
        {"message": {"role": "assistant", "content": "jour"}, "done": False},
        {"message": {"role": "assistant", "content": ""}, "done": True,
         "prompt_eval_count": 12, "eval_count": 3},
    ))
    chunks = list(OllamaClient("m").chat_stream([{"role": "user", "content": "Salut"}]))

    assert [c.content for c in chunks] == ["Bon", "jour", ""]
    assert [c.done for c in chunks] == [False, False, True]


def test_final_chunk_carries_token_counts(fake_post):
    fake_post(ndjson(
        {"message": {"content": "ok"}, "done": False},
        {"message": {"content": ""}, "done": True, "prompt_eval_count": 12, "eval_count": 3},
    ))
    *_, last = OllamaClient("m").chat_stream([])

    assert (last.prompt_tokens, last.completion_tokens) == (12, 3)


def test_is_lazy_generator(fake_post):
    calls = fake_post(ndjson({"message": {"content": "a"}, "done": True}))
    stream = OllamaClient("m").chat_stream([])
    assert calls == []          # rien n'est envoyé avant la première lecture
    next(stream)
    assert len(calls) == 1


def test_thinking_kept_apart_from_content(fake_post):
    fake_post(ndjson(
        {"message": {"content": "", "thinking": "Okay, the user"}, "done": False},
        {"message": {"content": "Bonjour"}, "done": True},
    ))
    chunks = list(OllamaClient("m").chat_stream([]))

    assert [c.thinking for c in chunks] == ["Okay, the user", ""]
    assert "".join(c.content for c in chunks) == "Bonjour"


def test_tool_calls_are_exposed(fake_post):
    call = {"function": {"name": "get_patient", "arguments": {"name": "[PATIENT_1]"}}}
    fake_post(ndjson({"message": {"content": "", "tool_calls": [call]}, "done": True}))
    chunks = list(OllamaClient("m").chat_stream([]))

    assert chunks[0].tool_calls == [call]


def test_skips_blank_lines(fake_post):
    lines = [b""] + ndjson({"message": {"content": "a"}, "done": True}) + [b""]
    fake_post(lines)

    assert [c.content for c in OllamaClient("m").chat_stream([])] == ["a"]


def test_request_body_and_url(fake_post):
    calls = fake_post(ndjson({"message": {"content": ""}, "done": True}))
    messages = [{"role": "user", "content": "Salut"}]
    tools = [{"type": "function", "function": {"name": "t"}}]
    client = OllamaClient("qwen3:4b", host="http://h:1/", options={"temperature": 0.2}, think=False)
    list(client.chat_stream(messages, tools=tools))

    call = calls[0]
    assert call["url"] == "http://h:1/api/chat"
    assert call["stream"] is True
    assert call["json"] == {"model": "qwen3:4b", "messages": messages, "stream": True,
                            "tools": tools, "options": {"temperature": 0.2}, "think": False}


def test_optional_fields_omitted_by_default(fake_post):
    calls = fake_post(ndjson({"message": {"content": ""}, "done": True}))
    list(OllamaClient("m").chat_stream([]))

    assert set(calls[0]["json"]) == {"model", "messages", "stream"}


def test_error_line_raises(fake_post):
    fake_post(ndjson(
        {"message": {"content": "a"}, "done": False},
        {"error": "model runner crashed"},
    ))
    stream = OllamaClient("m").chat_stream([])
    assert next(stream).content == "a"
    with pytest.raises(OllamaError, match="runner crashed"):
        next(stream)


def test_http_error_raises(fake_post):
    fake_post([], status=404)
    with pytest.raises(requests.HTTPError):
        list(OllamaClient("absent").chat_stream([]))
