"""Contexte patient local conforme à ContextProvider ; aucun RAG simulé."""
from sensai.core.interfaces import Message
from sensai.memory.patients import PatientStore


class PatientContext:
    def __init__(self, patients: PatientStore):
        self.patients = patients
        self.patient_id: str | None = None

    def select(self, reference: str) -> dict:
        patient = self.patients.resolve_patient(reference)
        self.patient_id = patient["patient_id"]
        return patient

    def provide(self, query: str, masked_query: str, session_id: str) -> list[Message]:
        if self.patient_id is None:
            return []
        patient = self.patients.get_patient(self.patient_id)
        lines = ["[Source : dossier patient local SQLite]", f"Patient : {patient['name']}"]
        if patient["birth_date"]:
            lines.append(f"Date de naissance : {patient['birth_date']}")
        for field, label in (("allergies", "Allergies"), ("treatments", "Traitements"),
                             ("medical_history", "Antécédents"), ("notes", "Notes")):
            lines.append(f"{label} : " + (" ; ".join(patient[field]) or "Aucun élément enregistré"))
        lines.append("Réponds uniquement sur ce patient. Une liste vide n'atteste pas l'absence "
                     "médicale d'une allergie. Aucune notice documentaire n'est encore fournie. "
                     "Pour ajouter une note, utilise add_patient_note avec le nom du patient "
                     "et une note textuelle. L'outil demandera la confirmation du médecin.")
        return [{"role": "system", "content": "\n".join(lines)}]
