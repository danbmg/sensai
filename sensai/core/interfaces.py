"""Contrat partagé entre les trois blocs (Phase 0).

Toute modification de ce fichier engage Dan, Timothée et Matteo :
la signaler à l'équipe avant de la pousser.
"""
from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Protocol

Message = dict[str, Any]  # format Ollama : {"role", "content", "tool_calls"?}

# Pseudonymes PII : format [TYPE_N], ex. [PATIENT_1], [TEL_1]


@dataclass
class GuardResult:
    text: str                                   # texte pseudonymisé
    blocked: bool = False                       # requête refusée ?
    reason: str = ""                            # motif affiché si bloquée
    mapping: dict[str, str] = field(default_factory=dict)  # pseudonyme -> valeur réelle


class InputGuard(Protocol):                     # Matteo (EV2)
    def check(self, text: str) -> GuardResult: ...


class OutputGuard(Protocol):                    # Matteo (EV2)
    def check(self, text: str, mapping: dict[str, str]) -> str: ...


class ContextProvider(Protocol):                # Timothée (profil M1, patients M3, RAG R1)
    def provide(self, query: str, session_id: str) -> list[Message]: ...


class SessionStore(Protocol):                   # Timothée (M1)
    def load(self, session_id: str) -> list[Message]: ...
    def save(self, session_id: str, history: list[Message]) -> None: ...
    def list(self) -> list[str]: ...


@dataclass
class ToolResult:
    content: str
    is_error: bool = False


class ToolRegistry(Protocol):                   # Matteo (T1)
    def schemas(self) -> list[dict]: ...        # format "tools" d'Ollama
    def is_dangerous(self, name: str) -> bool: ...  # True => validation humaine (A3)
    def call(self, name: str, args: dict) -> ToolResult: ...


@dataclass
class Event:                                    # émis par le pipeline, lu par CLI et web
    type: Literal["token", "tool_call", "tool_result", "confirm",
                  "usage", "error", "done"]
    data: Any = None


ConfirmFn = Callable[[str, str, dict], bool]    # (id, outil, args) -> accepté ?
