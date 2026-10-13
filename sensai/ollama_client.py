import requests


class OllamaError(Exception):
    """Error raised when communication with Ollama fails."""


class OllamaClient:
    def __init__(
        self,
        model: str = "qwen2.5:3b",
        base_url: str = "http://localhost:11434",
    ):
        self.model = model
        self.base_url = base_url.rstrip("/")

    def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
    ) -> dict:
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
        }

        if tools:
            payload["tools"] = tools

        try:
            response = requests.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=120,
            )

        except requests.exceptions.ConnectionError as error:
            raise OllamaError(
                "Impossible de contacter Ollama. "
                "Vérifie qu'Ollama est lancé."
            ) from error

        except requests.exceptions.Timeout as error:
            raise OllamaError(
                "Ollama met trop de temps à répondre."
            ) from error

        if not response.ok:
            raise OllamaError(
                f"Ollama HTTP {response.status_code}: "
                f"{response.text}"
            )

        try:
            return response.json()

        except ValueError as error:
            raise OllamaError(
                "Ollama returned invalid JSON."
            ) from error