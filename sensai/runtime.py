"""Assemblage des outils locaux ou MCP ; fermeture des ressources à la sortie."""
from contextlib import contextmanager
import sys

from sensai.tools.basic_tools import register_basic_tools
from sensai.tools.patient_tools import register_patient_tools
from sensai.tools.registry import AsyncRunner, ToolRegistry


@contextmanager
def medical_tools(patients, use_mcp: bool = False):
    if not use_mcp:
        registry = ToolRegistry()
        register_basic_tools(registry)
        register_patient_tools(registry, patients)
        yield registry
        return

    try:
        from sensai.mcp_client.client import MCPClient, register_mcp_tools
    except ImportError as error:
        raise RuntimeError("MCP absent : installez requirements.txt dans votre environnement Python.") from error
    runner = AsyncRunner()
    registry = ToolRegistry(runner)
    register_basic_tools(registry)
    client = MCPClient(name="medical", args=["-m", "sensai.mcp_server.medical",
                       "--db", str(patients.path.resolve())])
    try:
        async def connect():
            await client.connect()
            await register_mcp_tools(client, registry, dangerous={"add_patient_note"})
        runner.run(connect(), timeout=15)
        yield registry
    finally:
        try:
            runner.run(client.close(), timeout=10)
        except Exception as error:
            print(f"Fermeture MCP : {error}", file=sys.stderr)
        runner.close()
