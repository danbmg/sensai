"""Interface en ligne de commande."""
import argparse
import sys

import requests

from sensai.core.config import ConfigError, load_config
from sensai.core.interfaces import Message
from sensai.core.ollama_client import ModelNotFoundError, OllamaClient, OllamaError

DIM, RESET = "\033[2m", "\033[0m"
HELP = "/reset efface la conversation, /quit pour quitter"
OLLAMA_ERRORS = (OllamaError, requests.RequestException)


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
    _check_model(client)
    system = [{"role": "system", "content": cfg.system_prompt}] if cfg.system_prompt else []
    history: list[Message] = []     # tours précédents (user/assistant), renvoyés à chaque appel

    print(f"{DIM}Sensai · {cfg.model} — {HELP}{RESET}")
    while True:
        try:
            text = input("> ").strip()
        except EOFError:            # Ctrl+D
            print()
            return
        except KeyboardInterrupt:   # Ctrl+C à l'invite : on abandonne la ligne, pas la session
            print(f"\n{DIM}{HELP}{RESET}")
            continue
        if not text:
            continue
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
        try:
            answer = _stream(client, system + history + [user])
        except KeyboardInterrupt:
            print(f"{DIM}Génération interrompue.{RESET}")
            continue
        except OLLAMA_ERRORS as e:
            print(_explain(e, client), file=sys.stderr)
            continue
        # Le tour n'entre dans l'historique qu'une fois la réponse complète reçue.
        history += [user, {"role": "assistant", "content": answer}]


def _check_model(client: OllamaClient) -> None:
    """Au démarrage (/api/show) : quitte si le modèle est inutilisable, avertit s'il est lent."""
    try:
        capabilities = client.capabilities()
    except OLLAMA_ERRORS as e:
        sys.exit(_explain(e, client))
    if "tools" not in capabilities:
        sys.exit(f"{client.model} ne sait pas appeler d'outils (capacité « tools » absente) : "
                 "choisissez un autre modèle.")
    if "thinking" in capabilities:
        print(f"⚠ {client.model} est un modèle « thinking » : il raisonne avant de répondre, "
              "trop lent sur CPU pour la démo.", file=sys.stderr)


def _explain(e: Exception, client: OllamaClient) -> str:
    """Message lisible pour une erreur d'Ollama, à la place du traceback."""
    if isinstance(e, ModelNotFoundError):
        return f"Modèle {client.model} absent. Installez-le avec : ollama pull {client.model}"
    if isinstance(e, requests.ConnectionError):  # avant Timeout : ConnectTimeout hérite des deux
        return f"Ollama ne répond pas sur {client.host}. Lancez-le avec : ollama serve"
    if isinstance(e, requests.Timeout):
        return f"Ollama ne répond plus : aucun fragment reçu en {client.timeout:g} s."
    return f"Erreur d'Ollama : {e}"


def _stream(client: OllamaClient, messages: list[Message]) -> str:
    """Affiche la réponse au fil de l'eau et la renvoie complète (sans le raisonnement)."""
    answer = ""
    stream = client.chat_stream(messages)
    try:
        for chunk in stream:
            if chunk.thinking:
                print(f"{DIM}{chunk.thinking}{RESET}", end="", flush=True)
            print(chunk.content, end="", flush=True)
            answer += chunk.content
    finally:
        stream.close()              # ferme la connexion, y compris sur Ctrl+C : Ollama arrête de générer
        print()
    return answer
