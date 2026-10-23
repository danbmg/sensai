"""Pont thread -> SSE : verrou de session, format des événements, refus à la déconnexion."""
import asyncio
import threading

from sensai.core.interfaces import Event
from sensai.web.confirmations import Confirmations
from sensai.web.streaming import BUSY, EventStream, sse


def collect(stream: EventStream) -> list[str]:
    async def run():
        return [chunk async for chunk in stream]
    return asyncio.run(run())


def test_sse_format():
    assert sse(Event("token", "Bonjour « Mme »")) == 'event: token\ndata: "Bonjour « Mme »"\n\n'
    assert sse(Event("done")) == "event: done\ndata: null\n\n"


def test_stream_takes_and_releases_the_session_lock():
    lock = threading.Lock()
    seen = []

    def events():
        seen.append(lock.locked())      # le tour tourne verrou pris
        yield Event("token", "ok")
        yield Event("done")

    assert collect(EventStream(events(), Confirmations(), lock)) == [sse(Event("token", "ok")), sse(Event("done"))]
    assert seen == [True] and not lock.locked()


def test_unconsumed_stream_never_locks_the_session():
    lock = threading.Lock()
    EventStream(iter([Event("done")]), Confirmations(), lock)     # navigateur parti avant le flux

    assert not lock.locked()


def test_busy_session_reports_an_error_event():
    lock = threading.Lock()
    lock.acquire()
    started = []

    def events():
        started.append(True)
        yield Event("done")

    assert collect(EventStream(events(), Confirmations(), lock, wait=0.05)) == [sse(Event("error", BUSY))]
    assert started == []


def test_confirmation_waits_for_the_decision_and_times_out():
    confirmations = Confirmations(timeout=0.05)
    assert confirmations.wait("a", "add_patient_note", {}) is False           # délai dépassé : refus
    confirmations.open("b")
    assert confirmations.resolve("b", True)
    assert confirmations.wait("b", "add_patient_note", {}) is True            # clic arrivé avant l'attente
    assert not confirmations.resolve("b", True)                               # déjà décidée
    assert confirmations.pending() == []
