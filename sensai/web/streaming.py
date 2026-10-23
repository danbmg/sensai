"""Relais des Event du pipeline vers le navigateur en SSE (Server-Sent Events).

Le pipeline est un générateur synchrone qui peut bloquer longtemps : Ollama met parfois
une minute à répondre, et confirm() attend le clic du médecin. Il tourne donc dans son
propre thread, qui pousse chaque Event dans une file asyncio ; la boucle du serveur reste
libre pour traiter POST /api/confirm pendant ce temps.

Si le navigateur se déconnecte (bouton Arrêter, onglet fermé), le thread est prévenu :
les confirmations en attente sont refusées et le générateur est fermé, ce qui ferme
le flux Ollama (le modèle arrête de générer).
"""
import asyncio
import json
import threading
from dataclasses import dataclass, field
from typing import AsyncIterator, Iterator

from sensai.core.interfaces import Event
from sensai.web.confirmations import Confirmations

BUSY = "Une réponse est déjà en cours dans cette session."


def sse(event: Event) -> str:
    """Format SSE : « event: <type> » puis « data: <json> », terminé par une ligne vide."""
    return f"event: {event.type}\ndata: {json.dumps(event.data, ensure_ascii=False)}\n\n"


@dataclass
class EventStream:
    events: Iterator[Event]
    confirmations: Confirmations
    session_lock: threading.Lock    # un tour à la fois par session
    wait: float = 0.0               # délai accordé au tour précédent pour libérer la session
    _stop: threading.Event = field(default_factory=threading.Event)
    _opened: set[str] = field(default_factory=set)

    async def __aiter__(self) -> AsyncIterator[str]:
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[Event | None] = asyncio.Queue()

        def push(item: Event | None) -> None:
            try:
                loop.call_soon_threadsafe(queue.put_nowait, item)
            except RuntimeError:        # serveur arrêté pendant le tour
                pass

        def produce() -> None:
            # Le verrou est pris ici, pas dans la route : si le navigateur part avant que le
            # flux démarre, ce thread n'existe pas et la session n'est jamais bloquée.
            if not self.session_lock.acquire(timeout=self.wait):
                push(Event("error", BUSY))
                push(None)
                return
            try:
                for event in self.events:
                    if event.type == "confirm":
                        self._opened.add(event.data["id"])
                        self.confirmations.open(event.data["id"])
                    push(event)
                    if self._stop.is_set():
                        break
            except Exception as error:      # le pipeline rattrape déjà ses erreurs : filet de sécurité
                push(Event("error", f"Erreur interne : {error}"))
            finally:
                self.events.close()
                self.session_lock.release()
                push(None)

        threading.Thread(target=produce, name="sensai-turn", daemon=True).start()
        try:
            while (event := await queue.get()) is not None:
                yield sse(event)
        finally:
            self._stop.set()
            for call_id in list(self._opened):  # déconnexion : une action en attente est refusée
                self.confirmations.resolve(call_id, False)
