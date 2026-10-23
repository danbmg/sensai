"""Configuration du RAG, indépendante du modèle de conversation."""
from dataclasses import dataclass
import math
from pathlib import Path

from sensai.core.config import DEFAULT_PATH, ConfigError, tomllib


@dataclass(frozen=True)
class RAGSettings:
    enabled: bool = True
    search_mode: str = "auto"
    index_path: str = ""
    model: str = "nomic-embed-text"
    chunk_size: int = 900
    overlap: int = 120
    top_k: int = 3
    candidates: int = 20
    min_similarity: float = 0.7
    min_relevance: float = 0.5
    rerank: bool = True
    max_context_chars: int = 2600
    timeout: float = 180
    batch_size: int = 4


def load_settings(path: str | Path | None = None) -> RAGSettings:
    try:
        with Path(path or DEFAULT_PATH).open("rb") as file:
            section = tomllib.load(file).get("rag", {})
        if not isinstance(section, dict) or set(section) - RAGSettings.__dataclass_fields__.keys():
            raise ValueError("Table [rag] invalide ou option inconnue")
        settings = RAGSettings(**section)
        if not isinstance(settings.search_mode, str) or settings.search_mode not in {"auto", "always"}:
            raise ValueError("search_mode doit être auto ou always")
        for field in ("enabled", "rerank"):
            if not isinstance(getattr(settings, field), bool):
                raise ValueError(f"{field} doit être un booléen")
        if not isinstance(settings.index_path, str):
            raise ValueError("index_path doit être du texte")
        for field in ("model",):
            if not isinstance(getattr(settings, field), str) or not getattr(settings, field).strip():
                raise ValueError(f"{field} doit être un texte non vide")
        for field in ("chunk_size", "overlap", "top_k", "candidates", "max_context_chars", "batch_size"):
            value = getattr(settings, field)
            if not isinstance(value, int) or isinstance(value, bool) or value < (0 if field == "overlap" else 1):
                raise ValueError(f"{field} doit être un entier valide")
        if settings.chunk_size < 100 or settings.overlap >= settings.chunk_size or settings.candidates < settings.top_k or settings.max_context_chars < 400:
            raise ValueError("Taille, chevauchement, nombre de candidats ou budget invalides")
        for field, lower, upper in (("min_similarity", -1, 1), ("min_relevance", 0, 1), ("timeout", 0, float("inf"))):
            value = getattr(settings, field)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not lower <= value <= upper:
                raise ValueError(f"{field} doit être un nombre fini dans l'intervalle autorisé")
        if settings.timeout == 0:
            raise ValueError("timeout doit être positif")
        return settings
    except (OSError, ValueError, TypeError) as error:
        raise ConfigError(f"Configuration RAG : {error}") from error


def resolve_index_path(settings: RAGSettings, memory_db: str | Path) -> Path:
    return Path(settings.index_path) if settings.index_path else Path(memory_db).parent / "rag.sqlite3"
