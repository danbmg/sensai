import copy
import json
from dataclasses import asdict

import pytest
import requests

from sensai.core.defaults import InMemorySessionStore
from sensai.core.interfaces import Event, GuardResult, ToolResult
from sensai.core.ollama_client import ChatChunk
from sensai.core.pipeline import CANCELLED, REFUSED, Pipeline, _DisplayBuffer

# --- Doublures ---

DIRECTORY = {   # valeur réelle -> (type, variantes de la plus longue à la plus courte)
    "Jeanne Dupont": ("PATIENT", ["Mme Jeanne Dupont", "Jeanne Dupont", "Mme Dupont", "Dupont"]),
    "Louis Bernard": ("PATIENT", ["Louis Bernard", "M. Bernard"]),
    "12/03/1958": ("NAISSANCE", ["12/03/1958"]),
    "3 rue des Lilas, 69003 Lyon": ("ADRESSE", ["3 rue des Lilas, 69003 Lyon"]),
    "06 12 34 56 78": ("TEL", ["06 12 34 56 78"]),
}
SECRETS = ["Dupont", "Bernard", "12/03/1958", "Lilas", "06 12 34 56 78"]


class FakeVault:
    """PIIVault minimal conforme au contrat : variantes -> même pseudonyme, idempotent."""

    def __init__(self, pii_map):
        self.pii_map = dict(pii_map)

    def _pseudonym(self, value, kind):
        for pseudonym, real in self.pii_map.items():
            if real == value:
                return pseudonym
        pseudonym = f"[{kind}_{1 + sum(p.startswith(f'[{kind}_') for p in self.pii_map)}]"
        self.pii_map[pseudonym] = value
        return pseudonym

    def mask(self, text):
        for value, (kind, variants) in DIRECTORY.items():
            for variant in variants:
                if variant in text:
                    text = text.replace(variant, self._pseudonym(value, kind))
        return text

    def reveal(self, text):
        for pseudonym, real in self.pii_map.items():
            text = text.replace(pseudonym, real)
        return text

    def reveal_args(self, args):
        return {k: self.reveal(v) if isinstance(v, str) else v for k, v in args.items()}

    def export(self):
        return dict(self.pii_map)


class FakeModel:
    """Faux OllamaClient : une liste de fragments par appel (str = contenu, exception = levée)."""
    model, host, timeout = "fake-model", "http://h:1", 120.0

    def __init__(self, *replies):
        self.replies, self.calls, self.tools, self.closed = list(replies), [], [], 0

    def chat_stream(self, messages, tools=None):
        self.calls.append(copy.deepcopy(messages))
        self.tools.append(tools)
        try:
            for item in self.replies[len(self.calls) - 1]:
                if isinstance(item, BaseException):
                    raise item
                yield ChatChunk(content=item) if isinstance(item, str) else item
        finally:
            self.closed += 1


def tool_call(name, **args):
    return ChatChunk(tool_calls=[{"function": {"name": name, "arguments": args}}])


class FakeContext:
    def __init__(self, *per_call):              # contexte renvoyé à chaque appel, puis []
        self.per_call, self.calls = list(per_call), []

    def provide(self, query, masked_query, session_id):
        self.calls.append((query, masked_query, session_id))
        return copy.deepcopy(self.per_call[len(self.calls) - 1]) if len(self.calls) <= len(
            self.per_call) else []


class FakeRegistry:
    def __init__(self, dangerous=("add_patient_note",), result="Note ajoutée.", error=None):
        self.dangerous, self.result, self.error, self.calls = dangerous, result, error, []

    def schemas(self):
        return [{"type": "function", "function": {"name": "add_patient_note"}}]

    def is_dangerous(self, name):
        return name in self.dangerous

    def call(self, name, args):
        self.calls.append((name, args))
        if self.error:
            raise self.error
        return ToolResult(self.result)


class Confirm:
    def __init__(self, answer=True):
        self.answer, self.calls = answer, []

    def __call__(self, call_id, tool, args):
        self.calls.append((call_id, tool, args))
        return self.answer


class BlockAll:
    def check(self, text):
        return GuardResult(blocked=True, reason="Hors périmètre médical.")


def run(pipeline, text, session_id="s1", confirm=None):
    return list(pipeline.run(text, session_id, confirm or Confirm()))


def tokens(events):
    return "".join(e.data for e in events if e.type == "token")


def types(events):
    return [e.type for e in events]


# --- Frontière PII (test clé de l'étape 5) ---

def test_pii_never_leaves_the_clear_side():
    model = FakeModel(
        # tour 1, appel 1 : pseudonyme coupé, nom écrit en clair et coupé, « [ » isolé, outil
        ["Non : [PATI", "ENT_1] est allergique. Mme Dup", "ont ne doit pas en prendre [",
         "notice ANSM]. ",
         tool_call("add_patient_note", patient="[PATIENT_1]", note="Allergie pénicillines")],
        ["Note ajoutée pour [PATIENT_1]."],                         # tour 1, après l'outil
        ["[PATIENT_2] n'a pas d'allergie ; [PATIENT_1] habite [ADRESSE_1]."],  # tour 2
    )
    context = FakeContext([{"role": "system", "content": "Dossier de Jeanne Dupont, née le "
                            "12/03/1958, 3 rue des Lilas, 69003 Lyon. Allergie : pénicillines."}])
    registry = FakeRegistry(result="Note ajoutée au dossier de Jeanne Dupont (tél. 06 12 34 56 78).")
    sessions, records, confirm = InMemorySessionStore(), [], Confirm()
    pipeline = Pipeline(model, "Tu es Sensai.", vault_factory=FakeVault, context=context,
                        sessions=sessions, tools=registry, on_turn=records.append)

    turn1 = run(pipeline, "Mme Dupont (06 12 34 56 78) peut-elle prendre de l'amoxicilline ?",
                confirm=confirm)
    turn2 = run(pipeline, "Et Louis Bernard ?", confirm=confirm)

    # Côté pseudonymisé : modèle, requête d'embedding, historique, logs.
    history = sessions.load("s1").history
    pseudonymized = json.dumps([model.calls, [masked for _, masked, _ in context.calls],
                                history, [asdict(r) for r in records]], ensure_ascii=False)
    for secret in SECRETS:
        assert secret not in pseudonymized
    # Le nom écrit en clair et coupé entre deux fragments est rattrapé sur la réponse complète.
    assert history[1]["content"] == ("Non : [PATIENT_1] est allergique. [PATIENT_1] ne doit pas "
                                     "en prendre [notice ANSM]. ")

    # Côté clair : outil, confirmation, affichage.
    assert context.calls[0][0].startswith("Mme Dupont (06 12 34 56 78)")
    assert registry.calls == [("add_patient_note",
                               {"patient": "Jeanne Dupont", "note": "Allergie pénicillines"})]
    assert confirm.calls[0][2]["patient"] == "Jeanne Dupont"
    assert tokens(turn1) == ("Non : Jeanne Dupont est allergique. Mme Dupont ne doit pas en prendre "
                             "[notice ANSM]. Note ajoutée pour Jeanne Dupont.")

    # Tour suivant : [PATIENT_1] reste Jeanne Dupont, le nouveau patient devient [PATIENT_2],
    # et l'adresse vue au tour 1 (contexte vide au tour 2) se ré-identifie encore.
    assert model.calls[2][-1] == {"role": "user", "content": "Et [PATIENT_2] ?"}
    assert tokens(turn2) == ("Louis Bernard n'a pas d'allergie ; Jeanne Dupont habite "
                             "3 rue des Lilas, 69003 Lyon.")


# --- Tampon d'affichage ---

@pytest.fixture
def display():
    return _DisplayBuffer(lambda text: text.replace("[PATIENT_1]", "Jeanne Dupont")
                                            .replace("[PATIENT_12]", "Louis Bernard"))


def test_buffer_holds_split_pseudonym(display):
    assert display.feed("Non : [PATI") == "Non : "
    assert display.feed("ENT_1] est allergique") == "Jeanne Dupont est allergique"


def test_buffer_holds_while_digits_arrive(display):
    assert display.feed("[PATIENT_1") == ""
    assert display.feed("2] ok") == "Louis Bernard ok"


@pytest.mark.parametrize("fragment", ["[1", "[Notice", "[patient_1", "[PATIENTE", "[ x"])
def test_buffer_releases_bracket_that_cannot_be_a_pseudonym(display, fragment):
    assert display.feed("voir [") == "voir "
    assert display.feed(fragment[1:]) == fragment


def test_buffer_caps_held_text(display):
    long = "[PATIENT_" + "1" * 30
    assert display.feed(long) == long


def test_buffer_flush_returns_held_text(display):
    assert display.feed("fin [") == "fin "
    assert display.flush() == "["
    assert display.flush() == ""


# --- Déroulé d'un tour ---

def test_blocked_input_stops_before_model():
    model, sessions = FakeModel(), InMemorySessionStore()
    events = run(Pipeline(model, input_guard=BlockAll(), sessions=sessions), "Recette de crêpes ?")

    assert events == [Event("error", "Hors périmètre médical.")]
    assert model.calls == [] and sessions.list_sessions() == []


def test_messages_sent_in_order_and_context_not_stored():
    model = FakeModel(["Réponse 1"], ["Réponse 2"])
    context = FakeContext([{"role": "system", "content": "Contexte 1"}],
                          [{"role": "system", "content": "Contexte 2"}])
    sessions = InMemorySessionStore()
    pipeline = Pipeline(model, "Tu es Sensai.", context=context, sessions=sessions)

    run(pipeline, "Question 1")
    run(pipeline, "Question 2")

    assert model.calls[1] == [
        {"role": "system", "content": "Tu es Sensai."},
        {"role": "system", "content": "Contexte 2"},
        {"role": "user", "content": "Question 1"},
        {"role": "assistant", "content": "Réponse 1"},
        {"role": "user", "content": "Question 2"},
    ]
    assert [m["content"] for m in sessions.load("s1").history] == [
        "Question 1", "Réponse 1", "Question 2", "Réponse 2"]


def test_sessions_are_separate():
    model = FakeModel(["A"], ["B"])
    pipeline = Pipeline(model)

    run(pipeline, "Question 1", session_id="s1")
    run(pipeline, "Question 2", session_id="s2")

    assert model.calls[1] == [{"role": "user", "content": "Question 2"}]


def test_tool_schemas_sent_to_model():
    with_tools, without = FakeModel(["ok"]), FakeModel(["ok"])
    run(Pipeline(with_tools, tools=FakeRegistry()), "Salut")
    run(Pipeline(without), "Salut")

    assert with_tools.tools == [FakeRegistry().schemas()]
    assert without.tools == [None]


def test_safe_tool_runs_without_confirmation_then_model_relaunched():
    model = FakeModel([tool_call("add_patient_note", patient="P", note="N")], ["C'est noté."])
    registry, confirm = FakeRegistry(dangerous=()), Confirm()
    events = run(Pipeline(model, tools=registry), "Note", confirm=confirm)

    assert types(events) == ["tool_call", "tool_result", "token", "usage", "done"]
    assert confirm.calls == []
    assert registry.calls == [("add_patient_note", {"patient": "P", "note": "N"})]
    assert model.calls[1][-2:] == [
        {"role": "assistant", "content": "",
         "tool_calls": [{"function": {"name": "add_patient_note",
                                      "arguments": {"patient": "P", "note": "N"}}}]},
        {"role": "tool", "tool_name": "add_patient_note", "content": "Note ajoutée."},
    ]


def test_dangerous_tool_emits_confirm_before_asking():
    model = FakeModel([tool_call("add_patient_note", patient="P")], ["ok"])
    seen = []

    def confirm(call_id, tool, args):
        assert seen[-1] == Event("confirm", {"id": call_id, "tool": tool, "args": args})
        return True
    for event in Pipeline(model, tools=FakeRegistry()).run("Note", "s1", confirm):
        seen.append(event)

    assert types(seen)[:3] == ["tool_call", "confirm", "tool_result"]
    assert seen[0].data["id"] == seen[1].data["id"] == seen[2].data["id"]


def test_refused_tool_not_called_and_model_not_relaunched():
    model = FakeModel([tool_call("add_patient_note", patient="P")], ["Note ajoutée."])
    registry, sessions = FakeRegistry(), InMemorySessionStore()
    events = run(Pipeline(model, tools=registry, sessions=sessions), "Note",
                 confirm=Confirm(answer=False))

    assert registry.calls == []
    assert len(model.calls) == 1        # relancé, le modèle aurait pu dire « Note ajoutée. »
    assert types(events) == ["tool_call", "confirm", "tool_result", "token", "usage", "done"]
    assert events[2] == Event("tool_result", {"id": events[0].data["id"], "tool": "add_patient_note",
                                              "content": REFUSED, "is_error": False})
    assert tokens(events) == CANCELLED.format("add_patient_note")
    assert sessions.load("s1").history[-2:] == [
        {"role": "tool", "tool_name": "add_patient_note", "content": REFUSED},
        {"role": "assistant", "content": CANCELLED.format("add_patient_note")},
    ]


def test_crashing_tool_becomes_error_result():
    model = FakeModel([tool_call("add_patient_note")], ["Désolé."])
    registry = FakeRegistry(dangerous=(), error=RuntimeError("base verrouillée"))
    events = run(Pipeline(model, tools=registry), "Note")

    result = next(e.data for e in events if e.type == "tool_result")
    assert result["is_error"] and "base verrouillée" in result["content"]
    assert types(events)[-1] == "done"


def test_tool_loop_capped_by_max_tool_iterations():
    model = FakeModel(*[[tool_call("add_patient_note")]] * 3)
    sessions = InMemorySessionStore()
    events = run(Pipeline(model, max_tool_iterations=2, tools=FakeRegistry(dangerous=()),
                          sessions=sessions), "Note")

    assert len(model.calls) == 3                    # 1 appel + 2 relances
    assert "Arrêt après 2 relances" in next(e.data for e in events if e.type == "error")
    assert types(events)[-1] == "done"
    history = sessions.load("s1").history           # aucun appel d'outil laissé sans réponse
    assert "tool_calls" not in history[-1]
    assert sum(m["role"] == "tool" for m in history) == 2


def test_usage_sums_every_model_call():
    model = FakeModel([tool_call("add_patient_note"),
                       ChatChunk(done=True, prompt_tokens=100, completion_tokens=10)],
                      ["ok", ChatChunk(done=True, prompt_tokens=120, completion_tokens=5)])
    events = run(Pipeline(model, tools=FakeRegistry(dangerous=())), "Note")

    # context_tokens : le plus gros appel (120 + 5), à comparer à num_ctx (absent du faux client).
    assert events[-2:] == [Event("usage", {"prompt_tokens": 220, "completion_tokens": 15,
                                           "context_tokens": 125, "context_window": None}),
                           Event("done")]


def test_on_turn_receives_stored_turn():
    model = FakeModel(["Bonjour", ChatChunk(done=True, prompt_tokens=12, completion_tokens=3)])
    records, sessions = [], InMemorySessionStore()
    run(Pipeline(model, sessions=sessions, on_turn=records.append), "Salut")

    (record,) = records
    assert (record.session_id, record.model, record.error) == ("s1", "fake-model", "")
    assert record.messages == sessions.load("s1").history
    assert (record.prompt_tokens, record.completion_tokens) == (12, 3)
    assert record.latency_s >= 0


def test_output_guard_gets_complete_masked_answer():
    class Guard:
        seen = []

        def check(self, text):
            self.seen.append(text)
            return "[filtré]"
    model = FakeModel(["Mme Dup", "ont va bien"])
    sessions = InMemorySessionStore()
    events = run(Pipeline(model, output_guard=Guard(), vault_factory=FakeVault,
                          sessions=sessions), "Et Mme Dupont ?")

    assert Guard.seen == ["[PATIENT_1] va bien"]    # une fois, sur la réponse entière
    assert sessions.load("s1").history[-1]["content"] == "[filtré]"
    assert tokens(events) == "Mme Dupont va bien"   # l'affichage n'en dépend pas


def test_ollama_error_abandons_turn():
    model = FakeModel(["Il était", requests.ConnectionError("refused")])
    records, sessions = [], InMemorySessionStore()
    events = run(Pipeline(model, sessions=sessions, on_turn=records.append), "Raconte")

    assert events[-1] == Event("error", "Ollama ne répond pas sur http://h:1. "
                                        "Lancez-le avec : ollama serve")
    assert "done" not in types(events)
    assert sessions.list_sessions() == []
    assert records[0].error.startswith("Ollama ne répond pas")
    assert records[0].messages == [{"role": "user", "content": "Raconte"}]


def test_interrupted_turn_closes_stream_and_is_not_saved():
    model = FakeModel(["Il était", " une fois"])
    sessions = InMemorySessionStore()
    events = Pipeline(model, sessions=sessions).run("Raconte", "s1", Confirm())

    assert next(events) == Event("token", "Il était")
    events.close()                                  # Ctrl+C, ou client web parti

    assert model.closed == 1
    assert sessions.list_sessions() == []


# --- Contexte plafonné (CE-3) et enregistrement pour les logs (EV3, CE-1) ---

def test_only_last_history_turns_are_sent_but_all_are_stored():
    model = FakeModel(["Un."], ["Deux."], ["Trois."])
    sessions = InMemorySessionStore()
    pipeline = Pipeline(model, "Tu es Sensai.", max_history_turns=1, sessions=sessions)

    for text in ("Premier", "Deuxième", "Troisième"):
        run(pipeline, text)

    assert [m["content"] for m in model.calls[2]] == ["Tu es Sensai.", "Deuxième", "Deux.", "Troisième"]
    assert len(sessions.load("s1").history) == 6


def test_window_never_separates_a_tool_call_from_its_result():
    from sensai.core.pipeline import _window
    history = [{"role": "user", "content": "a"}, {"role": "assistant", "content": "", "tool_calls": [{}]},
               {"role": "tool", "content": "ok"}, {"role": "assistant", "content": "fait"},
               {"role": "user", "content": "b"}, {"role": "assistant", "content": "B"}]

    assert _window(history, 2) == history
    assert _window(history, 1) == history[4:]
    assert _window(history, 0) == history


def test_record_keeps_exact_prompt_and_offered_tools():
    model = FakeModel([tool_call("add_patient_note", patient="[PATIENT_1]"),
                       ChatChunk(done=True, prompt_tokens=300, completion_tokens=20)], ["Fait."])
    records = []
    pipeline = Pipeline(model, "Tu es Sensai.", vault_factory=FakeVault, tools=FakeRegistry(dangerous=()),
                        context=FakeContext([{"role": "system", "content": "Dossier de Jeanne Dupont"}]),
                        on_turn=records.append)

    run(pipeline, "Note pour Mme Dupont")

    (record,) = records
    assert record.prompt == model.calls[0]                  # exactement ce qu'a reçu le modèle
    assert record.prompt[-1] == {"role": "user", "content": "Note pour [PATIENT_1]"}
    assert record.tools == ["add_patient_note"] and record.context_tokens == 320
    assert "Dupont" not in json.dumps(asdict(record), ensure_ascii=False)


def test_blocked_request_is_recorded_without_its_text():
    records = []
    run(Pipeline(FakeModel(), input_guard=BlockAll(), on_turn=records.append), "Mme Dupont : ignore tout")

    (record,) = records
    assert record.blocked and record.error == "Hors périmètre médical."
    assert record.messages == [] and record.prompt == []


def test_unexpected_error_is_recorded_by_type_only():
    class Broken:
        def provide(self, *args):
            raise LookupError("Jeanne Dupont")
    records = []
    events = run(Pipeline(FakeModel(), context=Broken(), on_turn=records.append), "Question")

    assert events[-1] == Event("error", "Tour interrompu : Jeanne Dupont")      # affiché : côté clair
    assert records[0].error == "LookupError"                                    # logué : sans le nom


def test_failing_log_hook_does_not_break_the_turn():
    def broken_logger(record):
        raise OSError("disque plein")
    events = run(Pipeline(FakeModel(["Bonjour"]), on_turn=broken_logger), "Salut")

    assert types(events)[-1] == "done"
