import json

import pytest
import requests
from urllib3.exceptions import ReadTimeoutError

from sensai.core import ollama_client
from sensai.core.ollama_client import ModelNotFoundError, OllamaClient, OllamaError


class FakeResponse:
    def __init__(self, lines=(), status=200, payload=None):
        self.lines = lines
        self.status_code = status
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}")

    def json(self):
        return self.payload

    def iter_lines(self):
        for line in self.lines:
            if isinstance(line, Exception):
                raise line
            yield line


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


def test_final_chunk_carries_durations_in_seconds(fake_post):
    fake_post(ndjson({"message": {"content": ""}, "done": True, "load_duration": 2_000_000_000,
                      "prompt_eval_duration": 500_000_000, "eval_duration": 1_500_000_000}))
    (last,) = OllamaClient("m").chat_stream([])

    assert (last.load_s, last.prompt_eval_s, last.eval_s) == (2.0, 0.5, 1.5)


def test_missing_model_raises_model_not_found(fake_post):
    fake_post([], status=404)
    with pytest.raises(ModelNotFoundError, match="absent"):
        list(OllamaClient("absent").chat_stream([]))


def test_other_http_error_raises(fake_post):
    fake_post([], status=500)
    with pytest.raises(requests.HTTPError):
        list(OllamaClient("m").chat_stream([]))


def test_mid_stream_timeout_is_a_timeout_not_a_connection_error(fake_post):
    # requests transforme ce timeout en ConnectionError : le client doit le rétablir
    timeout = requests.ConnectionError(ReadTimeoutError(None, None, "Read timed out."))
    fake_post(ndjson({"message": {"content": "a"}, "done": False}) + [timeout])
    stream = OllamaClient("m").chat_stream([])
    next(stream)
    with pytest.raises(requests.ReadTimeout):
        next(stream)


def test_real_connection_error_unchanged(fake_post):
    fake_post([requests.ConnectionError("connection refused")])
    with pytest.raises(requests.ConnectionError) as info:
        list(OllamaClient("m").chat_stream([]))
    assert not isinstance(info.value, requests.Timeout)


def test_list_models(monkeypatch):
    payload = {"models": [{"name": "qwen3:4b-instruct"}, {"name": "llama3.2:3b"}]}
    monkeypatch.setattr(ollama_client.requests, "get",
                        lambda url, **kw: FakeResponse(payload=payload))

    assert OllamaClient("m").list_models() == ["qwen3:4b-instruct", "llama3.2:3b"]


def test_capabilities(monkeypatch):
    calls = []

    def post(url, **kwargs):
        calls.append((url, kwargs["json"]))
        return FakeResponse(payload={"capabilities": ["completion", "tools"]})
    monkeypatch.setattr(ollama_client.requests, "post", post)

    assert OllamaClient("m", host="http://h:1").capabilities() == ["completion", "tools"]
    assert calls == [("http://h:1/api/show", {"model": "m"})]


def test_capabilities_missing_model(monkeypatch):
    monkeypatch.setattr(ollama_client.requests, "post",
                        lambda url, **kw: FakeResponse(status=404))
    with pytest.raises(ModelNotFoundError):
        OllamaClient("absent").capabilities()
