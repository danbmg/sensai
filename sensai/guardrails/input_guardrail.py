"""Input Guardrail de SENSAI.

Filtre les requêtes utilisateur avant leur transmission au modèle.
Respecte le contrat InputGuard défini dans core/interfaces.py.
"""

import re

from sensai.core.interfaces import GuardResult


class SensaiInputGuard:
    """Vérifie les requêtes utilisateur avant traitement."""

    MAX_INPUT_LENGTH = 20_000

    INJECTION_PATTERNS = (
        re.compile(
            r"\bignore[rz]?\s+(?:toutes?\s+)?"
            r"(?:les\s+)?(?:instructions|consignes|règles)"
            r"(?:\s+précédentes)?\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(?:désactive|desactive|contourne|bypasse)\s+"
            r"(?:les?\s+)?(?:guardrails?|protections?|filtres?|sécurité|securite)\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(?:reveal|ignore)\s+"
            r"(?:all\s+)?(?:previous\s+)?"
            r"(?:instructions|system\s+prompt)\b",
            re.IGNORECASE,
        ),
    )

    SENSITIVE_EXTRACTION_PATTERNS = (
        re.compile(
            r"\b(?:affiche|révèle|revele|exporte|extrais|liste)\b"
            r".{0,100}\b(?:tous\s+les\s+)?"
            r"(?:mots\s+de\s+passe|passwords?|clés?\s+api|api\s+keys?)\b",
            re.IGNORECASE | re.DOTALL,
        ),
    )

    def check(self, text: str) -> GuardResult:
        """Renvoie blocked=True si la requête doit être refusée."""

        if not isinstance(text, str):
            return GuardResult(
                blocked=True,
                reason="La requête doit être du texte.",
            )

        if not text.strip():
            return GuardResult(
                blocked=True,
                reason="La requête ne peut pas être vide.",
            )

        if len(text) > self.MAX_INPUT_LENGTH:
            return GuardResult(
                blocked=True,
                reason="La requête dépasse la taille maximale autorisée.",
            )

        for pattern in self.INJECTION_PATTERNS:
            if pattern.search(text):
                return GuardResult(
                    blocked=True,
                    reason="Requête refusée : tentative de contournement des instructions.",
                )

        for pattern in self.SENSITIVE_EXTRACTION_PATTERNS:
            if pattern.search(text):
                return GuardResult(
                    blocked=True,
                    reason="Requête refusée : demande d'extraction de données sensibles.",
                )

        return GuardResult(blocked=False)