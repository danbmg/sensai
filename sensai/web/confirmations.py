"""Validation humaine côté web (A3) : le pipeline attend, POST /api/confirm/{id} décide.

Le pipeline appelle confirm() dans le thread du tour et bloque ; le clic du médecin
arrive par une autre requête HTTP. Sans réponse avant le délai, l'action est refusée.
"""
import threading
from dataclasses import dataclass, field


@dataclass
class _Pending:
    decided: threading.Event = field(default_factory=threading.Event)
    approved: bool = False


class Confirmations:
    def __init__(self, timeout: float = 120.0):
        self.timeout = timeout
        self._pending: dict[str, _Pending] = {}
        self._lock = threading.Lock()

    def open(self, call_id: str) -> None:
        """Ouvre l'attente AVANT d'envoyer l'événement « confirm » : un clic rapide n'est pas perdu."""
        with self._lock:
            self._pending.setdefault(call_id, _Pending())

    def wait(self, call_id: str, tool: str, args: dict) -> bool:
        """ConfirmFn du pipeline : bloque jusqu'à la décision ; refus si délai dépassé."""
        self.open(call_id)
        pending = self._pending[call_id]
        decided = pending.decided.wait(self.timeout)
        with self._lock:
            self._pending.pop(call_id, None)
        return decided and pending.approved

    def resolve(self, call_id: str, approved: bool) -> bool:
        """Décision du médecin ; False si l'action est inconnue ou n'attend plus."""
        with self._lock:
            pending = self._pending.get(call_id)
        if pending is None:
            return False
        pending.approved = approved
        pending.decided.set()
        return True

    def pending(self) -> list[str]:
        with self._lock:
            return list(self._pending)
