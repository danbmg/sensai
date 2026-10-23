"""Validation humaine (A3) et interruption, avec un vrai serveur HTTP (uvicorn) et un faux Ollama.

TestClient lit une réponse en entier avant de la rendre : impossible d'y cliquer « Valider »
pendant le flux. Ici, le flux SSE est lu au fil de l'eau, comme le fait le navigateur.
"""
import json
import threading
import time

import pytest
import requests
import uvicorn

from sensai.memory.patients import PatientStore
from sensai.memory.sessions import SQLiteSessionStore
from sensai.web.api import create_app

NOTE_REQUEST = "Ajoute une note au dossier : allergie à la pénicilline documentée."


@pytest.fixture
def live(options):
    """URL d'un serveur Sensai lancé dans un thread ; délai de confirmation court."""
    def start(confirm_timeout=30.0):
        server = uvicorn.Server(uvicorn.Config(create_app(options, confirm_timeout=confirm_timeout),
                                               host="127.0.0.1", port=0, log_level="warning"))
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        while not server.started:
            time.sleep(0.01)
        servers.append((server, thread))
        return f"http://127.0.0.1:{server.servers[0].sockets[0].getsockname()[1]}"
    servers = []
    yield start
    for server, thread in servers:
        server.should_exit = True
        thread.join(10)


def sse(response):
    kind = None
    for line in response.iter_lines(decode_unicode=True):
        if line.startswith("event: "):
            kind = line[7:]
        elif line.startswith("data: "):
            yield kind, json.loads(line[6:])


def new_session(url):
    return requests.post(f"{url}/api/sessions", json={"patient": "demo-dupont"}, timeout=5).json()["session_id"]


def chat(url, session_id, message, on_confirm=None):
    """Lit le tour au fil de l'eau ; `on_confirm(data)` est appelé dès l'événement confirm."""
    received = []
    with requests.post(f"{url}/api/chat", json={"session_id": session_id, "message": message},
                       stream=True, timeout=30) as response:
        assert response.status_code == 200, response.text
        for kind, data in sse(response):
            received.append((kind, data))
            if kind == "confirm" and on_confirm:
                on_confirm(data)
    return received


def notes(options):
    return PatientStore(options.db).get_patient("demo-dupont")["notes"]


@pytest.mark.parametrize("approved", [True, False], ids=["validée", "refusée"])
def test_doctor_decides_in_the_browser(live, options, approved):
    url = live()
    session_id = new_session(url)
    before = notes(options)
    shown = []

    def click(data):
        shown.append(data)
        answer = requests.post(f"{url}/api/confirm/{data['id']}", json={"approved": approved}, timeout=5)
        assert answer.status_code == 200

    received = chat(url, session_id, NOTE_REQUEST, click)

    kinds = [kind for kind, _ in received]
    assert kinds[:3] == ["tool_call", "confirm", "tool_result"] and kinds[-1] == "done"
    assert shown[0]["args"]["patient"] == "Jeanne Dupont"      # le médecin voit le vrai nom
    answer = "".join(data for kind, data in received if kind == "token")
    if approved:
        assert notes(options) == before + ["Allergie à la pénicilline documentée."]
        assert answer == "Note ajoutée au dossier de Jeanne Dupont."
    else:
        assert notes(options) == before
        assert answer.startswith("Action annulée à votre demande")


def test_no_answer_before_timeout_means_refused(live, options):
    url = live(confirm_timeout=0.5)
    before = notes(options)

    received = chat(url, new_session(url), NOTE_REQUEST)

    assert ("tool_result", "Action refusée par le médecin") in [(k, d.get("content") if isinstance(d, dict) else d)
                                                                 for k, d in received]
    assert notes(options) == before


def wait_until_free(url, session_id, deadline=5.0):
    """Le tour abandonné libère la session : un nouveau tour est accepté (pas de 409)."""
    end = time.monotonic() + deadline
    while time.monotonic() < end:
        response = requests.post(f"{url}/api/chat", json={"session_id": session_id, "message": "Bonjour"},
                                 timeout=10)
        if response.status_code != 409:
            return response
        time.sleep(0.05)
    raise AssertionError("session toujours occupée")


def test_closing_the_page_while_waiting_refuses_the_action(live, options):
    url = live(confirm_timeout=60)
    session_id = new_session(url)
    before = notes(options)
    with requests.post(f"{url}/api/chat", json={"session_id": session_id, "message": NOTE_REQUEST},
                       stream=True, timeout=30) as response:
        for kind, _ in sse(response):
            if kind == "confirm":
                break               # onglet fermé pendant que la modale attend

    started = time.monotonic()
    assert wait_until_free(url, session_id).status_code == 200
    assert time.monotonic() - started < 5      # libérée tout de suite, sans attendre les 60 s
    assert notes(options) == before


def test_stop_button_interrupts_generation(live, options, ollama):
    url = live()
    session_id = new_session(url)
    ollama.slowdown = 2.0       # ~0,1 s entre deux fragments
    interrupted = ollama.interrupted
    try:
        with requests.post(f"{url}/api/chat", json={"session_id": session_id,
                                                     "message": "Mme Dupont peut-elle prendre de l'amoxicilline ?"},
                           stream=True, timeout=30) as response:
            for kind, _ in sse(response):
                if kind == "token":
                    break           # bouton Arrêter : le navigateur coupe la connexion
        end = time.monotonic() + 5
        while ollama.interrupted == interrupted and time.monotonic() < end:
            time.sleep(0.05)
    finally:
        ollama.slowdown = 0
    assert ollama.interrupted == interrupted + 1        # le flux Ollama a été fermé
    assert SQLiteSessionStore(options.db).load(session_id).history == []   # tour non enregistré
    assert wait_until_free(url, session_id).status_code == 200
