"""Configuration des logs ([logging] de config.toml), indépendante du modèle de conversation."""
from dataclasses import dataclass
from pathlib import Path

from sensai.core.config import DEFAULT_PATH, ConfigError, tomllib


@dataclass(frozen=True)
class LogSettings:
    enabled: bool = False           # activé dans config.toml : sans [logging], rien n'est écrit
    directory: str = "logs"         # relatif au dossier de lancement, comme .sensai/


def load_log_settings(path: str | Path | None = None) -> LogSettings:
    try:
        with Path(path or DEFAULT_PATH).open("rb") as file:
            section = tomllib.load(file).get("logging", {})
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ConfigError(f"Configuration des logs : {error}") from error
    if not isinstance(section, dict) or set(section) - LogSettings.__dataclass_fields__.keys():
        raise ConfigError("Configuration des logs : table [logging] invalide ou option inconnue")
    settings = LogSettings(**section)
    if not isinstance(settings.enabled, bool):
        raise ConfigError("Configuration des logs : enabled doit être un booléen")
    if not isinstance(settings.directory, str) or not settings.directory.strip():
        raise ConfigError("Configuration des logs : directory doit être un chemin non vide")
    return settings
