"""Interface en ligne de commande."""
import argparse
import sys

from sensai.core.config import ConfigError, load_config
from sensai.core.interfaces import Message
from sensai.core.ollama_client import OllamaClient

DIM, RESET = "\033[2m", "\033[0m"
HELP = "/reset efface la conversation, /quit pour quitter"


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
    system = [{"role": "system", "content": cfg.system_prompt}] if cfg.system_prompt else []
    history: list[Message] = []     # tours précédents (user/assistant), renvoyés à chaque appel

    print(f"{DIM}Sensai · {cfg.model} — {HELP}{RESET}")
    while True:
        try:
            text = input("> ").strip()
        except EOFError:            # Ctrl+D
            print()
            return
        if text == "/quit":
            return
        if text == "/reset":
            history.clear()
            print(f"{DIM}Conversation effacée.{RESET}")
            continue
        if text.startswith("/"):
            print(f"Commande inconnue : {text} ({HELP})")
            continue

        user = {"role": "user", "content": text}
        answer = _stream(client, system + history + [user])
        # Le tour n'entre dans l'historique qu'une fois la réponse complète reçue.
        history += [user, {"role": "assistant", "content": answer}]


def _stream(client: OllamaClient, messages: list[Message]) -> str:
    """Affiche la réponse au fil de l'eau et la renvoie complète (sans le raisonnement)."""
    answer = ""
    for chunk in client.chat_stream(messages):
        if chunk.thinking:
            print(f"{DIM}{chunk.thinking}{RESET}", end="", flush=True)
        print(chunk.content, end="", flush=True)
        answer += chunk.content
    print()
    return answer
