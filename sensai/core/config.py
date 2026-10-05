"""Chargement de config.toml, surchargé par les arguments de la CLI."""
import sys
from dataclasses import dataclass
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from sensai.core.ollama_client import DEFAULT_HOST

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "config.toml"


class ConfigError(Exception):
    """config.toml absent, illisible ou incomplet."""


@dataclass
class Config:
    model: str                      # seul endroit où le nom du modèle est défini
    host: str = DEFAULT_HOST
    temperature: float = 0.2
    system_prompt: str = ""
    max_tool_iterations: int = 5


def load_config(path: str | Path | None = None, model: str | None = None) -> Config:
    """Lit `path` (défaut : config.toml du projet) ; `model` surcharge [model] name."""
    path = Path(path) if path else DEFAULT_PATH
    try:
        with path.open("rb") as f:
            data = tomllib.load(f)
    except FileNotFoundError:
        raise ConfigError(f"fichier introuvable : {path}") from None
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{path} : {e}") from None

    model_section = data.get("model", {})
    assistant_section = data.get("assistant", {})
    name = model or model_section.get("name")
    if not name:
        raise ConfigError(f"{path} : [model] name manquant")
    return Config(
        model=name,
        host=model_section.get("host", Config.host),
        temperature=model_section.get("temperature", Config.temperature),
        system_prompt=assistant_section.get("system_prompt", Config.system_prompt).strip(),
        max_tool_iterations=assistant_section.get("max_tool_iterations",
                                                  Config.max_tool_iterations),
    )
