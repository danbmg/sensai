
"""Output Guardrail de SENSAI.

Masque certaines données personnelles résiduelles dans les réponses
du modèle avant leur enregistrement dans l'historique.

Ce module complète le PIIVault, mais ne le remplace pas.
"""

import re


class SensaiOutputGuard:
    """Filtre les données sensibles détectables dans une réponse."""

    EMAIL_PATTERN = re.compile(
        r"(?<![\w.+-])"
        r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
        r"(?![\w.-])"
    )

    PHONE_PATTERN = re.compile(
        r"(?<!\d)"
        r"(?:\+33[\s.-]?[1-9]|0[1-9])"
        r"(?:[\s.-]?\d{2}){4}"
        r"(?!\d)"
    )

    NIR_PATTERN = re.compile(
        r"(?<!\d)"
        r"[12][\s]?\d{2}[\s]?(?:0[1-9]|1[0-2]|20|[3-9]\d)"
        r"[\s]?\d{2}[\s]?\d{3}[\s]?\d{3}[\s]?\d{2}"
        r"(?!\d)"
    )

    IBAN_PATTERN = re.compile(
        r"(?<![A-Za-z0-9])"
        r"FR\d{2}(?:[\s]?[A-Za-z0-9]{4}){5}"
        r"[\s]?[A-Za-z0-9]{3}"
        r"(?![A-Za-z0-9])",
        re.IGNORECASE,
    )

    def check(self, text: str) -> str:
        """Renvoie une version filtrée du texte."""

        if not isinstance(text, str):
            raise TypeError("La réponse doit être une chaîne de caractères.")

        if not text:
            return text

        result = self.EMAIL_PATTERN.sub("[EMAIL_MASQUE]", text)
        result = self.PHONE_PATTERN.sub("[TELEPHONE_MASQUE]", result)
        result = self.NIR_PATTERN.sub("[NIR_MASQUE]", result)
        result = self.IBAN_PATTERN.sub("[IBAN_MASQUE]", result)

        return result
