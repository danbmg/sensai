"""Une consultation = une session : son patient, son profil, ses filtres et ses sources.

C'est le contexte de Timothée (PatientContext) plus les actions qu'on fait dessus.
La CLI et le web n'appellent que ces méthodes : ils ne font qu'afficher.
"""
from __future__ import annotations

import threading
import uuid
from dataclasses import asdict
from datetime import datetime
from typing import TYPE_CHECKING, Iterator

from sensai.app.tool_routing import requested_tools
from sensai.core.interfaces import ConfirmFn, Event, Message, ToolResult
from sensai.memory.context import PatientContext
from sensai.rag.retrieval import Hit, format_context, source_records
from sensai.rag.store import Filters

if TYPE_CHECKING:
    from sensai.app.runtime import Runtime


class Consultation:
    def __init__(self, runtime: Runtime, session_id: str, context: PatientContext):
        self.runtime = runtime
        self.session_id = session_id
        self.context = context
        self.busy = threading.Lock()    # un seul tour à la fois par session (web : 2 onglets)

    @classmethod
    def new(cls, runtime: Runtime, session_id: str, *, profile: str = "default",
            patient: str | None = None, filters: Filters | None = None) -> Consultation:
        context = runtime.make_context(profile)
        if patient:
            context.select(patient)
        if filters:
            context.filters = filters
        return cls(runtime, session_id, context)

    @classmethod
    def restore(cls, runtime: Runtime, session_id: str, saved: dict) -> Consultation:
        """Recrée la consultation sauvegardée ; tout est validé avant d'être appliqué."""
        context = runtime.make_context(saved.get("profile_id") or "default")
        patient_id = saved.get("patient_id")
        if patient_id:
            runtime.stores.patients.get_patient(patient_id)
        filters = saved.get("filters", {})
        filters = Filters(**{**filters, "tags": tuple(filters.get("tags", ()))})
        filters.validate()
        context.patient_id, context.filters = patient_id, filters
        context.last_hits = [Hit(**record) for record in saved.get("sources", [])]
        return cls(runtime, session_id, context)

    # --- État ---

    @property
    def patient_id(self) -> str | None:
        return self.context.patient_id

    @property
    def profile_id(self) -> str:
        return self.context.profile.profile_id if self.context.profile else "default"

    def save(self) -> None:
        """Métadonnées de la session (patient, profil, filtres, sources), à côté de son historique."""
        self.runtime.stores.sessions.save_context(self.session_id, {
            "patient_id": self.patient_id,
            "profile_id": self.profile_id,
            "filters": asdict(self.context.filters),
            "sources": [asdict(hit) for hit in self.context.last_hits],
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        })

    def describe(self) -> dict:
        """Résumé affichable (EN CLAIR : nom du patient compris)."""
        patient = self.patient_record() if self.patient_id else None
        return {
            "session_id": self.session_id,
            "patient": {key: patient[key] for key in ("patient_id", "name")} if patient else None,
            "profile": asdict(self.context.profile) if self.context.profile else None,
            "filters": asdict(self.context.filters),
            "messages": len(self.runtime.stores.sessions.load(self.session_id).history),
        }

    def patient_record(self) -> dict:
        if self.patient_id is None:
            raise ValueError("Sélectionnez un patient avec /patient.")
        return self.runtime.stores.patients.get_patient(self.patient_id)

    def history(self, revealed: bool = False) -> list[Message]:
        """Historique stocké (pseudonymisé) ; `revealed` le ré-identifie pour l'afficher au médecin."""
        state = self.runtime.stores.sessions.load(self.session_id)
        if not revealed:
            return state.history
        vault = self.runtime.vault(state.pii_map)
        messages = []
        for message in state.history:
            shown = {**message, "content": vault.reveal(message.get("content", ""))}
            if "tool_calls" in message:
                shown["tool_calls"] = [{**call, "function": {
                    **call.get("function", {}),
                    "arguments": vault.reveal_args(call.get("function", {}).get("arguments", {}))}}
                    for call in message["tool_calls"]]
            messages.append(shown)
        return messages

    def sources(self) -> list[dict]:
        return source_records(self.context.last_hits)

    def last_prompt(self) -> dict | None:
        """Le dernier prompt exactement envoyé au modèle (pseudonymisé), pendant cette exécution."""
        record = self.runtime.last_records.get(self.session_id)
        if record is None:
            return None
        return {"model": record.model, "tools": record.tools, "messages": record.prompt,
                "prompt_tokens": record.prompt_tokens, "completion_tokens": record.completion_tokens,
                "context_tokens": record.context_tokens,
                "context_window": self.runtime.pipeline.client_options().get("num_ctx")}

    def is_refused(self, text: str) -> bool:
        """La demande serait-elle bloquée par l'InputGuard ? (la CLI n'annonce alors pas de génération)"""
        return self.runtime.pipeline.input_guard.check(text).blocked

    # --- Actions ---

    def set_filters(self, filters: Filters) -> None:
        filters.validate()
        self.context.filters, self.context.last_hits = filters, []
        self.save()

    def search(self, query: str) -> str:
        """Recherche documentaire seule, sans génération (la requête part masquée aux embeddings)."""
        if self.context.retriever is None:
            raise ValueError("Aucun index documentaire chargé. Utilisez python -m sensai.rag index.")
        state = self.runtime.stores.sessions.load(self.session_id)
        masked = self.runtime.vault(state.pii_map).mask(query)
        hits = self.context.retriever.search(masked, self.context.filters)
        text, self.context.last_hits = format_context(hits, self.context.max_context_chars)
        self.save()
        return text

    def add_note(self, note: str, confirm: ConfirmFn) -> ToolResult | None:
        """Note demandée par le médecin lui-même : même outil et même confirmation que le modèle."""
        args = {"patient": self.patient_record()["patient_id"], "note": note}
        if not confirm(uuid.uuid4().hex, "add_patient_note", args):
            return None
        return self.runtime.tools.call("add_patient_note", args)

    def ask(self, text: str, confirm: ConfirmFn) -> Iterator[Event]:
        """Un tour du pipeline, puis les sources retenues ; un tour raté garde les sources d'avant."""
        previous = self.context.last_hits
        keywords = getattr(self.runtime.tools, "keywords", {})     # outils des serveurs MCP tiers
        tool_names = requested_tools(text, keywords) if self.patient_id else None
        completed = False
        events = self.runtime.pipeline.run(text, self.session_id, confirm, tool_names=tool_names)
        try:
            for event in events:
                if event.type == "done":
                    completed = True
                    self.save()
                    if self.context.last_hits:
                        yield Event("sources", self.sources())
                    if self.context.rag_error:
                        yield Event("error", f"RAG : {self.context.rag_error}")
                yield event
            if not completed and self.context.rag_error:
                yield Event("error", f"RAG : {self.context.rag_error}")
        finally:
            events.close()      # interruption : le pipeline ferme le flux, Ollama arrête de générer
            if not completed:
                self.context.last_hits = previous
