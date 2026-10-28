"""Assemblage des outils locaux ou MCP ; fermeture des ressources à la sortie."""
from contextlib import contextmanager
import sys

from sensai.tools.basic_tools import register_basic_tools
from sensai.tools.patient_tools import DANGEROUS_TOOLS, register_patient_tools
from sensai.tools.registry import AsyncRunner, ToolRegistry


@contextmanager
def medical_tools(patients, use_mcp: bool = False, servers=()):
    """`servers` : serveurs MCP tiers ([[mcp.servers]]), démarrés seulement avec --mcp."""
    if not use_mcp:
        registry = ToolRegistry()
        register_basic_tools(registry)
        register_patient_tools(registry, patients)
        yield registry
        return

    try:
        from sensai.tools.mcp_client import MCPClient, register_mcp_tools
    except ImportError as error:
        raise RuntimeError("MCP absent : installez requirements.txt dans votre environnement Python.") from error
    runner = AsyncRunner()
    registry = ToolRegistry(runner)
    register_basic_tools(registry)
    client = MCPClient(name="medical", args=["-m", "sensai.tools.mcp_server",
                       "--db", str(patients.path.resolve())])
    clients = [client]
    try:
        async def connect():
            await client.connect()
            await register_mcp_tools(client, registry, dangerous=DANGEROUS_TOOLS)
        runner.run(connect(), timeout=15)
        for server in servers:
            third_party = _connect_third_party(server, runner, registry, MCPClient, register_mcp_tools)
            if third_party:
                clients.append(third_party)
        yield registry
    finally:
        for opened in clients:
            try:
                runner.run(opened.close(), timeout=10)
            except Exception as error:
                print(f"Fermeture MCP ({opened.name}) : {error}", file=sys.stderr)
        runner.close()


def _connect_third_party(server, runner, registry, client_class, register):
    """Un serveur tiers indisponible est signalé puis ignoré : la consultation continue sans lui."""
    client = client_class(name=server.name, args=list(server.args), command=server.command or None)

    async def connect():
        await client.connect()
        try:
            return await register(client, registry, prefix=server.prefix, dangerous=set(server.dangerous),
                                  only=set(server.tools) or None)
        except BaseException:
            await client.close()
            raise
    try:
        names = runner.run(connect(), timeout=15)
    except Exception as error:
        print(f"Serveur MCP « {server.name} » ignoré : {error}", file=sys.stderr)
        return None
    for name in names:
        registry.keywords[name] = server.keywords
    print(f"Serveur MCP « {server.name} » : {', '.join(names) or 'aucun outil retenu'}", file=sys.stderr)
    return client
