"""Fixtures du web : faux Ollama HTTP, config et base temporaires, application FastAPI."""
import json

import pytest
from fastapi.testclient import TestClient

from sensai.app.runtime import RuntimeOptions
from sensai.web.api import create_app
from tests.web import fake_ollama


@pytest.fixture(scope="module")
def ollama():
    server = fake_ollama.start(slowdown=0)
    yield server
    server.shutdown()


def write_config(path, host, *, logs=None, rag=False):
    path.write_text(
        f'[model]\nname = "qwen2.5:3b"\nhost = "{host}"\ntimeout = 10\n'
        '[assistant]\nsystem_prompt = "Tu es Sensai."\nmax_history_turns = 2\n'
        f"[rag]\nenabled = {json.dumps(rag)}\n"
        f"[logging]\nenabled = {json.dumps(logs is not None)}\ndirectory = {json.dumps(str(logs or 'logs'))}\n",
        encoding="utf-8")
    return path


@pytest.fixture
def options(tmp_path, ollama):
    host = f"http://127.0.0.1:{ollama.server_address[1]}"
    config = write_config(tmp_path / "config.toml", host, logs=tmp_path / "logs")
    return RuntimeOptions(config=str(config), db=tmp_path / "memory.sqlite3", demo=True)


@pytest.fixture
def client(options):
    with TestClient(create_app(options, confirm_timeout=2, busy_wait=0.1)) as test_client:
        yield test_client


def events(response) -> list[tuple[str, object]]:
    """Événements SSE d'une réponse complète : [(type, data), …]."""
    parsed = []
    for block in response.text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        parsed.append((lines["event"], json.loads(lines["data"])))
    return parsed
