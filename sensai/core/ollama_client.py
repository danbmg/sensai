"""Client HTTP direct vers l'API d'Ollama (aucun framework LLM)."""
import json
from dataclasses import dataclass, field
from typing import Any, Iterator

import requests
from urllib3.exceptions import ReadTimeoutError

from sensai.core.interfaces import Message

DEFAULT_HOST = "http://localhost:11434"
NS = 1e9  # Ollama donne ses durées en nanosecondes


class OllamaError(RuntimeError):
    """Erreur signalée par Ollama dans le flux NDJSON."""


class ModelNotFoundError(OllamaError):
    """Modèle non installé (HTTP 404) : il faut un `ollama pull`."""


@dataclass
class ChatChunk:
    """Un fragment de réponse, déjà extrait de la ligne NDJSON."""
    content: str = ""
    thinking: str = ""              # raisonnement des modèles « thinking » (qwen3), hors réponse
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    done: bool = False
    # Renseignés sur le fragment final uniquement :
    prompt_tokens: int = 0
    completion_tokens: int = 0
    load_s: float = 0.0             # chargement du modèle en mémoire
    prompt_eval_s: float = 0.0      # lecture du prompt
    eval_s: float = 0.0             # génération de la réponse


class OllamaClient:
    def __init__(self, model: str, host: str = DEFAULT_HOST,
                 options: dict[str, Any] | None = None,
                 think: bool | None = None, timeout: float = 120.0):
        self.model = model
        self.host = host.rstrip("/")
        self.options = options or {}
        self.think = think          # None : on laisse le défaut du modèle
        self.timeout = timeout      # en streaming : délai max entre deux fragments

    def list_models(self) -> list[str]:
        """GET /api/tags : noms des modèles installés."""
        resp = requests.get(f"{self.host}/api/tags", timeout=self.timeout)
        resp.raise_for_status()
        return [m["name"] for m in resp.json().get("models", [])]

    def capabilities(self) -> list[str]:
        """POST /api/show : ex. ["completion", "tools", "thinking"]."""
        resp = requests.post(f"{self.host}/api/show", json={"model": self.model},
                             timeout=self.timeout)
        if resp.status_code == 404:
            raise ModelNotFoundError(self.model)
        resp.raise_for_status()
        return resp.json().get("capabilities", [])

    def chat_stream(self, messages: list[Message],
                    tools: list[dict] | None = None) -> Iterator[ChatChunk]:
        """POST /api/chat en streaming : un ChatChunk par ligne NDJSON reçue."""
        body: dict[str, Any] = {"model": self.model, "messages": messages, "stream": True}
        if tools:
            body["tools"] = tools
        if self.options:
            body["options"] = self.options
        if self.think is not None:
            body["think"] = self.think

        with requests.post(f"{self.host}/api/chat", json=body,
                           stream=True, timeout=self.timeout) as resp:
            if resp.status_code == 404:
                raise ModelNotFoundError(self.model)
            resp.raise_for_status()
            for line in _lines(resp):
                if not line:
                    continue
                data = json.loads(line)
                if "error" in data:
                    raise OllamaError(data["error"])
                message = data.get("message", {})
                yield ChatChunk(
                    content=message.get("content", ""),
                    thinking=message.get("thinking", ""),
                    tool_calls=message.get("tool_calls", []),
                    done=data.get("done", False),
                    prompt_tokens=data.get("prompt_eval_count", 0),
                    completion_tokens=data.get("eval_count", 0),
                    load_s=data.get("load_duration", 0) / NS,
                    prompt_eval_s=data.get("prompt_eval_duration", 0) / NS,
                    eval_s=data.get("eval_duration", 0) / NS,
                )


def _lines(resp: requests.Response) -> Iterator[bytes]:
    try:
        yield from resp.iter_lines()
    except requests.ConnectionError as e:
        # requests signale un timeout survenu en cours de flux comme une ConnectionError :
        # on le remet en Timeout pour ne pas le confondre avec « Ollama éteint ».
        if e.args and isinstance(e.args[0], ReadTimeoutError):
            raise requests.ReadTimeout(*e.args) from e
        raise
