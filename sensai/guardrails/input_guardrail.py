"""Input Guardrail de SENSAI.

Filtre les requêtes utilisateur avant leur transmission au modèle.
Respecte le contrat InputGuard défini dans core/interfaces.py.
"""

import re

from sensai.core.interfaces import GuardResult
from sensai.guardrails.settings import INPUT_FAMILIES, GuardRule
from sensai.guardrails.medical_scope import REASON, is_medical


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

    REASONS = {
        "injection": "Requête refusée : tentative de contournement des instructions.",
        "secrets": "Requête refusée : demande d'extraction de données sensibles.",
    }

    def __init__(self, families: tuple[str, ...] = INPUT_FAMILIES,
                 custom_rules: tuple[GuardRule, ...] = (), max_input_length: int = MAX_INPUT_LENGTH):
        """Familles de règles intégrées retenues, puis règles propres au cabinet ([guardrails])."""
        patterns = {"injection": self.INJECTION_PATTERNS, "secrets": self.SENSITIVE_EXTRACTION_PATTERNS}
        self.medical_scope = "medical_scope" in families
        self.max_input_length = max_input_length
        self.rules = [(pattern, self.REASONS[family]) for family in families if family in patterns for pattern in patterns[family]]
        self.rules += [(re.compile(rule.pattern, re.IGNORECASE | re.DOTALL), rule.reason)
                       for rule in custom_rules]

    @classmethod
    def from_settings(cls, settings) -> "SensaiInputGuard":
        return cls(settings.input_rules, settings.custom_rules, settings.max_input_length)

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

        if len(text) > self.max_input_length:
            return GuardResult(
                blocked=True,
                reason="La requête dépasse la taille maximale autorisée.",
            )

        for pattern, reason in self.rules:
            if pattern.search(text):
                return GuardResult(blocked=True, reason=reason)

        if self.medical_scope and not is_medical(text):
            return GuardResult(blocked=True, reason=REASON)

        return GuardResult(blocked=False)