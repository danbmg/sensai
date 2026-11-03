"""Outils médicaux utilisant le CRUD de Timothée : l'agent lit, cherche et met à jour les dossiers."""
from sensai.memory.patients import PatientStore

# Listes du dossier que l'agent peut compléter ou corriger (les notes ont leur propre outil).
RECORD_FIELDS = ("allergies", "treatments", "medical_history")
# Toute écriture dans un dossier passe par la validation du médecin (A3).
DANGEROUS_TOOLS = frozenset({"add_patient_note", "add_patient_entry", "remove_patient_entry"})

PATIENT_ARG = {"type": "string", "description": "Nom complet ou identifiant du patient"}
FIELD_ARG = {"type": "string", "enum": list(RECORD_FIELDS),
             "description": "allergies, treatments (traitements) ou medical_history (antécédents)"}


def _text(value: str, label: str) -> str:
    if not isinstance(value, str) or value.strip().startswith(("{", "[")):
        raise ValueError(f"{label} doit être du texte, pas un schéma JSON.")
    return value


def register_patient_tools(registry, patients: PatientStore) -> None:
    registry.register(
        name="get_patient", description="Consulte le dossier local du patient identifié.",
        parameters={"type": "object", "properties": {"patient": PATIENT_ARG},
                    "required": ["patient"], "additionalProperties": False},
        function=lambda patient: patients.resolve_patient(patient),
    )

    registry.register(
        name="find_patients",
        description="Cherche les patients dont le nom contient le texte donné (nom et identifiant).",
        parameters={"type": "object", "properties": {
            "query": {"type": "string", "description": "Partie du nom du patient"}},
            "required": ["query"], "additionalProperties": False},
        function=lambda query: {"patients": [{"patient_id": p["patient_id"], "name": p["name"]}
                                             for p in patients.find_patients(query)]},
    )

    registry.register(
        name="add_patient_note", description="Ajoute une note textuelle au dossier après confirmation du médecin.",
        parameters={"type": "object", "properties": {
            "patient": PATIENT_ARG,
            "note": {"type": "string", "description": "Texte de la note à ajouter"}},
            "required": ["patient", "note"], "additionalProperties": False},
        function=lambda patient, note: patients.add_patient_note(patient, _text(note, "La note")),
        dangerous=True,
    )

    registry.register(
        name="add_patient_entry",
        description="Ajoute une allergie, un traitement ou un antécédent au dossier, après confirmation du médecin.",
        parameters={"type": "object", "properties": {
            "patient": PATIENT_ARG, "field": FIELD_ARG,
            "value": {"type": "string", "description": "Élément à ajouter, ex. « Latex »"}},
            "required": ["patient", "field", "value"], "additionalProperties": False},
        function=lambda patient, field, value: patients.add_entry(patient, field, _text(value, "L'élément")),
        dangerous=True,
    )

    registry.register(
        name="remove_patient_entry",
        description="Retire une allergie, un traitement ou un antécédent du dossier, après confirmation du médecin.",
        parameters={"type": "object", "properties": {
            "patient": PATIENT_ARG, "field": FIELD_ARG,
            "value": {"type": "string", "description": "Élément à retirer, tel qu'écrit dans le dossier"}},
            "required": ["patient", "field", "value"], "additionalProperties": False},
        function=lambda patient, field, value: patients.remove_entry(patient, field, _text(value, "L'élément")),
        dangerous=True,
    )
