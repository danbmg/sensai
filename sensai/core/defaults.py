"""Implémentations neutres des interfaces, prises par le Pipeline quand un module manque."""
import copy

from sensai.core.interfaces import GuardResult, Message, SessionState, ToolResult


class NullGuard:                        # remplace l'InputGuard de Matteo
    def check(self, text: str) -> GuardResult:
        """Laisse tout passer."""
        return GuardResult()


class NullOutputGuard:                  # remplace l'OutputGuard de Matteo
    def check(self, text: str) -> str:
        """Renvoie la réponse telle quelle."""
        return text


class NullVault:                        # remplace le PIIVault de Matteo : aucune pseudonymisation
    """La classe sert aussi de VaultFactory : NullVault(pii_map) recrée le coffre."""

    def __init__(self, pii_map: dict[str, str] | None = None):
        """Garde la table reçue pour la rendre telle quelle à export()."""
        self.pii_map = dict(pii_map or {})

    def mask(self, text: str) -> str:
        """Ne masque rien."""
        return text

    def reveal(self, text: str) -> str:
        """Ne ré-identifie rien."""
        return text

    def reveal_args(self, args: dict) -> dict:
        """Renvoie les arguments tels quels."""
        return args

    def export(self) -> dict[str, str]:
        """Renvoie une copie de la table reçue."""
        return dict(self.pii_map)


class EmptyContext:                     # remplace le ContextProvider de Timothée
    def provide(self, query: str, masked_query: str, session_id: str) -> list[Message]:
        """N'ajoute aucun contexte."""
        return []


class EmptyRegistry:                    # remplace le ToolRegistry de Matteo : aucun outil
    def schemas(self) -> list[dict]:
        """Aucun outil proposé au modèle."""
        return []

    def is_dangerous(self, name: str) -> bool:
        """Aucun outil, donc rien à confirmer."""
        return False

    def call(self, name: str, args: dict) -> ToolResult:
        """Tout appel échoue : aucun outil n'existe."""
        return ToolResult(f"Outil inconnu : {name}", is_error=True)


class InMemorySessionStore:             # remplace le SessionStore de Timothée (perdu à l'arrêt)
    def __init__(self):
        """Sessions gardées en mémoire, indexées par identifiant."""
        self._sessions: dict[str, SessionState] = {}

    def load(self, session_id: str) -> SessionState:
        """Renvoie une copie : un état modifié sans save() ne change rien, comme en base."""
        return copy.deepcopy(self._sessions.get(session_id, SessionState()))

    def save(self, session_id: str, state: SessionState) -> None:
        """Enregistre une copie de l'état."""
        self._sessions[session_id] = copy.deepcopy(state)

    def list_sessions(self) -> list[str]:
        """Identifiants des sessions enregistrées."""
        return list(self._sessions)
