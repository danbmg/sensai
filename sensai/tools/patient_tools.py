"""Outils médicaux utilisant le CRUD de Timothée : l'agent lit, cherche et met à jour les dossiers."""
from datetime import date

from sensai.memory.patients import PatientStore

# Listes du dossier que l'agent peut compléter ou corriger (les notes ont leur propre outil).
RECORD_FIELDS = ("allergies", "treatments", "medical_history")
# Toute écriture dans un dossier passe par la validation du médecin (A3).
DANGEROUS_TOOLS = frozenset({"add_patient_note", "add_patient_entry", "remove_patient_entry",
                              "create_patient", "delete_patient"})

PATIENT_ARG = {"type": "string", "description": "Nom complet ou identifiant du patient"}
FIELD_ARG = {"type": "string", "enum": list(RECORD_FIELDS),
             "description": "allergies, treatments (traitements) ou medical_history (antécédents)"}


def _text(value: str, label: str) -> str:
    if not isinstance(value, str) or value.strip().startswith(("{", "[")):
        raise ValueError(f"{label} doit être du texte, pas un schéma JSON.")
    return value


def register_patient_tools(registry, patients: PatientStore) -> None:
    def create(name: str, birth_date: str = "") -> dict:
        name = _text(name, "Le nom").strip()
        if not name:
            raise ValueError("Le nom doit être non vide.")
        if not isinstance(birth_date, str):
            raise ValueError("La date de naissance doit être du texte au format AAAA-MM-JJ.")
        if birth_date:
            try:
                parsed = date.fromisoformat(birth_date)
            except ValueError:
                raise ValueError("Date de naissance invalide : format AAAA-MM-JJ attendu.") from None
            if parsed.isoformat() != birth_date:
                raise ValueError("Format AAAA-MM-JJ attendu.")
        # Ne pas multiplier les dossiers si le modèle répète le même appel.
        if any(p["name"].casefold() == name.casefold() and p["birth_date"] == birth_date
               for p in patients.list_patients()):
            raise ValueError("Un patient avec ce nom et cette date existe déjà. Consultez son dossier.")
        return patients.create_patient(name, birth_date)

    def delete(patient_id: str) -> dict:
        # Identifiant obligatoire : aucune suppression par nom, même sans homonyme.
        patient = patients.get_patient(patient_id)
        patients.delete_patient(patient["patient_id"])
        return {"deleted": True, "patient_id": patient["patient_id"], "name": patient["name"]}

    registry.register(
        name="create_patient",
        description="Crée un patient après confirmation du médecin. Nom obligatoire ; date AAAA-MM-JJ facultative. Ne jamais inventer une information manquante.",
        parameters={"type": "object", "properties": {
            "name": {"type": "string", "description": "Nom complet fourni par le médecin"},
            "birth_date": {"type": "string", "description": "AAAA-MM-JJ, ou texte vide si inconnue"}},
            "required": ["name"], "additionalProperties": False},
        function=create, dangerous=True,
    )
    registry.register(
        name="delete_patient",
        description="Supprime définitivement le dossier patient après confirmation du médecin. Utiliser son identifiant exact, obtenu par find_patients ou get_patient ; jamais deviner un identifiant.",
        parameters={"type": "object", "properties": {
            "patient_id": {"type": "string", "description": "Identifiant SQLite exact du patient à supprimer"}},
            "required": ["patient_id"], "additionalProperties": False},
        function=delete, dangerous=True,
    )

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
