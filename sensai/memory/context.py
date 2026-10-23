"""ContextProvider : profil médecin, dossier local et extraits publics sourcés."""
import copy
import sqlite3

from sensai.core.interfaces import Message
from sensai.memory.patients import PatientStore
from sensai.memory.profiles import DoctorProfile
from sensai.rag.embeddings import EmbeddingError
from sensai.rag.retrieval import format_context
from sensai.rag.routing import is_record_lookup
from sensai.rag.store import Filters, IndexError


class PatientContext:
    def __init__(self, patients: PatientStore, *, profile: DoctorProfile | None = None,
                 retriever=None, max_context_chars=2600, profiles=None, search_mode="auto"):
        if search_mode not in {"auto", "always"}:
            raise ValueError("Mode de recherche attendu : auto ou always.")
        self.patients = patients
        self.patient_id: str | None = None
        # Snapshot : une modification en base s'applique à la prochaine sélection/initialisation.
        self.profile = copy.deepcopy(profile)
        self.profiles = profiles
        self.retriever = retriever
        self.search_mode = search_mode
        self.max_context_chars = max_context_chars
        self.filters = Filters()
        self.last_hits = []
        self.rag_error = ""

    def select(self, reference: str) -> dict:
        patient = self.patients.resolve_patient(reference)
        self.patient_id = patient["patient_id"]
        return patient

    def provide(self, query: str, masked_query: str, session_id: str) -> list[Message]:
        messages = []
        self.last_hits, self.rag_error = [], ""
        if self.profile and (self.profile.specialty or self.profile.preferences or self.profile.instructions):
            profile = self.profile
            text = (f"Profil médecin : {profile.profile_id}\nSpécialité : {profile.specialty or 'non renseignée'}\n"
                    + "Préférences : " + "; ".join(profile.preferences)
                    + f"\nInstructions personnalisées : {profile.instructions}")
            messages.append({"role": "system", "content": text})
        if self.patient_id is not None:
            messages.append(self._patient_message())
        record_only = self.patient_id is not None and self.search_mode == "auto" and is_record_lookup(masked_query)
        if self.retriever is not None and not record_only:
            try:
                # La requête en clair et le dossier ne sont JAMAIS envoyés aux embeddings.
                hits = self.retriever.search(masked_query, self.filters)
                text, self.last_hits = format_context(hits, self.max_context_chars)
            except (EmbeddingError, IndexError, sqlite3.Error) as error:
                self.rag_error = str(error)
                text = "Recherche documentaire indisponible. N'invente aucune source documentaire."
            messages.append({"role": "system", "content": text})
        return messages

    def _patient_message(self) -> Message:
        patient = self.patients.get_patient(self.patient_id)
        lines = ["[Source : dossier patient local SQLite]", f"Patient : {patient['name']}"]
        if patient["birth_date"]:
            lines.append(f"Date de naissance : {patient['birth_date']}")
        for field, label in (("allergies", "Allergies"), ("treatments", "Traitements"),
                             ("medical_history", "Antécédents"), ("notes", "Notes")):
            lines.append(f"{label} : " + (" ; ".join(patient[field]) or "Aucun élément enregistré"))
        lines.append("Réponds uniquement sur ce patient. Une liste vide n'atteste pas l'absence "
                     "médicale d'une allergie. Les documents publics éventuels sont fournis séparément. "
                     "Pour ajouter une note, utilise add_patient_note avec le nom du patient "
                     "et une note textuelle. L'outil demandera la confirmation du médecin.")
        return {"role": "system", "content": "\n".join(lines)}
