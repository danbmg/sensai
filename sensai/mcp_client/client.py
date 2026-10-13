
"""Client MCP générique utilisant le transport stdio."""

import asyncio
import sys
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class MCPClientError(Exception):
    """Erreur de communication avec un serveur MCP."""


class MCPClient:
    def __init__(
        self,
        workspace: str = ".",
        command: str | None = None,
        args: list[str] | None = None,
        name: str = "developer",
    ):
        self.workspace = workspace
        self.name = name
        self.command = command or sys.executable
        self.args = args if args is not None else [
            "-m",
            "sensai.mcp_server.server",
            "--workspace",
            workspace,
        ]

        self._session: ClientSession | None = None
        self._session_task: asyncio.Task | None = None
        self._ready: asyncio.Event | None = None
        self._stop: asyncio.Event | None = None
        self._startup_error: BaseException | None = None

    async def _run_session(self) -> None:
        """Maintient les contextes MCP dans une même tâche."""
        try:
            params = StdioServerParameters(
                command=self.command,
                args=self.args,
            )

            async with stdio_client(params) as (
                read_stream,
                write_stream,
            ):
                async with ClientSession(
                    read_stream,
                    write_stream,
                ) as session:
                    await session.initialize()

                    self._session = session
                    self._ready.set()

                    await self._stop.wait()

        except BaseException as error:
            self._startup_error = error
            self._ready.set()
            raise

        finally:
            self._session = None

    async def connect(self) -> None:
        """Démarre la connexion MCP."""
        if self._session_task is not None:
            if self._session is not None:
                return
            raise MCPClientError(
                "Une connexion MCP est déjà en cours."
            )

        self._ready = asyncio.Event()
        self._stop = asyncio.Event()
        self._startup_error = None

        self._session_task = asyncio.create_task(
            self._run_session()
        )

        await self._ready.wait()

        if self._startup_error is not None:
            try:
                await self._session_task
            except BaseException:
                pass

            self._session_task = None

            raise MCPClientError(
                f"Connexion impossible à '{self.name}': "
                f"{self._startup_error}"
            ) from self._startup_error

    async def list_tools(self) -> list[dict[str, Any]]:
        """Récupère les outils du serveur MCP."""
        if self._session is None:
            raise MCPClientError("Serveur MCP non connecté.")

        try:
            response = await self._session.list_tools()
        except Exception as error:
            raise MCPClientError(
                f"Impossible de récupérer les outils : {error}"
            ) from error

        return [
            {
                "name": tool.name,
                "description": tool.description or "",
                "parameters": getattr(tool, "inputSchema", None)
                or {"type": "object", "properties": {}},
            }
            for tool in response.tools
        ]

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> Any:
        """Exécute un outil sur le serveur MCP."""
        if self._session is None:
            raise MCPClientError("Serveur MCP non connecté.")

        try:
            result = await self._session.call_tool(
                name, arguments
            )
        except Exception as error:
            raise MCPClientError(
                f"Erreur MCP pour '{name}': {error}"
            ) from error

        if getattr(result, "isError", False):
            messages = [
                item.text
                for item in result.content
                if getattr(item, "text", None)
            ]
            raise MCPClientError(
                "\n".join(messages) or "Erreur MCP inconnue."
            )

        structured = getattr(
            result, "structuredContent", None
        )
        if structured is not None:
            return structured

        messages = [
            item.text
            for item in result.content
            if getattr(item, "text", None) is not None
        ]

        return "\n".join(messages) if messages else None

    async def close(self) -> None:
        """Ferme la session MCP proprement."""
        task = self._session_task

        if task is None:
            return

        self._stop.set()

        try:
            await task
        finally:
            self._session_task = None
            self._session = None
            self._ready = None
            self._stop = None
            self._startup_error = None


async def register_mcp_tools(
    client: MCPClient,
    registry,
    prefix: str = "",
    dangerous: bool = True,
) -> None:
    """Enregistre les outils MCP dans le ToolRegistry."""
    tools = await client.list_tools()

    for tool in tools:
        original_name = tool["name"]
        registered_name = f"{prefix}{original_name}"

        async def execute_mcp_tool(
            _tool_name=original_name,
            **arguments,
        ):
            return await client.call_tool(
                _tool_name, arguments
            )

        registry.register(
            name=registered_name,
            description=tool["description"],
            parameters=tool["parameters"],
            function=execute_mcp_tool,
            source=f"mcp:{client.name}",
            dangerous=dangerous,
        )
