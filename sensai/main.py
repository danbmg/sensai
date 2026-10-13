
import argparse
import asyncio
import json
from pathlib import Path

from ollama_client import OllamaClient, OllamaError
from tools.registry import ToolRegistry
from tools.basic_tools import register_basic_tools
from mcp_client.client import MCPClient, MCPClientError, register_mcp_tools


MAX_TOOL_ITERATIONS = 5

# Only expose read-only tools from the external Filesystem server.
FILESYSTEM_ALLOWED_TOOLS = {
    "list_directory",
    "list_directory_with_sizes",
    "directory_tree",
    "read_file",
    "read_text_file",
    "read_multiple_files",
    "get_file_info",
    "list_allowed_directories",
    "search_files",
}


SYSTEM_PROMPT = """
You are Sensai, a local AI developer assistant.

You have access to local tools and MCP tools.

Rules:
- Use tools whenever they are useful to answer the user.
- Use calculator for arithmetic.
- Use get_current_time for the current date or time.
- Use project_overview to understand the project.
- Use inspect_project_directory to inspect a directory.
- Use inspect_python_file to analyze a Python file.
- Use read_project_file to read source code.
- Use find_in_code to search the project.
- Use repository_status and repository_diff for Git information.
- Use execute_tests to run project tests.
- Tools starting with fs_ belong to an external Filesystem MCP server.
- Use fs_ tools to inspect the external test workspace.
- File tools may require an absolute path or a relative path,
  depending on their declared schema.
- Always follow the exact argument names in each tool schema.
- Never invent tool results.
- Never claim to have read a file without using a tool.
- Never claim to have executed tests without using a tool.
- Respect workspace access restrictions.
- If a tool fails, explain the error or try a valid alternative.
- Give clear and concise final answers.
- IMPORTANT: Filesystem MCP tools use the argument "path", not "file_path".
- For fs_read_text_file, always call it with {"path": "/absolute/path/to/file"}.
- For fs_list_directory, always call it with {"path": "/absolute/path/to/directory"}.
- Never replace a tool's declared argument name with a synonym.
""".strip()


async def run_agent(
    client: OllamaClient,
    registry: ToolRegistry,
    messages: list[dict],
) -> str:
    """
    Run the agent loop.

    The model can request tools, receive their results,
    and continue reasoning before producing an answer.
    """

    for iteration in range(MAX_TOOL_ITERATIONS):

        response = client.chat(
            messages=messages,
            tools=registry.ollama_tools(),
        )

        assistant_message = response.get("message")

        if not assistant_message:
            return "Ollama returned no assistant message."

        messages.append(assistant_message)

        tool_calls = assistant_message.get("tool_calls") or []

        if not tool_calls:
            return assistant_message.get("content", "")

        print(
            f"\n[Agent] iteration {iteration + 1}: "
            f"{len(tool_calls)} tool call(s)"
        )

        for tool_call in tool_calls:

            function = tool_call.get("function", {})
            tool_name = function.get("name")
            arguments = function.get("arguments", {})

            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError:
                    arguments = {}

            if not isinstance(arguments, dict):
                arguments = {}

            print(f"[Tool] {tool_name}({arguments})")

            result = await registry.execute(
                tool_name,
                arguments,
            )

            print(f"[Result] {result}")

            messages.append(
                {
                    "role": "tool",
                    "tool_name": tool_name,
                    "content": result,
                }
            )

    return (
        "Maximum number of tool iterations reached. "
        "The request was stopped to prevent an infinite loop."
    )


async def connect_mcp(
    client: MCPClient,
    registry: ToolRegistry,
    connected_clients: list[MCPClient],
    prefix: str = "",
    allowed_tools: set[str] | None = None,
) -> bool:
    """
    Connect to an MCP server and register its tools.

    If allowed_tools is provided, only those tools
    are exposed to the language model.
    """

    try:
        print(f"Connecting to {client.name} MCP...")

        await client.connect()

        # Keep track of the connected process immediately, so it can be closed even if registration fails.
        connected_clients.append(client)

        if allowed_tools is None:
            await register_mcp_tools(
                client,
                registry,
                prefix=prefix,
            )
        else:
            tools = await client.list_tools()

            for tool in tools:
                if tool["name"] not in allowed_tools:
                    continue

                original_name = tool["name"]
                registered_name = f"{prefix}{original_name}"

                async def execute_external_tool(
                    _tool_name=original_name,
                    _client=client,
                    **arguments,
                ):
                    return await _client.call_tool(
                        _tool_name,
                        arguments,
                    )

                registry.register(
                    name=registered_name,
                    description=tool["description"],
                    parameters=tool["parameters"],
                    function=execute_external_tool,
                    source=f"mcp:{client.name}",
                )

        print(f"{client.name.capitalize()} MCP connected.")
        return True

    except Exception as error:
        print(f"{client.name.capitalize()} MCP warning: {error}")
        return False


async def main():

    parser = argparse.ArgumentParser(
        description="Sensai local AI assistant"
    )

    parser.add_argument(
        "--model",
        default="qwen2.5:3b",
        help="Ollama model to use",
    )

    parser.add_argument(
        "--workspace",
        default=".",
        help="Workspace accessible to Developer MCP",
    )

    args = parser.parse_args()

    registry = ToolRegistry()
    register_basic_tools(registry)

    mcp_clients = []

    try:

        developer_mcp = MCPClient(
            workspace=args.workspace,
            name="developer",
        )

        developer_connected = await connect_mcp(
            developer_mcp,
            registry,
            mcp_clients,
        )

        test_workspace = (
            Path("mcp_test_workspace").resolve()
        )

        test_workspace.mkdir(
            parents=True,
            exist_ok=True,
        )

        filesystem_mcp = MCPClient(
            name="filesystem",
            command="npx",
            args=[
                "-y",
                "@modelcontextprotocol/server-filesystem",
                str(test_workspace),
            ],
        )

        filesystem_connected = await connect_mcp(
            filesystem_mcp,
            registry,
            mcp_clients,
            prefix="fs_",
            allowed_tools=FILESYSTEM_ALLOWED_TOOLS,
        )

        # Ollama

        client = OllamaClient(
            model=args.model,
        )

        messages = [
            {
                "role": "system",
                "content": (
                    SYSTEM_PROMPT
                    + "\nExternal Filesystem MCP workspace: "
                    + str(test_workspace)
                ),
            }
        ]

        # CLI

        print()
        print("=" * 50)
        print("SENSAI")
        print("=" * 50)

        print(f"Model: {args.model}")
        print(f"Workspace: {args.workspace}")

        connected_count = (
            int(developer_connected)
            + int(filesystem_connected)
        )

        print(
            f"MCP servers connected: {connected_count}"
        )

        print("\nTools:")

        for tool in registry.describe_tools():
            print(
                f"  - {tool['name']} "
                f"[{tool['source']}]"
            )

        print("\nType /exit to quit.")
        print("Type /tools to list tools.\n")

        # Conversation loop

        while True:

            try:
                user_input = input("You > ").strip()

            except (KeyboardInterrupt, EOFError):
                print("\nBye!")
                break

            if user_input == "/exit":
                print("Bye!")
                break

            if user_input == "/tools":
                print("\nAvailable tools:")

                for tool in registry.describe_tools():
                    print(
                        f"- {tool['name']} "
                        f"[{tool['source']}]"
                    )

                print()
                continue

            if not user_input:
                print("Input cannot be empty.\n")
                continue

            messages.append(
                {
                    "role": "user",
                    "content": user_input,
                }
            )

            try:
                answer = await run_agent(
                    client,
                    registry,
                    messages,
                )

                print(f"\nSensai > {answer}\n")

            except OllamaError as error:
                print(f"\nOllama error: {error}\n")

                if (
                    messages
                    and messages[-1].get("role") == "user"
                ):
                    messages.pop()

            except Exception as error:
                print(f"\nUnexpected error: {error}\n")

    finally:
        for mcp_client in reversed(mcp_clients):
            try:
                await mcp_client.close()
            except Exception as error:
                print(
                    f"Error closing MCP "
                    f"'{mcp_client.name}': {error}"
                )


if __name__ == "__main__":
    asyncio.run(main())
