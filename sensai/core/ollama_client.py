"""Client HTTP direct vers l'API d'Ollama (aucun framework LLM)."""
import json
from dataclasses import dataclass, field
from typing import Any, Iterator

import requests

from sensai.core.interfaces import Message

DEFAULT_HOST = "http://localhost:11434"


class OllamaError(RuntimeError):
    """Erreur signalée par Ollama dans le flux NDJSON."""


@dataclass
class ChatChunk:
    """Un fragment de réponse, déjà extrait de la ligne NDJSON."""
    content: str = ""
    thinking: str = ""              # raisonnement des modèles « thinking » (qwen3), hors réponse
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    done: bool = False
    prompt_tokens: int = 0          # renseigné sur le fragment final uniquement
    completion_tokens: int = 0      # idem


class OllamaClient:
    def __init__(self, model: str, host: str = DEFAULT_HOST,
                 options: dict[str, Any] | None = None,
                 think: bool | None = None, timeout: float = 120.0):
        self.model = model
        self.host = host.rstrip("/")
        self.options = options or {}
        self.think = think          # None : on laisse le défaut du modèle
        self.timeout = timeout      # en streaming : délai max entre deux fragments

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
            resp.raise_for_status()
            for line in resp.iter_lines():
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
                )
