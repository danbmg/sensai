"""Implémentations neutres des interfaces, en attendant les vrais modules (étape 10)."""
import copy

from sensai.core.interfaces import GuardResult, Message, SessionState, ToolResult


class NullGuard:                        # remplace l'InputGuard de Matteo
    def check(self, text: str) -> GuardResult:
        return GuardResult()            # laisse tout passer


class NullOutputGuard:                  # remplace l'OutputGuard de Matteo
    def check(self, text: str) -> str:
        return text


class NullVault:                        # remplace le PIIVault de Matteo : aucune pseudonymisation
    """La classe sert aussi de VaultFactory : NullVault(pii_map) recrée le coffre."""

    def __init__(self, pii_map: dict[str, str] | None = None):
        self.pii_map = dict(pii_map or {})

    def mask(self, text: str) -> str:
        return text

    def reveal(self, text: str) -> str:
        return text

    def reveal_args(self, args: dict) -> dict:
        return args

    def export(self) -> dict[str, str]:
        return dict(self.pii_map)


class EmptyContext:                     # remplace le ContextProvider de Timothée
    def provide(self, query: str, masked_query: str, session_id: str) -> list[Message]:
        return []


class EmptyRegistry:                    # remplace le ToolRegistry de Matteo : aucun outil
    def schemas(self) -> list[dict]:
        return []

    def is_dangerous(self, name: str) -> bool:
        return False

    def call(self, name: str, args: dict) -> ToolResult:
        return ToolResult(f"Outil inconnu : {name}", is_error=True)


class InMemorySessionStore:             # remplace le SessionStore de Timothée (perdu à l'arrêt)
    def __init__(self):
        self._sessions: dict[str, SessionState] = {}

    # Copies : comme un vrai stockage, un état modifié sans save() ne change rien.
    def load(self, session_id: str) -> SessionState:
        return copy.deepcopy(self._sessions.get(session_id, SessionState()))

    def save(self, session_id: str, state: SessionState) -> None:
        self._sessions[session_id] = copy.deepcopy(state)

    def list_sessions(self) -> list[str]:
        return list(self._sessions)
