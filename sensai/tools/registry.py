
"""Registre des outils disponibles dans SENSAI."""

import asyncio
import inspect
import json
from concurrent.futures import Future
from threading import Thread
from typing import Any, Callable

from sensai.core.interfaces import ToolResult


class AsyncRunner:
    """Exécute les opérations MCP sur une boucle asynchrone dédiée."""

    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self.thread = Thread(
            target=self.loop.run_forever,
            daemon=True,
            name="sensai-mcp-loop",
        )
        self.thread.start()

    def run(self, coroutine, timeout: float = 30):
        future: Future = asyncio.run_coroutine_threadsafe(
            coroutine, self.loop
        )
        try:
            return future.result(timeout=timeout)
        except TimeoutError:
            future.cancel()
            raise TimeoutError("L'opération MCP a dépassé le délai autorisé.") from None

    def close(self):
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(timeout=5)
        if not self.thread.is_alive():
            self.loop.close()


class ToolRegistry:
    """Implémente le contrat ToolRegistry du pipeline."""

    def __init__(self, runner: AsyncRunner | None = None):
        self._tools: dict[str, dict[str, Any]] = {}
        self.runner = runner
        # Outil tiers -> mots qui le proposent au modèle quand un dossier est ouvert.
        self.keywords: dict[str, tuple[str, ...]] = {}

    def register(
        self,
        name: str,
        description: str,
        parameters: dict,
        function: Callable,
        source: str = "local",
        dangerous: bool = False,
    ) -> None:
        if name in self._tools:
            raise ValueError(f"Tool '{name}' is already registered.")

        self._tools[name] = {
            "name": name,
            "description": description,
            "parameters": parameters,
            "function": function,
            "source": source,
            "dangerous": dangerous,
        }

    def schemas(self) -> list[dict]:
        """Schémas des outils au format attendu par Ollama."""
        return [
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool["parameters"],
                },
            }
            for tool in self._tools.values()
        ]

    def is_dangerous(self, name: str) -> bool:
        # Par sécurité, un outil inconnu nécessite confirmation.
        if name not in self._tools:
            return True
        return self._tools[name]["dangerous"]

    def call(self, name: str, args: dict) -> ToolResult:
        """Exécution synchrone attendue par Pipeline."""
        if name not in self._tools:
            return ToolResult(
                content=f"Outil inconnu : {name}",
                is_error=True,
            )

        if not isinstance(args, dict):
            return ToolResult(
                content="Les arguments doivent être un dictionnaire.",
                is_error=True,
            )

        tool = self._tools[name]

        try:
            function = tool["function"]

            if inspect.iscoroutinefunction(function):
                if self.runner is None:
                    return ToolResult(
                        content="Aucune boucle asynchrone MCP configurée.",
                        is_error=True,
                    )
                result = self.runner.run(function(**args))
            else:
                result = function(**args)
                if inspect.isawaitable(result):
                    if self.runner is None:
                        return ToolResult(
                            content="Aucune boucle asynchrone configurée.",
                            is_error=True,
                        )
                    result = self.runner.run(result)

            content = (
                result
                if isinstance(result, str)
                else json.dumps(result, ensure_ascii=False, default=str)
            )
            return ToolResult(content=content)

        except Exception as error:
            return ToolResult(
                content=f"Erreur de l'outil '{name}': {error}",
                is_error=True,
            )
