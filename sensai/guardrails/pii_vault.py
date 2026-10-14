
"""Coffre de pseudonymisation des données personnelles de SENSAI.

Le coffre est propre à une session. Les correspondances sont exportables
pour permettre la restauration de la session.
"""

import re
from collections import Counter

from sensai.core.interfaces import PSEUDONYM_TYPES


class SensaiPIIVault:
    """Implémentation du contrat PIIVault de core/interfaces.py."""

    PATTERNS = {
        "NIR": re.compile(
            r"(?<!\d)"
            r"[12]\s?\d{2}\s?(?:0[1-9]|1[0-2]|20|[3-9]\d)"
            r"\s?\d{2}\s?\d{3}\s?\d{3}\s?\d{2}"
            r"(?!\d)"
        ),
        "EMAIL": re.compile(
            r"(?<![\w.+-])"
            r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
            r"(?![\w.-])"
        ),
        "TEL": re.compile(
            r"(?<!\d)"
            r"(?:\+33[\s.-]?[1-9]|0[1-9])"
            r"(?:[\s.-]?\d{2}){4}"
            r"(?!\d)"
        ),
        "NAISSANCE": re.compile(
            r"\b(?:né|née)\s+le\s+"
            r"(?P<date>\d{2}/\d{2}/\d{4}|\d{4}-\d{2}-\d{2})\b"
            r"|\bdate\s+de\s+naissance\s*[:=]?\s*"
            r"(?P<date_alt>\d{2}/\d{2}/\d{4}|\d{4}-\d{2}-\d{2})\b",
            re.IGNORECASE,
        ),
        "PATIENT": re.compile(
            r"\b(?:Mme\.?|Madame|Monsieur|M\.)\s+"
            r"[A-ZÀ-ÖØ-Þ][a-zà-öø-ÿ'-]+(?:\s+[A-ZÀ-ÖØ-Þ][a-zà-öø-ÿ'-]+)?"
        ),
        "ADRESSE": re.compile(
            r"\b\d{1,4}\s+(?:rue|avenue|boulevard|chemin|impasse|place)\s+"
            r"[^\n.;]+", re.IGNORECASE,
        ),
    }

    PLACEHOLDER_PATTERN = re.compile(
        r"\[(?:" + "|".join((*PSEUDONYM_TYPES, "TELEPHONE")) + r")_\d+\]"
    )

    def __init__(self, pii_map: dict[str, str] | None = None, *, patients: list[dict] | None = None):
        # Convention : {"[EMAIL_1]": "patient@example.com"}
        self.pii_map = dict(pii_map or {})

        self._reverse_map = {
            original: placeholder
            for placeholder, original in self.pii_map.items()
        }

        self._counters = {}
        self._entities = []
        patients = patients or []
        surnames = Counter(patient["name"].split()[-1].casefold() for patient in patients)
        for patient in patients:
            name = patient["name"]
            if identifier := patient.get("patient_id"):
                self._entities.append((identifier, name, "PATIENT"))
            variants = [name]
            surname = name.split()[-1]
            if surnames[surname.casefold()] == 1:
                variants.append(surname)
            for variant in variants:
                for prefix in ("Mme ", "Mme. ", "Madame ", "Monsieur ", "M. ", ""):
                    self._entities.append((prefix + variant, name, "PATIENT"))
            if date := patient.get("birth_date"):
                self._entities.append((date, date, "NAISSANCE"))
                if re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
                    self._entities.append((f"{date[8:10]}/{date[5:7]}/{date[:4]}", date, "NAISSANCE"))
        # Les valeurs déjà connues restent masquées même sans le préfixe initial.
        for placeholder, original in self.pii_map.items():
            match = re.fullmatch(r"\[([A-Z]+)_\d+\]", placeholder)
            if match:
                self._entities.append((original, original, match[1]))
        self._entities.sort(key=lambda entity: len(entity[0]), reverse=True)

        for placeholder in self.pii_map:
            match = re.fullmatch(
                r"\[([A-Z]+)_(\d+)\]", placeholder
            )
            if match:
                category = match.group(1)
                number = int(match.group(2))
                self._counters[category] = max(
                    self._counters.get(category, 0),
                    number,
                )

    def _register(self, original: str, category: str) -> str:
        """Réutilise un pseudonyme existant ou en crée un nouveau."""

        if original in self._reverse_map:
            return self._reverse_map[original]

        number = self._counters.get(category, 0) + 1
        placeholder = f"[{category}_{number}]"

        while placeholder in self.pii_map:
            number += 1
            placeholder = f"[{category}_{number}]"

        self._counters[category] = number
        self.pii_map[placeholder] = original
        self._reverse_map[original] = placeholder

        return placeholder

    def mask(self, text: str) -> str:
        """Remplace les données détectées par des pseudonymes."""

        if not isinstance(text, str):
            raise TypeError("Le texte doit être une chaîne de caractères.")

        # Normaliser les pseudonymes connus si le modèle omet leurs crochets.
        for placeholder in self.pii_map:
            if self.PLACEHOLDER_PATTERN.fullmatch(placeholder):
                text = re.sub(r"(?<![\w\[])" + re.escape(placeholder[1:-1]) + r"(?![\w\]])",
                              lambda match, value=placeholder: value, text)

        # On protège les pseudonymes déjà présents dans le texte.
        protected = {}

        def protect(match):
            marker = f"\x00SENSAI_{len(protected)}\x00"
            protected[marker] = match.group(0)
            return marker

        result = self.PLACEHOLDER_PATTERN.sub(protect, text)

        for variant, original, category in self._entities:
            result = re.sub(
                r"(?<!\w)" + re.escape(variant) + r"(?!\w)",
                lambda match, value=original, kind=category: self._register(value, kind),
                result, flags=re.IGNORECASE,
            )

        for category, pattern in self.PATTERNS.items():
            if category == "NAISSANCE":
                def replace_birth(match):
                    date = match.group("date") or match.group("date_alt")
                    placeholder = self._register(date, "NAISSANCE")
                    return match.group(0).replace(date, placeholder)

                result = pattern.sub(replace_birth, result)
            else:
                result = pattern.sub(
                    lambda match, kind=category: self._register(
                        match.group(0), kind
                    ),
                    result,
                )

        for marker, placeholder in protected.items():
            result = result.replace(marker, placeholder)

        return result

    def reveal(self, text: str) -> str:
        """Restaure uniquement les pseudonymes connus de ce coffre."""

        if not isinstance(text, str):
            raise TypeError("Le texte doit être une chaîne de caractères.")

        return self.PLACEHOLDER_PATTERN.sub(
            lambda match: self.pii_map.get(
                match.group(0), match.group(0)
            ),
            text,
        )

    def reveal_args(self, args: dict) -> dict:
        """Restaure les pseudonymes dans les arguments d'un outil."""

        def restore(value):
            if isinstance(value, str):
                return self.reveal(value)
            if isinstance(value, dict):
                return {
                    key: restore(item)
                    for key, item in value.items()
                }
            if isinstance(value, list):
                return [restore(item) for item in value]
            return value

        return restore(args)

    def export(self) -> dict[str, str]:
        """Renvoie une copie des correspondances de la session."""

        return dict(self.pii_map)
