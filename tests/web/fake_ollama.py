"""Faux serveur Ollama HTTP pour les tests de bout en bout du web : aucun vrai modèle.

Il joue le scénario du Dr Martin à partir des messages reçus (déjà pseudonymisés) :
- une demande de note → appel de add_patient_note pour [PATIENT_1], puis confirmation ;
- une question sur l'amoxicilline avec l'allergie au dossier → « Non », en citant [S1] ;
- sinon, une réponse courte.
Lancement manuel : python -m tests.web.fake_ollama --port 11500
"""
import argparse
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MODELS = {"qwen2.5:3b": ["completion", "tools"], "llama3.2:3b": ["completion", "tools"],
          "qwen3:4b": ["completion", "tools", "thinking"], "qwen2:0.5b": ["completion"]}


def reply(body: dict) -> list:
    """Lignes NDJSON (dict) et pauses (nombre de secondes) pour une requête /api/chat."""
    messages = body["messages"]
    tools = [tool["function"]["name"] for tool in body.get("tools", [])]
    user = next(m["content"] for m in reversed(messages) if m["role"] == "user").casefold()
    context = " ".join(m["content"] for m in messages if m["role"] == "system").casefold()
    prompt_tokens = sum(len(m["content"]) for m in messages) // 4
    if any(m["role"] == "tool" for m in messages[-2:]):
        words = ["Note ", "ajoutée ", "au ", "dossier ", "de ", "[PATI", "ENT_1]."]
    elif "note" in user and "add_patient_note" in tools:
        return [{"message": {"role": "assistant", "content": "", "tool_calls": [{"function": {
            "name": "add_patient_note",
            "arguments": {"patient": "[PATIENT_1]", "note": "Allergie à la pénicilline documentée."}}}]},
            "done": False}, done(prompt_tokens, 12)]
    elif "amoxicilline" in user and "pénicilline" in context:
        words = ["Non. ", "[PATIENT_1] ", "est ", "allergique ", "à ", "la ", "pénicilline ",
                 "(dossier local), ", "et ", "l'amoxicilline ", "est ", "une ", "pénicilline ", "[S1]."]
    else:
        words = ["Réponse ", "de ", "test."]
    lines: list = []
    for word in words:
        lines += [{"message": {"role": "assistant", "content": word}, "done": False}, 0.05]
    return lines + [done(prompt_tokens, len(words))]


def done(prompt_tokens: int, completion_tokens: int) -> dict:
    return {"message": {"role": "assistant", "content": ""}, "done": True,
            "prompt_eval_count": prompt_tokens, "eval_count": completion_tokens,
            "load_duration": 10**8, "prompt_eval_duration": 10**8, "eval_duration": 10**8}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"   # comme Ollama : flux en « chunked », un fragment après l'autre

    def log_message(self, *args):
        pass

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._json(200, {"models": [{"name": name} for name in MODELS]})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.server.requests.append((self.path, body))
        if self.path == "/api/embed":       # RAG : même vecteur pour toutes les requêtes
            return self._json(200, {"embeddings": [[1.0, 0.0] for _ in body["input"]]})
        if body.get("model") not in MODELS:
            return self._json(404, {"error": f"model '{body.get('model')}' not found"})
        if self.path == "/api/show":
            return self._json(200, {"capabilities": MODELS[body["model"]]})
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        try:
            for line in reply(body):
                if isinstance(line, (int, float)):
                    time.sleep(line * self.server.slowdown)
                    continue
                data = json.dumps(line).encode() + b"\n"
                self.wfile.write(f"{len(data):x}\r\n".encode() + data + b"\r\n")
                self.wfile.flush()
            self.wfile.write(b"0\r\n\r\n")
        except (BrokenPipeError, ConnectionResetError):
            self.server.interrupted += 1        # le client a fermé le flux : génération arrêtée


def start(port: int = 0, slowdown: float = 1.0) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.requests, server.interrupted, server.slowdown = [], 0, slowdown
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=11500)
    parser.add_argument("--slowdown", type=float, default=1.0, help="multiplie les pauses entre fragments")
    args = parser.parse_args()
    server = start(args.port, args.slowdown)
    print(f"Faux Ollama sur http://127.0.0.1:{server.server_address[1]}")
    threading.Event().wait()
