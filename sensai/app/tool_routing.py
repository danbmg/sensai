"""Choix des outils proposés au modèle pour un tour, par mots-clés.

Un petit modèle local (3B) appelle volontiers un outil sans raison, et chaque schéma
allonge le prompt. Quand un dossier est déjà dans le contexte, on ne propose donc que
les outils que la demande rend plausibles. La liste est volontairement étroite : une
formulation non reconnue n'offre aucun outil d'écriture, jamais l'inverse.
"""
import re

# Verbe d'action à l'impératif ou à l'infinitif : « Quelles allergies sont enregistrées ? »
# (participe) ne doit pas proposer d'écriture.
_ADD = re.compile(r"\b(?:ajout\w*|rajout\w*|enregistre[rz]?|consigne[rz]?|note[rz]? que|"
                  r"mets? à jour|mettre à jour)\b")
_REMOVE = re.compile(r"\b(?:retir\w*|supprim\w*|enl[eè]v\w*|efface[rz]?|n'est plus|ne prend plus)\b")
_NOTE = re.compile(r"\bnotes?\b")
_FIELD = re.compile(r"\b(?:allergi\w*|traitements?|m[ée]dicaments?|ant[ée]c[ée]dents?)\b")
_FIND = re.compile(r"\b(?:cherche\w*|recherche\w*|trouve\w*)\b.*\bpatient")


def requested_tools(text: str, keywords: dict[str, tuple[str, ...]] | None = None) -> set[str]:
    """Noms des outils plausibles pour cette demande (ensemble vide : aucun outil).

    `keywords` : outils des serveurs MCP tiers -> mots qui les proposent ([[mcp.servers]]).
    """
    query = text.casefold()
    names = {name for name, words in (keywords or {}).items() if any(word in query for word in words)}
    # Un patient entier, contrairement à une note ou une liste de son dossier.
    if re.search(r"\b(?:ajout\w*|cr[ée]e[rz]?|créer|enregistre[rz]?)\s+(?:(?:un|une|le|la|nouveau|nouvelle)\s+)*(?:patient|patiente)\b", query):
        names.add("create_patient")
    if re.search(r"\b(?:supprim\w*|retir\w*|efface[rz]?|enl[eè]v\w*)\s+(?:(?:le|la|un|une|ce|cette|patient|patiente|dossier|de|du)\s+)*(?:patient|patiente|dossier)\b", query):
        names.update({"delete_patient", "find_patients", "get_patient"})
    if _NOTE.search(query) and _ADD.search(query):
        names.add("add_patient_note")
    elif _FIELD.search(query):
        if _REMOVE.search(query):
            names.add("remove_patient_entry")
        elif _ADD.search(query):
            names.add("add_patient_entry")
    if _FIND.search(query):
        names.add("find_patients")
    if "get_patient" in query:
        names.add("get_patient")
    if "calcul" in query or re.search(r"\d\s*[+*/-]\s*\d", query):
        names.add("calculator")
    if "heure" in query or "date actuelle" in query or "aujourd'hui" in query:
        names.add("get_current_time")
    return names
