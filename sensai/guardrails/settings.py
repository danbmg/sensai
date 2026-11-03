"""Configuration des garde-fous ([guardrails] de config.toml) : les règles se règlent sans toucher au code.

La pseudonymisation (PIIVault) n'en fait pas partie : elle reste toujours active, car c'est
la frontière entre le cabinet et le modèle.
"""
import re
from dataclasses import dataclass
from pathlib import Path

from sensai.core.config import DEFAULT_PATH, ConfigError, tomllib

INPUT_FAMILIES = ("injection", "secrets")          # règles d'entrée fournies par SensaiInputGuard
OUTPUT_TYPES = ("EMAIL", "TEL", "NIR", "IBAN")      # données masquées par SensaiOutputGuard


@dataclass(frozen=True)
class GuardRule:
    pattern: str        # expression régulière, casse ignorée
    reason: str         # motif affiché au médecin quand la requête est refusée


@dataclass(frozen=True)
class GuardrailSettings:
    enabled: bool = True                # false : ni filtre d'entrée ni masquage de sortie
    max_input_length: int = 20_000
    input_rules: tuple[str, ...] = INPUT_FAMILIES
    custom_rules: tuple[GuardRule, ...] = ()
    output_types: tuple[str, ...] = OUTPUT_TYPES


def load_guardrail_settings(path: str | Path | None = None) -> GuardrailSettings:
    """Lève ConfigError si la table est invalide ; sans table [guardrails], les règles par défaut."""
    try:
        with Path(path or DEFAULT_PATH).open("rb") as file:
            section = tomllib.load(file).get("guardrails", {})
        if not isinstance(section, dict) or set(section) - GuardrailSettings.__dataclass_fields__.keys():
            raise ValueError("table [guardrails] invalide ou option inconnue")
        if not isinstance(section.get("enabled", True), bool):
            raise ValueError("enabled doit être un booléen")
        length = section.get("max_input_length", GuardrailSettings.max_input_length)
        if not isinstance(length, int) or isinstance(length, bool) or length < 1:
            raise ValueError("max_input_length doit être un entier positif")
        families = _names(section.get("input_rules", INPUT_FAMILIES), (*INPUT_FAMILIES, "medical_scope"), "input_rules")
        types = _names(section.get("output_types", OUTPUT_TYPES), OUTPUT_TYPES, "output_types")
        rules = section.get("custom_rules", [])
        if not isinstance(rules, list):
            raise ValueError("custom_rules doit être une liste de [[guardrails.custom_rules]]")
        custom = tuple(_rule(rule) for rule in rules)
        return GuardrailSettings(section.get("enabled", True), length, families, custom, types)
    except (OSError, ValueError, TypeError, tomllib.TOMLDecodeError) as error:
        raise ConfigError(f"Configuration des garde-fous : {error}") from error


def _names(value, allowed: tuple[str, ...], field: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or not all(isinstance(name, str) for name in value):
        raise ValueError(f"{field} doit être une liste de noms")
    unknown = set(value) - set(allowed)
    if unknown:
        raise ValueError(f"{field} : {', '.join(sorted(unknown))} inconnu (possibles : {', '.join(allowed)})")
    return tuple(value)


def _rule(rule) -> GuardRule:
    if not isinstance(rule, dict) or set(rule) != {"pattern", "reason"}:
        raise ValueError("chaque règle personnalisée a exactement pattern et reason")
    if not all(isinstance(rule[key], str) and rule[key].strip() for key in rule):
        raise ValueError("pattern et reason doivent être des textes non vides")
    try:
        re.compile(rule["pattern"])
    except re.error as error:
        raise ValueError(f"motif invalide {rule['pattern']!r} : {error}") from error
    return GuardRule(rule["pattern"], rule["reason"])
