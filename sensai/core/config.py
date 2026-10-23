"""Chargement de config.toml, surchargé par les arguments de la CLI."""
import sys
import math
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
    max_history_turns: int = 0      # tours d'historique envoyés au modèle (0 = tous)
    num_ctx: int = 2048
    num_predict: int = 128
    num_thread: int = 2
    num_batch: int = 64
    timeout: float = 180


def load_config(path: str | Path | None = None, model: str | None = None) -> Config:
    """Lit `path` (défaut : config.toml du projet) ; `model` surcharge [model] name."""
    path = Path(path) if path else DEFAULT_PATH
    try:
        with path.open("rb") as f:
            data = tomllib.load(f)
    except FileNotFoundError:
        raise ConfigError(f"fichier introuvable : {path}") from None
    except OSError as e:
        raise ConfigError(f"fichier illisible : {path} ({e})") from None
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{path} : {e}") from None

    model_section = data.get("model", {})
    assistant_section = data.get("assistant", {})
    if not isinstance(model_section, dict) or not isinstance(assistant_section, dict):
        raise ConfigError("model et assistant doivent être des tables TOML")
    name = model or model_section.get("name")
    if not name:
        raise ConfigError(f"{path} : [model] name manquant")
    prompt = assistant_section.get("system_prompt", Config.system_prompt)
    if not isinstance(prompt, str):
        raise ConfigError("system_prompt doit être du texte")
    cfg = Config(
        model=name,
        host=model_section.get("host", Config.host),
        temperature=model_section.get("temperature", Config.temperature),
        system_prompt=prompt.strip(),
        max_tool_iterations=assistant_section.get("max_tool_iterations",
                                                  Config.max_tool_iterations),
        max_history_turns=assistant_section.get("max_history_turns", Config.max_history_turns),
        num_ctx=model_section.get("num_ctx", Config.num_ctx),
        num_predict=model_section.get("num_predict", Config.num_predict),
        num_thread=model_section.get("num_thread", Config.num_thread),
        num_batch=model_section.get("num_batch", Config.num_batch),
        timeout=model_section.get("timeout", Config.timeout),
    )
    validate_config(cfg)
    return cfg


def validate_config(cfg: Config) -> None:
    """Vérifie chaque réglage ; sert aussi aux changements faits depuis le web (PUT /api/config)."""
    if not isinstance(cfg.model, str) or not cfg.model.strip():
        raise ConfigError("name doit être un texte non vide")
    if not isinstance(cfg.host, str) or not cfg.host.startswith(("http://", "https://")):
        raise ConfigError("host doit être une URL HTTP ou HTTPS")
    if not isinstance(cfg.temperature, (int, float)) or isinstance(cfg.temperature, bool) or not math.isfinite(cfg.temperature) or cfg.temperature < 0:
        raise ConfigError("temperature doit être un nombre positif ou nul")
    for field in ("num_ctx", "num_predict", "num_thread", "num_batch"):
        value = getattr(cfg, field)
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise ConfigError(f"{field} doit être un entier positif")
    for field in ("max_tool_iterations", "max_history_turns"):
        value = getattr(cfg, field)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ConfigError(f"{field} doit être un entier positif ou nul")
    if not isinstance(cfg.timeout, (int, float)) or isinstance(cfg.timeout, bool) or not math.isfinite(cfg.timeout) or cfg.timeout <= 0:
        raise ConfigError("timeout doit être un nombre positif")
