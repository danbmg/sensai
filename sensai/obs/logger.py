"""Logs structurés EV3 : une ligne JSON par tour, un fichier par jour (logs/AAAA-MM-JJ.jsonl).

Seule source : le TurnRecord du hook on_turn, déjà pseudonymisé par le pipeline.
Jamais les Event, qui sont en clair (ils servent à l'affichage).
"""
import hashlib
import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from sensai.core.pipeline import TurnRecord


def short_hash(text: str) -> str:
    """Empreinte courte et stable : regroupe sans révéler (identifiant de session, prompt)."""
    return hashlib.sha256(text.encode()).hexdigest()[:10]


class TurnLogger:
    def __init__(self, directory: str | Path, describe: Callable[[], dict[str, Any]] | None = None,
                 clock: Callable[[], datetime] = datetime.now):
        """`describe` renvoie la configuration en vigueur (paramètres, version du prompt)."""
        self.directory = Path(directory)
        self.describe = describe or dict
        self.clock = clock
        self.last_error = ""        # affiché par /api/status : un log en échec ne bloque pas le tour
        self._lock = threading.Lock()

    def __call__(self, record: TurnRecord) -> None:
        now = self.clock()
        entry = {
            "timestamp": now.isoformat(timespec="seconds"),
            # L'identifiant est choisi par le médecin (« dupont ») : on n'en garde qu'une empreinte.
            "session": short_hash(record.session_id),
            "model": record.model,
            "status": "blocked" if record.blocked else "error" if record.error else "ok",
            "error": record.error,
            "latency_s": round(record.latency_s, 3),
            "prompt_tokens": record.prompt_tokens,
            "completion_tokens": record.completion_tokens,
            "context_tokens": record.context_tokens,
            "tools_offered": record.tools,
            "tool_calls": [{"name": call.get("function", {}).get("name", ""),
                            "arguments": call.get("function", {}).get("arguments", {})}
                           for message in record.messages for call in message.get("tool_calls", [])],
            "prompt": record.prompt,            # pseudonymisé, exactement ce qu'a reçu le modèle
            "response": next((m["content"] for m in reversed(record.messages)
                              if m.get("role") == "assistant"), ""),
            "messages": record.messages,
            "config": self.describe(),
        }
        try:
            line = json.dumps(entry, ensure_ascii=False, default=str)
            with self._lock:
                self.directory.mkdir(parents=True, exist_ok=True)
                with (self.directory / f"{now.date().isoformat()}.jsonl").open("a", encoding="utf-8") as file:
                    file.write(line + "\n")
            self.last_error = ""
        except OSError as error:
            self.last_error = f"Écriture des logs impossible : {error}"
