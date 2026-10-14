"""Outils médicaux utilisant le CRUD de Timothée."""
from sensai.memory.patients import PatientStore


def register_patient_tools(registry, patients: PatientStore) -> None:
    registry.register(
        name="get_patient", description="Consulte le dossier local du patient identifié.",
        parameters={"type": "object", "properties": {
            "patient": {"type": "string", "description": "Nom complet ou identifiant du patient"}},
            "required": ["patient"], "additionalProperties": False},
        function=lambda patient: patients.resolve_patient(patient),
    )

    def add_note(patient: str, note: str) -> dict:
        if not isinstance(note, str) or note.strip().startswith(("{", "[")):
            raise ValueError("La note doit être du texte, pas un schéma JSON.")
        return patients.add_patient_note(patient, note)

    registry.register(
        name="add_patient_note", description="Ajoute une note textuelle au dossier après confirmation du médecin.",
        parameters={"type": "object", "properties": {
            "patient": {"type": "string", "description": "Nom complet ou identifiant du patient"},
            "note": {"type": "string", "description": "Texte de la note à ajouter"}},
            "required": ["patient", "note"], "additionalProperties": False},
        function=add_note, dangerous=True,
    )
