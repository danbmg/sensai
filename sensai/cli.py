"""Interface en ligne de commande."""
import argparse

from sensai.core.ollama_client import OllamaClient

DIM, RESET = "\033[2m", "\033[0m"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="sensai", description="Assistant médical local.")
    parser.add_argument("--model", default="qwen3:4b", help="modèle Ollama à utiliser")
    args = parser.parse_args(argv)

    client = OllamaClient(args.model)
    question = input("> ")
    for chunk in client.chat_stream([{"role": "user", "content": question}]):
        if chunk.thinking:
            print(f"{DIM}{chunk.thinking}{RESET}", end="", flush=True)
        print(chunk.content, end="", flush=True)
    print()
