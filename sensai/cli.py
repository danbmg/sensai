"""Interface en ligne de commande."""
import argparse
import sys

from sensai.core.config import ConfigError, load_config
from sensai.core.ollama_client import OllamaClient

DIM, RESET = "\033[2m", "\033[0m"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="sensai", description="Assistant médical local.")
    parser.add_argument("--model", help="modèle Ollama (défaut : celui de config.toml)")
    parser.add_argument("--config", help="fichier de configuration (défaut : config.toml du projet)")
    args = parser.parse_args(argv)

    try:
        cfg = load_config(args.config, model=args.model)
    except ConfigError as e:
        sys.exit(f"Configuration invalide : {e}")

    client = OllamaClient(cfg.model, cfg.host, options={"temperature": cfg.temperature})
    messages = [{"role": "system", "content": cfg.system_prompt}] if cfg.system_prompt else []
    messages.append({"role": "user", "content": input("> ")})
    for chunk in client.chat_stream(messages):
        if chunk.thinking:
            print(f"{DIM}{chunk.thinking}{RESET}", end="", flush=True)
        print(chunk.content, end="", flush=True)
    print()
