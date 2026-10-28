"""Serveurs MCP tiers ([[mcp.servers]] de config.toml), lancés avec --mcp à côté du serveur médical.

Un serveur tiers tourne dans son propre processus, avec son propre environnement Python ou
Node : il n'a pas besoin de partager les dépendances de Sensai.
"""
from dataclasses import dataclass
from pathlib import Path

from sensai.core.config import DEFAULT_PATH, ConfigError, tomllib


@dataclass(frozen=True)
class MCPServer:
    name: str
    args: tuple[str, ...]
    command: str = ""                   # vide : l'interpréteur Python de Sensai
    tools: tuple[str, ...] = ()         # outils retenus (vide : tous ceux du serveur)
    dangerous: tuple[str, ...] = ()     # outils soumis à la validation du médecin (A3)
    keywords: tuple[str, ...] = ()      # mots qui proposent ces outils quand un dossier est ouvert

    @property
    def prefix(self) -> str:
        """Préfixe des noms d'outils : « time_get_current_time » ne heurte pas « get_current_time »."""
        return f"{self.name}_"


def load_mcp_servers(path: str | Path | None = None) -> tuple[MCPServer, ...]:
    """Lève ConfigError si un serveur est mal décrit ; sans table [mcp], aucun serveur tiers."""
    try:
        with Path(path or DEFAULT_PATH).open("rb") as file:
            section = tomllib.load(file).get("mcp", {})
        if not isinstance(section, dict) or set(section) - {"servers"}:
            raise ValueError("table [mcp] invalide ou option inconnue")
        servers = section.get("servers", [])
        if not isinstance(servers, list):
            raise ValueError("servers doit être une liste de [[mcp.servers]]")
        parsed = tuple(_server(server) for server in servers)
        names = [server.name for server in parsed]
        if len(set(names)) != len(names) or "medical" in names:
            raise ValueError("chaque serveur a un nom unique, différent de « medical »")
        return parsed
    except (OSError, ValueError, TypeError, tomllib.TOMLDecodeError) as error:
        raise ConfigError(f"Configuration MCP : {error}") from error


def _server(server) -> MCPServer:
    if not isinstance(server, dict) or set(server) - MCPServer.__dataclass_fields__.keys():
        raise ValueError("serveur invalide ou option inconnue")
    name = server.get("name")
    if not isinstance(name, str) or not name.isidentifier():
        raise ValueError("name doit être un identifiant (lettres, chiffres, _)")
    if not isinstance(server.get("command", ""), str):
        raise ValueError(f"{name} : command doit être du texte")
    lists = {}
    for field in ("args", "tools", "dangerous", "keywords"):
        value = server.get(field, [])
        if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
            raise ValueError(f"{name} : {field} doit être une liste de textes")
        lists[field] = tuple(value)
    if not lists["args"] and not server.get("command"):
        raise ValueError(f"{name} : command ou args est obligatoire")
    return MCPServer(name, lists["args"], server.get("command", ""), lists["tools"],
                     lists["dangerous"], tuple(word.casefold() for word in lists["keywords"]))
