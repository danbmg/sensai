import inspect
import json
from typing import Any, Callable


class ToolRegistry:
    """
    Central registry for every tool available to Sensai.

    A tool may come from:
    - local Python code
    - an MCP server
    """

    def __init__(self):
        self._tools: dict[str, dict[str, Any]] = {}

    def register(
        self,
        name: str,
        description: str,
        parameters: dict,
        function: Callable,
        source: str = "local",
    ) -> None:

        if name in self._tools:
            raise ValueError(
                f"Tool '{name}' is already registered."
            )

        self._tools[name] = {
            "name": name,
            "description": description,
            "parameters": parameters,
            "function": function,
            "source": source,
        }

    def has_tool(self, name: str) -> bool:
        return name in self._tools

    def list_tools(self) -> list[str]:
        return list(self._tools.keys())

    def describe_tools(self) -> list[dict]:
        return [
            {
                "name": tool["name"],
                "source": tool["source"],
            }
            for tool in self._tools.values()
        ]

    async def execute(
        self,
        name: str,
        arguments: dict,
    ) -> str:

        if not self.has_tool(name):
            return json.dumps(
                {
                    "success": False,
                    "error": f"Unknown tool: {name}",
                },
                ensure_ascii=False,
            )

        tool = self._tools[name]

        try:
            result = tool["function"](**arguments)

            if inspect.isawaitable(result):
                result = await result

            return json.dumps(
                {
                    "success": True,
                    "source": tool["source"],
                    "result": result,
                },
                ensure_ascii=False,
            )

        except TypeError as error:
            return json.dumps(
                {
                    "success": False,
                    "source": tool["source"],
                    "error": (
                        f"Invalid arguments: {error}"
                    ),
                },
                ensure_ascii=False,
            )

        except Exception as error:
            return json.dumps(
                {
                    "success": False,
                    "source": tool["source"],
                    "error": str(error),
                },
                ensure_ascii=False,
            )

    def ollama_tools(self) -> list[dict]:
        tools = []

        for tool in self._tools.values():
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool["name"],
                        "description": tool[
                            "description"
                        ],
                        "parameters": tool[
                            "parameters"
                        ],
                    },
                }
            )

        return tools