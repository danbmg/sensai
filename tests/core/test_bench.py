"""bench_models.py contre un faux serveur Ollama local : aucun vrai modèle n'est lancé."""
import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

import bench_models

DONE = {"done": True, "load_duration": 1_000_000_000,
        "prompt_eval_count": 800, "prompt_eval_duration": 4_000_000_000,
        "eval_count": 40, "eval_duration": 2_000_000_000}
NOTE_CALL = {"function": {"name": "add_patient_note",
                          "arguments": {"patient": "[PATIENT_1]", "note": "Allergie aux pénicillines."}}}


def chunk(content="", **message):
    return {"message": {"role": "assistant", "content": content, **message}, "done": False}


def has_tool_result(messages):
    return any(m["role"] == "tool" for m in messages)


# Comportements du faux modèle : messages reçus -> lignes NDJSON (un nombre = pause en secondes)
def normal(messages):
    if not has_tool_result(messages):
        return [chunk(tool_calls=[NOTE_CALL]), DONE]
    return [chunk("Non : "), chunk("allergie aux pénicillines, note ajoutée."), DONE]


def ignores_tool(messages):
    return [chunk("Oui, "), chunk("sans problème."), DONE]


def stalls(messages):
    return [chunk("Je "), 3]                      # plus rien pendant 3 s


def rambles(messages):
    return [x for _ in range(100) for x in (chunk("bla "), 0.02)]   # 2 s sans jamais finir


class FakeOllama(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _json(self, status, payload):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._json(200, {"models": [{"name": name} for name in self.server.models]})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.server.bodies.append((self.path, body))
        model = self.server.models.get(body["model"])
        if model is None:
            return self._json(404, {"error": f"model '{body['model']}' not found"})
        capabilities, behaviour = model
        if self.path == "/api/show":
            return self._json(200, {"capabilities": capabilities})

        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.end_headers()
        try:
            for line in behaviour(body["messages"]):
                if isinstance(line, (int, float)):
                    time.sleep(line)
                    continue
                self.wfile.write(json.dumps(line).encode() + b"\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass                                  # le bench a coupé la connexion (timeout)


@pytest.fixture
def ollama():
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeOllama)
    server.models, server.bodies = {}, []
    threading.Thread(target=server.serve_forever, args=(0.02,), daemon=True).start()
    yield server
    server.shutdown()
    server.server_close()


@pytest.fixture
def bench(ollama, capsys):
    """Lance le bench ; renvoie (code retour, {modèle: cellules du tableau}, stderr)."""
    def run(*models, host=None):
        host = host or f"http://127.0.0.1:{ollama.server_port}"
        code = bench_models.main([*models, "--host", host, "--runs", "2", "--timeout", "0.5"])
        out = capsys.readouterr()
        rows = {}
        for line in out.out.splitlines():
            if line.startswith("| `"):
                cells = [c.strip() for c in line.strip("|").split("|")]
                rows[cells[0].split("`")[1]] = cells
        return code, rows, out.err
    return run


TOOLS = ["completion", "tools"]


def test_normal_model_passes(ollama, bench):
    ollama.models["ok"] = (TOOLS, normal)
    code, rows, _ = bench("ok")

    name, verdict, *_, tool, answer = rows["ok"]
    assert code == 0
    assert (verdict, tool, answer) == ("✅", "✅", "✅")
    assert rows["ok"][5:8] == ["200", "20.0", "800"]   # 800 tok / 4 s, 40 tok / 2 s, prompt


def test_turn_sends_tool_result_back(ollama, bench):
    ollama.models["ok"] = (TOOLS, normal)
    bench("ok")

    chats = [body for path, body in ollama.bodies if path == "/api/chat"]
    assert len(chats) == 4                                   # 2 tours x 2 appels
    assert chats[0]["options"] == {"temperature": 0, "num_ctx": 4096}
    assert chats[0]["tools"][0]["function"]["name"] == "add_patient_note"
    assert "think" not in chats[0]
    assert chats[1]["messages"][-1] == {"role": "tool", "tool_name": "add_patient_note",
                                        "content": bench_models.TOOL_RESULT}


def test_thinking_model_flagged_and_think_disabled(ollama, bench):
    ollama.models["thinker"] = (TOOLS + ["thinking"], normal)
    _, rows, _ = bench("thinker")

    assert "⚠ thinking" in rows["thinker"][0]
    chats = [body for path, body in ollama.bodies if path == "/api/chat"]
    assert chats and all(body["think"] is False for body in chats)


def test_model_without_tools_is_skipped(ollama, bench):
    ollama.models["notools"] = (["completion"], normal)
    _, rows, _ = bench("notools")

    assert "ignoré" in rows["notools"][1]
    assert not [path for path, _ in ollama.bodies if path == "/api/chat"]


def test_missing_model_reported(ollama, bench):
    _, rows, _ = bench("absent:1b")

    assert rows["absent:1b"][1] == "absent : `ollama pull absent:1b`"


def test_model_ignoring_tool_fails(ollama, bench):
    ollama.models["lazy"] = (TOOLS, ignores_tool)
    _, rows, _ = bench("lazy")

    _, verdict, *_, tool, answer = rows["lazy"]
    assert (verdict, tool, answer) == ("❌", "❌", "❌")


@pytest.mark.parametrize("behaviour", [stalls, rambles], ids=["silence", "never_ends"])
def test_timeout_reported(ollama, bench, behaviour):
    ollama.models["slow"] = (TOOLS, behaviour)
    start = time.monotonic()
    code, rows, _ = bench("slow")

    assert code == 0
    assert rows["slow"][1] == "❌ timeout (> 0.5 s)"
    assert time.monotonic() - start < 2.5        # abandonné, pas attendu jusqu'au bout


def test_other_models_still_measured_after_failures(ollama, bench):
    ollama.models["ok"] = (TOOLS, normal)
    ollama.models["slow"] = (TOOLS, stalls)
    _, rows, _ = bench("absent:1b", "slow", "ok")

    assert list(rows) == ["absent:1b", "slow", "ok"]
    assert rows["ok"][1] == "✅"


def test_ollama_down(bench):
    with socket.socket() as s:                   # port libre, personne n'écoute
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    code, rows, err = bench("ok", host=f"http://127.0.0.1:{port}")

    assert code == 1
    assert rows == {}
    assert "Ollama ne répond pas" in err


def test_over_budget_fails_verdict():
    fast_ok = bench_models.Run(first_fragment_s=1, turn_s=10, load_s=0, prompt_tokens=800,
                               prompt_tps=100, gen_tps=10, tool_ok=True, answer_ok=True)
    slow_ok = bench_models.Run(**{**vars(fast_ok), "turn_s": 45})
    result = bench_models.ModelResult("m", runs=[fast_ok, slow_ok, slow_ok])

    assert bench_models.summarize(result, budget=30)[1] == "❌"
    assert bench_models.summarize(result, budget=60)[1] == "✅"


def test_single_run_is_used_when_no_warm_run():
    run = bench_models.Run(first_fragment_s=1, turn_s=12, load_s=3, prompt_tokens=800,
                           prompt_tps=100, gen_tps=10, tool_ok=True, answer_ok=True)
    row = bench_models.summarize(bench_models.ModelResult("m", runs=[run]), budget=30)

    assert row[1:3] == ["✅", "12.0"]


@pytest.mark.parametrize("calls, expected", [
    ([NOTE_CALL], True),
    ([{"function": {"name": "add_patient_note",
                    "arguments": {"patient": " [PATIENT_1] ", "note": "[PATIENT_1] : allergie."}}}], True),
    ([{"function": {"name": "add_patient_note", "arguments": {"patient": "[PATIENT_1]"}}}], False),
    ([{"function": {"name": "add_patient_note",     # vu avec llama3.2:1b : schéma recopié
                    "arguments": {"patient": "[PATIENT_1]",
                                  "note": '{"type":"string","description":"Amoxicilline non recommandée"}'}}}],
     False),
    ([{"function": {"name": "add_patient_note", "arguments": {"patient": "Jeanne Dupont"}}}], False),
    ([{"function": {"name": "other_tool", "arguments": {"patient": "[PATIENT_1]"}}}], False),
    ([{"function": {"name": "add_patient_note", "arguments": "[PATIENT_1]"}}], False),
    ([], False),
])
def test_tool_ok(calls, expected):
    assert bench_models.tool_ok(calls) is expected


@pytest.mark.parametrize("text, expected", [
    ("Non, elle est allergique.", True),
    ("Contre-indiquée : PÉNICILLINES.", True),
    ("Oui, aucun problème.", False),
])
def test_answer_ok(text, expected):
    assert bench_models.answer_ok(text) is expected


def test_context_is_pseudonymized():
    text = json.dumps(bench_models.build_messages("Tu es Sensai.", 0), ensure_ascii=False)

    for pseudonym in ("[PATIENT_1]", "[NAISSANCE_1]", "[ADRESSE_1]"):
        assert pseudonym in text
    assert "Dupont" not in text
