"""Interface en ligne de commande."""
import argparse
import sys
import uuid
from typing import Iterator

from sensai.core.config import ConfigError, load_config
from sensai.core.interfaces import Event
from sensai.core.ollama_client import OLLAMA_ERRORS, OllamaClient, describe_error
from sensai.core.pipeline import Pipeline
from sensai.guardrails.input_guardrail import SensaiInputGuard
from sensai.guardrails.output_guardrail import SensaiOutputGuard
from sensai.guardrails.pii_vault import SensaiPIIVault

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
    _check_model(client)
    pipeline = Pipeline(
        client,
        cfg.system_prompt,
        cfg.max_tool_iterations,
        input_guard=SensaiInputGuard(),
        output_guard=SensaiOutputGuard(),
        vault_factory=SensaiPIIVault,
    )
    session_id = uuid.uuid4().hex

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
        if text == "/reset":        # nouvelle session : l'ancienne reste dans le SessionStore
            session_id = uuid.uuid4().hex
            print(f"{DIM}Conversation effacée.{RESET}")
            continue
        if text.startswith("/"):
            print(f"Commande inconnue : {text} ({HELP})")
            continue

        try:
            _show(pipeline.run(text, session_id, _refuse))
        except KeyboardInterrupt:   # le tour n'est pas enregistré : la session reste intacte
            print(f"{DIM}Génération interrompue.{RESET}")


def _check_model(client: OllamaClient) -> None:
    """Au démarrage (/api/show) : quitte si le modèle est inutilisable, avertit s'il est lent."""
    try:
        capabilities = client.capabilities()
    except OLLAMA_ERRORS as e:
        sys.exit(describe_error(e, client))
    if "tools" not in capabilities:
        sys.exit(f"{client.model} ne sait pas appeler d'outils (capacité « tools » absente) : "
                 "choisissez un autre modèle.")
    if "thinking" in capabilities:
        print(f"⚠ {client.model} est un modèle « thinking » : il raisonne avant de répondre, "
              "trop lent sur CPU pour la démo.", file=sys.stderr)


def _refuse(call_id: str, tool: str, args: dict) -> bool:
    return False                    # étape 8 : demander au médecin (« Confirmer ? [o/N] »)


def _show(events: Iterator[Event]) -> None:
    """Affiche au fil de l'eau les Event du pipeline (en clair)."""
    mid_line = False                # une réponse est en cours sur la ligne
    try:
        for event in events:
            if event.type == "token":
                print(event.data, end="", flush=True)
                mid_line = True
                continue
            if mid_line:
                print()
                mid_line = False
            if event.type == "tool_call":
                args = ", ".join(f"{k}={v!r}" for k, v in event.data["args"].items())
                print(f"{DIM}→ {event.data['tool']}({args}){RESET}")
            elif event.type == "tool_result":
                print(f"{DIM}← {event.data['content']}{RESET}")
            elif event.type == "error":
                print(event.data, file=sys.stderr)
    finally:
        events.close()              # sur Ctrl+C : ferme le flux, Ollama arrête de générer
        if mid_line:
            print()
