"""Serveur MCP stdio de test, étranger à Sensai : il joue un serveur tiers comme mcp-server-time.

Il ne partage aucun code avec sensai.tools ; seul le protocole MCP les relie.
"""
from mcp.server.mcpserver import MCPServer

server = MCPServer("fake-time", log_level="WARNING")


@server.tool()
def get_current_time(timezone: str) -> dict:
    """Heure courante dans un fuseau IANA."""
    return {"timezone": timezone, "datetime": "2026-10-28T14:00:00+01:00"}


@server.tool()
def convert_time(source_timezone: str, time: str, target_timezone: str) -> dict:
    """Convertit une heure d'un fuseau à l'autre."""
    return {"source": f"{time} {source_timezone}", "target": f"{time} {target_timezone}"}


@server.tool()
def set_clock(datetime: str) -> str:
    """Outil qui modifie quelque chose : doit être écarté ou validé par le médecin."""
    return f"horloge réglée sur {datetime}"


if __name__ == "__main__":
    server.run()
