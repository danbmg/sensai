"""Évite la recherche documentaire pour les lectures explicites du dossier seul."""
import re
import unicodedata


LOOKUP_WORDS = frozenset("quel quelle quels quelles sont est les le la l de du des d au aux un une "
                        "liste montre affiche rappelle consulte lis resume donne moi nous vous mes ses "
                        "allergie allergies traitement traitements antecedent antecedents note notes dossier "
                        "enregistre enregistree enregistres enregistrees consigne consignee consignes consignees "
                        "renseigne renseignee renseignes renseignees dans pour sur patient patiente patients "
                        "ce cette son sa mon ma mme monsieur madame m cite citer source sources "
                        "local locale locaux locales sqlite merci".split())


def is_record_lookup(query: str) -> bool:
    """En cas d'ambiguïté, conserver le RAG plutôt que perdre un document utile."""
    query = re.sub(r"\[[A-Z]+_\d+\]", "patient", query)
    text = unicodedata.normalize("NFKD", query).encode("ascii", "ignore").decode().casefold()
    # Un médicament, une demande d'explication ou un terme inconnu conserve
    # la recherche. Cette liste volontairement étroite privilégie les faux négatifs.
    if not set(re.findall(r"[a-z]+", text)).issubset(LOOKUP_WORDS):
        return False
    if text.count("?") > 1 or ";" in text:
        return False
    lookup = re.match(r"\s*(?:quels?|quelles?|liste|montre|affiche|rappelle|consulte|lis|resume|donne)\b", text)
    field = re.search(r"\b(?:allergies?|traitements?|antecedents?|notes?|dossier)\b", text)
    stored = re.search(r"\b(?:enregistr\w*|consign\w*|renseign\w*|dossier)\b", text)
    return bool(lookup and field and stored)
