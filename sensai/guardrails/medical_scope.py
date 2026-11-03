"""Périmètre lexical conservateur : une demande ambiguë doit être reformulée."""
import re
import unicodedata

MEDICAL = re.compile(
    r"\b(?:medic\w*|patient\w*|dossier\w*|consult\w*|sante|symptom\w*|"
    r"douleur\w*|fievre|touss\w*|toux|fatigue|nause\w*|vomiss\w*|diarrhe\w*|"
    r"allerg\w*|traitement\w*|antecedent\w*|ordonnance\w*|prescri\w*|"
    r"vaccin\w*|infection\w*|diabet\w*|tension|cardia\w*|respira\w*|"
    r"amoxicilline|penicilline|paracetamol|ibuprofene|metformine|amlodipine|"
    r"imc|poids|taille|notice\w*|ansm|has|soins?|diagnostic\w*|"
    r"infirmier\w*|pharmac\w*|get_patient)\b")
OFF_TOPIC = re.compile(
    r"\b(?:meteo|football|politique|election\w*|bitcoin|cryptomonnaie\w*|"
    r"bourse|recette\w*|cuisine|film\w*|jeux?|programm\w*|python|javascript|"
    r"voyage\w*|poeme\w*|blague\w*|roman\w*|capitale\w*)\b")
REASON = ("Hors périmètre : je traite uniquement les demandes médicales et les dossiers patients. "
          "Précisez le contexte médical de votre question.")


def is_medical(text: str) -> bool:
    normalized = ''.join(c for c in unicodedata.normalize('NFD', text.casefold())
                         if unicodedata.category(c) != 'Mn')
    # Un mot médical ajouté à une demande hors sujet ne suffit pas à l'autoriser.
    return bool(MEDICAL.search(normalized)) and not OFF_TOPIC.search(normalized)
