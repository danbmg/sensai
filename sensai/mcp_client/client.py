import sys
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class MCPClientError(Exception):
    """Raised when communication with an MCP server fails."""


class MCPClient:
    """
    Generic MCP client using stdio.

    Can connect to:
    - Sensai's custom MCP server
    - Any compatible external MCP stdio server
    """

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

        self.args = (
            args
            if args is not None
            else [
                "-m",
                "mcp_server.server",
                "--workspace",
                workspace,
            ]
        )

        self._stdio_context = None
        self._session_context = None
        self._session: ClientSession | None = None

    async def connect(self) -> None:
        """Start the MCP server and initialize the session."""

        if self._session is not None:
            return

        server_params = StdioServerParameters(
            command=self.command,
            args=self.args,
        )

        try:
            self._stdio_context = stdio_client(server_params)

            read_stream, write_stream = (
                await self._stdio_context.__aenter__()
            )

            self._session_context = ClientSession(
                read_stream,
                write_stream,
            )

            self._session = (
                await self._session_context.__aenter__()
            )

            await self._session.initialize()

        except Exception as error:
            try:
                await self.close()
            except Exception:
                pass

            raise MCPClientError(
                f"Unable to connect to MCP server "
                f"'{self.name}': {error}"
            ) from error

    async def list_tools(self) -> list[dict[str, Any]]:
        """Discover tools exposed by the MCP server."""

        if self._session is None:
            raise MCPClientError(
                f"MCP server '{self.name}' is not connected."
            )

        try:
            response = await self._session.list_tools()

        except Exception as error:
            raise MCPClientError(
                f"Unable to list tools from "
                f"'{self.name}': {error}"
            ) from error

        tools = []

        for tool in response.tools:

            parameters = getattr(
                tool,
                "inputSchema",
                None,
            )

            if not parameters:
                parameters = {
                    "type": "object",
                    "properties": {},
                }

            tools.append(
                {
                    "name": tool.name,
                    "description": tool.description or "",
                    "parameters": parameters,
                }
            )

        return tools

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> Any:
        """Execute a tool on the connected MCP server."""

        if self._session is None:
            raise MCPClientError(
                f"MCP server '{self.name}' is not connected."
            )

        try:
            result = await self._session.call_tool(
                name,
                arguments,
            )

        except Exception as error:
            raise MCPClientError(
                f"MCP tool '{name}' failed: {error}"
            ) from error

        # MCP protocol-level tool error.
        if getattr(result, "isError", False):

            error_messages = []

            for item in result.content:
                value = getattr(item, "text", None)

                if value:
                    error_messages.append(value)

            message = "\n".join(error_messages)

            raise MCPClientError(
                f"MCP tool '{name}' returned an error: "
                f"{message or 'unknown error'}"
            )

        structured = getattr(
            result,
            "structuredContent",
            None,
        )

        if structured is not None:
            return structured

        content = []

        for item in result.content:

            value = getattr(item, "text", None)

            if value is not None:
                content.append(value)

        if content:
            return "\n".join(content)

        return None

    async def close(self) -> None:
        """Close the MCP session and subprocess."""

        try:
            if self._session_context is not None:
                await self._session_context.__aexit__(
                    None,
                    None,
                    None,
                )
        finally:
            try:
                if self._stdio_context is not None:
                    await self._stdio_context.__aexit__(
                        None,
                        None,
                        None,
                    )
            finally:
                self._session = None
                self._session_context = None
                self._stdio_context = None


async def register_mcp_tools(
    client: MCPClient,
    registry,
    prefix: str = "",
) -> None:
    """
    Dynamically register MCP tools in Sensai.

    A prefix can be used to avoid name collisions
    when connecting multiple MCP servers.
    """

    tools = await client.list_tools()

    for tool in tools:

        original_name = tool["name"]

        registered_name = (
            f"{prefix}{original_name}"
        )

        async def execute_mcp_tool(
            _tool_name=original_name,
            **arguments,
        ):
            return await client.call_tool(
                _tool_name,
                arguments,
            )

        registry.register(
            name=registered_name,
            description=tool["description"],
            parameters=tool["parameters"],
            function=execute_mcp_tool,
            source=f"mcp:{client.name}",
        )