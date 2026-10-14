"""Orchestration guards -> contexte -> modèle -> outils, émet des Event (étape 5).

Le pipeline est la SEULE frontière PII : il pseudonymise tout ce qui part vers le modèle,
l'historique et les logs, et ré-identifie ce qui revient vers le médecin (voir interfaces.py).

Brancher un vrai module (les autres gardent leur version neutre de defaults.py) :

    pipeline = Pipeline(client, cfg.system_prompt, cfg.max_tool_iterations,
                        context=MonContextProvider(), sessions=MonSessionStore())
    for event in pipeline.run("Mme Dupont peut-elle prendre de l'amoxicilline ?", "s1", confirm):
        ...

Event émis (data EN CLAIR) :
    token        str : fragment de réponse à afficher
    tool_call    {"id", "tool", "args"}
    confirm      {"id", "tool", "args"} : outil dangereux, juste avant l'appel à confirm()
    tool_result  {"id", "tool", "content", "is_error"}
    usage        {"prompt_tokens", "completion_tokens"} : cumul du tour
    error        str : message à afficher. Sans « done » derrière, le tour est abandonné.
    done         None : le tour est enregistré dans la session
"""
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Generator, Iterator

from sensai.core.defaults import (EmptyContext, EmptyRegistry, InMemorySessionStore, NullGuard,
                                  NullOutputGuard, NullVault)
from sensai.core.interfaces import (PSEUDONYM_TYPES, ConfirmFn, ContextProvider, Event, InputGuard,
                                    Message, OutputGuard, PIIVault, SessionStore, ToolRegistry,
                                    ToolResult, VaultFactory)
from sensai.core.ollama_client import OLLAMA_ERRORS, OllamaClient, describe_error

MAX_PSEUDONYM_LEN = 24          # au-delà, un « [ » sans « ] » n'est pas un pseudonyme
REFUSED = "Action refusée par le médecin"


@dataclass
class TurnRecord:               # passé au hook on_turn (logs EV3) : PSEUDONYMISÉ uniquement
    session_id: str
    model: str
    messages: list[Message]     # le tour tel qu'enregistré : user, assistant, tool
    latency_s: float
    prompt_tokens: int
    completion_tokens: int
    error: str = ""             # tour abandonné sur une erreur d'Ollama


class Pipeline:
    def __init__(self, client: OllamaClient, system_prompt: str = "",
                 max_tool_iterations: int = 5, *,
                 input_guard: InputGuard | None = None,
                 output_guard: OutputGuard | None = None,
                 vault_factory: VaultFactory | None = None,
                 context: ContextProvider | None = None,
                 sessions: SessionStore | None = None,
                 tools: ToolRegistry | None = None,
                 on_turn: Callable[[TurnRecord], None] | None = None):
        self.client = client
        self.system = [{"role": "system", "content": system_prompt}] if system_prompt else []
        self.max_tool_iterations = max_tool_iterations
        self.input_guard = input_guard or NullGuard()
        self.output_guard = output_guard or NullOutputGuard()
        self.vault_factory = vault_factory or NullVault
        self.context = context or EmptyContext()
        self.sessions = sessions or InMemorySessionStore()
        self.tools = tools or EmptyRegistry()
        self.on_turn = on_turn

    def run(self, user_text: str, session_id: str, confirm: ConfirmFn, *,
            tool_names: set[str] | None = None) -> Iterator[Event]:
        """Un tour complet. `user_text` arrive en clair ; les Event repartent en clair."""
        try:
            yield from self._run(user_text, session_id, confirm, tool_names)
        except Exception as error:
            # Une erreur de stockage/contexte/outil mal formé ne ferme pas la CLI.
            yield Event("error", f"Tour interrompu : {error}")

    def _run(self, user_text: str, session_id: str, confirm: ConfirmFn,
             tool_names: set[str] | None) -> Iterator[Event]:
        start = time.perf_counter()
        guard = self.input_guard.check(user_text)
        if guard.blocked:
            yield Event("error", guard.reason)
            return

        state = self.sessions.load(session_id)
        vault = self.vault_factory(state.pii_map)
        masked = vault.mask(user_text)
        context = [{**m, "content": vault.mask(m["content"])}
                   for m in self.context.provide(user_text, masked, session_id)]
        turn: list[Message] = [{"role": "user", "content": masked}]  # pseudonymisé
        usage = {"prompt_tokens": 0, "completion_tokens": 0}

        try:
            for iteration in range(self.max_tool_iterations + 1):
                reply = yield from self._ask(self.system + context + state.history + turn,
                                             vault, usage, tool_names)
                turn.append(reply)
                if "tool_calls" not in reply:
                    break
                if iteration == self.max_tool_iterations:
                    # Plus de relance possible : on n'enregistre pas d'appel resté sans réponse.
                    del reply["tool_calls"]
                    yield Event("error", f"Arrêt après {self.max_tool_iterations} relances "
                                         "du modèle pour des appels d'outils.")
                    break
                for call in reply["tool_calls"]:
                    turn.append((yield from self._run_tool(call, vault, confirm, tool_names)))
        except OLLAMA_ERRORS as e:
            message = describe_error(e, self.client)
            self._record(session_id, turn[:1], start, usage, message)
            yield Event("error", message)
            return

        state.history += turn
        state.pii_map = vault.export()
        self.sessions.save(session_id, state)
        self._record(session_id, turn, start, usage)
        yield Event("usage", dict(usage))
        yield Event("done")

    def _ask(self, messages: list[Message], vault: PIIVault,
             usage: dict[str, int], tool_names: set[str] | None = None) -> Generator[Event, None, Message]:
        """Un appel au modèle : émet les fragments en clair, renvoie la réponse pseudonymisée."""
        display = _DisplayBuffer(vault.reveal)
        content, tool_calls = "", []
        schemas = self.tools.schemas()
        if tool_names is not None:
            schemas = [schema for schema in schemas if schema["function"]["name"] in tool_names]
        stream = self.client.chat_stream(messages, schemas or None)
        try:
            for chunk in stream:
                if text := display.feed(chunk.content):
                    yield Event("token", text)
                content += chunk.content
                tool_calls += chunk.tool_calls
                usage["prompt_tokens"] += chunk.prompt_tokens
                usage["completion_tokens"] += chunk.completion_tokens
        finally:
            stream.close()      # interruption (Ctrl+C, client web parti) : Ollama arrête de générer
        if text := display.flush():
            yield Event("token", text)

        # Sur la réponse COMPLÈTE : un nom coupé entre deux fragments (« Dup » + « ont ») est rattrapé.
        reply = {"role": "assistant", "content": self.output_guard.check(vault.mask(content))}
        if tool_calls:
            reply["tool_calls"] = _map_strings(tool_calls, vault.mask)
        return reply

    def _run_tool(self, call: dict, vault: PIIVault,
                  confirm: ConfirmFn, tool_names: set[str] | None = None) -> Generator[Event, None, Message]:
        """Exécute un appel d'outil en clair ; renvoie le message « tool » pseudonymisé."""
        function = call.get("function", {}) if isinstance(call, dict) else {}
        name = function.get("name", "") if isinstance(function, dict) else ""
        raw_args = function.get("arguments", {}) if isinstance(function, dict) else {}
        if not isinstance(name, str) or not name or not isinstance(raw_args, dict):
            yield Event("error", "Appel d'outil invalide reçu du modèle ; aucune action exécutée.")
            return {"role": "tool", "tool_name": str(name), "content": "Arguments d'outil invalides."}
        if tool_names is not None and name not in tool_names:
            yield Event("error", f"Outil non autorisé pour ce tour : {name}")
            return {"role": "tool", "tool_name": name, "content": "Outil non autorisé pour ce tour."}
        args = vault.reveal_args(raw_args)
        call_id = uuid.uuid4().hex
        yield Event("tool_call", {"id": call_id, "tool": name, "args": args})

        approved = True
        if self.tools.is_dangerous(name):
            yield Event("confirm", {"id": call_id, "tool": name, "args": args})
            approved = confirm(call_id, name, args)
        result = self._call(name, args) if approved else ToolResult(REFUSED)

        yield Event("tool_result", {"id": call_id, "tool": name,
                                    "content": result.content, "is_error": result.is_error})
        return {"role": "tool", "tool_name": name, "content": vault.mask(result.content)}

    def _call(self, name: str, args: dict) -> ToolResult:
        try:
            return self.tools.call(name, args)
        except Exception as e:  # un outil qui plante ne doit pas faire tomber le tour
            return ToolResult(f"Erreur de l'outil {name} : {e}", is_error=True)

    def _record(self, session_id: str, messages: list[Message], start: float,
                usage: dict[str, int], error: str = "") -> None:
        if self.on_turn:
            self.on_turn(TurnRecord(session_id, self.client.model, messages,
                                    time.perf_counter() - start, usage["prompt_tokens"],
                                    usage["completion_tokens"], error))


class _DisplayBuffer:
    """Côté affichage : retient un pseudonyme coupé entre deux fragments avant vault.reveal.

    « [PATI » + « ENT_1] » ne doit pas s'afficher tel quel. Un « [ » qui ne peut pas devenir
    un pseudonyme (« [1] », « [Notice ») est relâché aussitôt : il ne bloque pas le flux.
    """

    def __init__(self, reveal: Callable[[str], str]):
        self.reveal = reveal
        self.pending = ""

    def feed(self, text: str) -> str:
        self.pending += text
        start = self.pending.rfind("[")
        if start != -1 and _may_become_pseudonym(self.pending[start:]):
            ready, self.pending = self.pending[:start], self.pending[start:]
        else:
            ready, self.pending = self.pending, ""
        return self.reveal(ready)

    def flush(self) -> str:
        ready, self.pending = self.pending, ""
        return self.reveal(ready)


def _may_become_pseudonym(text: str) -> bool:
    """`text` commence par « [ » : est-ce le début d'un [TYPE_N] encore incomplet ?"""
    if "]" in text or len(text) > MAX_PSEUDONYM_LEN:
        return False
    body = text[1:]
    return any(f"{t}_".startswith(body)                                # « [PAT », « [PATIENT_ »
               or (body.startswith(f"{t}_") and body[len(t) + 1:].isdigit())  # « [PATIENT_1 »
               for t in (*PSEUDONYM_TYPES, "TELEPHONE"))


def _map_strings(value: Any, fn: Callable[[str], str]) -> Any:
    """Applique `fn` à chaque chaîne d'une structure JSON (arguments d'outils)."""
    if isinstance(value, str):
        return fn(value)
    if isinstance(value, dict):
        return {k: _map_strings(v, fn) for k, v in value.items()}
    if isinstance(value, list):
        return [_map_strings(v, fn) for v in value]
    return value
