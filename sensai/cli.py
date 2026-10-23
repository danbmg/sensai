"""Interface en ligne de commande : lit les commandes, affiche les Event. L'assemblage est dans sensai.app."""
import argparse
import json
import sys
from contextlib import ExitStack
from dataclasses import asdict
from typing import Iterator

from sensai.app.consultation import Consultation
from sensai.app.runtime import (DEMO_PATIENT, ModelUnusable, Runtime, RuntimeOptions, Settings,
                                StartupError, Stores, add_runtime_arguments, open_runtime)
from sensai.core.config import ConfigError
from sensai.core.interfaces import Event
from sensai.obs.metrics import load_entries, render, summarize
from sensai.rag.store import Filters

DIM, RESET = "\033[2m", "\033[0m"
HELP = "/reset efface la conversation, /quit pour quitter, /help pour les commandes"
COMMANDS = ("/patients, /patient <nom complet ou id>, /dossier, /note <texte>, /sessions, /session <id>, "
            "/history, /profile [id], /profiles, /rag, /search <question>, /sources, "
            "/rag-filter <JSON ou all>, /tools, /prompt, /metrics, /reset, /quit")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sensai", description="Assistant médical local.")
    add_runtime_arguments(parser)
    parser.add_argument("--session", help="identifiant de session à créer ou reprendre")
    parser.add_argument("--patient", help="nom complet ou identifiant du patient à sélectionner")
    parser.add_argument("--profile", help="profil médecin (défaut : profil de la session ou default)")
    parser.add_argument("--list-sessions", action="store_true", help="lister les sessions sans appeler Ollama")
    parser.add_argument("--list-profiles", action="store_true", help="lister les profils sans appeler Ollama")
    return parser


def main(argv: list[str] | None = None) -> None:
    """Point d'entrée : prépare la configuration et la base, puis lance la conversation."""
    args = _parser().parse_args(argv)
    options = RuntimeOptions.from_args(args)
    try:
        settings = Settings.load(options)
    except ConfigError as e:
        sys.exit(f"Configuration invalide : {e}")
    try:
        stores = Stores.open(args.db, args.demo)
    except StartupError as error:
        sys.exit(f"Stockage/contexte indisponible : {error}")
    if args.list_sessions:
        print("\n".join(stores.sessions.list_sessions()) or "Aucune session enregistrée.")
        return
    if args.list_profiles:
        print("\n".join(stores.profiles.list_profiles()))
        return

    with ExitStack() as stack:
        try:
            runtime = stack.enter_context(open_runtime(options, settings=settings, stores=stores))
            consultation = runtime.open_consultation(args.session, patient=args.patient, profile=args.profile,
                                                     default_patient=DEMO_PATIENT if args.demo else None)
        except (StartupError, ValueError, LookupError) as error:
            sys.exit(f"Stockage/contexte indisponible : {error}")
        except Exception as error:      # serveur MCP qui ne démarre pas…
            sys.exit(f"Sensai indisponible : {error}")
        try:
            warning = runtime.check_model()
        except ModelUnusable as error:
            sys.exit(str(error))
        if warning:
            print(warning, file=sys.stderr)
        try:
            Shell(runtime, consultation).loop()
        except KeyboardInterrupt:
            print("\nArrêt de Sensai.")


class Shell:
    """Boucle de saisie : une commande /… s'exécute sur la consultation, le reste part au modèle."""

    def __init__(self, runtime: Runtime, consultation: Consultation):
        self.runtime = runtime
        self.consultation = consultation

    def loop(self) -> None:
        print(f"{DIM}Sensai · {self.runtime.client.model} · session {self.consultation.session_id} — {HELP}{RESET}")
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
            if text.startswith("/"):
                self.command(text)
            else:
                self.ask(text)

    def ask(self, text: str) -> None:
        if self.consultation.patient_id and not self.consultation.is_refused(text):
            print(f"{DIM}Génération locale en cours (Ctrl+C pour interrompre)…{RESET}")
        try:
            _show(self.consultation.ask(text, _confirm))
        except KeyboardInterrupt:       # le tour n'est pas enregistré : la session reste intacte
            print(f"{DIM}Génération interrompue.{RESET}")

    def command(self, text: str) -> None:
        name, _, value = text.partition(" ")
        value = value.strip()
        handler = getattr(self, "cmd_" + name[1:].replace("-", "_"), None)
        if handler is None:
            print(f"Commande inconnue : {text} ({HELP})")
            return
        try:
            handler(value)
        except (KeyboardInterrupt, EOFError):
            print("\nCommande interrompue ; aucune nouvelle confirmation donnée.")
        except Exception as error:
            print(f"Commande refusée : {error}", file=sys.stderr)

    def switch(self, consultation: Consultation) -> None:
        self.consultation = consultation

    # --- Commandes (une méthode par commande : /rag-filter -> cmd_rag_filter) ---

    def cmd_help(self, _: str) -> None:
        print(COMMANDS)

    def cmd_reset(self, _: str) -> None:
        # Nouvelle session : l'ancienne reste en base ; le profil est relu (modifié entre-temps ?).
        self.switch(self.runtime.fork(self.consultation))
        print(f"{DIM}Conversation effacée.{RESET}")

    def cmd_profiles(self, _: str) -> None:
        print("\n".join(self.runtime.stores.profiles.list_profiles()))

    def cmd_profile(self, value: str) -> None:
        if value:
            self.switch(self.runtime.fork(self.consultation, profile=value))
        print(json.dumps(asdict(self.consultation.context.profile), ensure_ascii=False, indent=2))

    def cmd_rag(self, _: str) -> None:
        context = self.consultation.context
        print("RAG actif" if context.retriever else "RAG inactif : aucun index chargé ou recherche désactivée.")
        print(f"Mode de recherche : {context.search_mode}")
        print(json.dumps(asdict(context.filters), ensure_ascii=False))

    def cmd_rag_filter(self, value: str) -> None:
        self.consultation.set_filters(Filters() if value == "all" else Filters(**json.loads(value)))
        print("Filtres documentaires mis à jour.")

    def cmd_sources(self, _: str) -> None:
        print(json.dumps(self.consultation.sources(), ensure_ascii=False, indent=2))

    def cmd_search(self, value: str) -> None:
        _require(value, "/search <question>")
        print(self.consultation.search(value))

    def cmd_patients(self, _: str) -> None:
        for patient in self.runtime.stores.patients.list_patients():
            print(f"{patient['patient_id']} : {patient['name']}")

    def cmd_patient(self, value: str) -> None:
        _require(value, "/patient <nom complet ou id>")
        patient = self.runtime.stores.patients.resolve_patient(value)
        if patient["patient_id"] != self.consultation.patient_id:   # autre patient : autre session
            self.switch(self.runtime.fork(self.consultation, patient=patient["patient_id"]))
        print(f"Patient sélectionné : {patient['name']} · session {self.consultation.session_id}")

    def cmd_dossier(self, _: str) -> None:
        print(json.dumps(self.consultation.patient_record(), ensure_ascii=False, indent=2))

    def cmd_note(self, value: str) -> None:
        _require(value, "/note <texte>")
        result = self.consultation.add_note(value, _confirm)
        print(result.content if result else "Action refusée par le médecin.")

    def cmd_sessions(self, _: str) -> None:
        print("\n".join(self.runtime.stores.sessions.list_sessions()) or "Aucune session enregistrée.")

    def cmd_history(self, _: str) -> None:
        print(json.dumps(self.consultation.history(), ensure_ascii=False, indent=2))

    def cmd_session(self, value: str) -> None:
        _require(value, "/session <id>")
        try:
            self.switch(self.runtime.consultation(value))
        except KeyError:                # session inconnue : on la crée avec le patient courant
            self.switch(self.runtime.fork(self.consultation, session_id=value))
        print(f"Session {value} : {len(self.consultation.history())} messages")

    def cmd_tools(self, _: str) -> None:
        for schema in self.runtime.tools.schemas():
            function = schema["function"]
            danger = " (validation du médecin)" if self.runtime.tools.is_dangerous(function["name"]) else ""
            print(f"{function['name']} : {function.get('description', '')}{danger}")

    def cmd_prompt(self, _: str) -> None:
        prompt = self.consultation.last_prompt()
        if prompt is None:
            print("Aucun prompt envoyé au modèle dans cette session depuis le lancement.")
            return
        print(f"{DIM}Prompt exact du dernier tour, tel que reçu par {prompt['model']} (pseudonymisé) :{RESET}")
        print(json.dumps(prompt["messages"], ensure_ascii=False, indent=2))
        print(f"{DIM}Outils proposés : {', '.join(prompt['tools']) or 'aucun'} · "
              f"{_usage_line(prompt)}{RESET}")

    def cmd_metrics(self, _: str) -> None:
        if self.runtime.logger is None:
            print("Logs désactivés ([logging] enabled = false).")
            return
        entries, skipped = load_entries(self.runtime.logger.directory)
        print(render(summarize(entries), skipped))


def _require(value: str, usage: str) -> None:
    if not value:
        raise ValueError(f"usage : {usage}")


def _confirm(call_id: str, tool: str, args: dict) -> bool:
    """Demande au médecin de valider l'action (arguments en clair) ; refus par défaut."""
    print(f"Action proposée : {tool}({json.dumps(args, ensure_ascii=False)})")
    try:
        return input("Confirmer ? [o/N] ").strip().casefold() in {"o", "oui"}
    except (KeyboardInterrupt, EOFError):
        return False


def _usage_line(usage: dict) -> str:
    window = usage.get("context_window")
    context = f"{usage['context_tokens']}/{window}" if window else str(usage["context_tokens"])
    return (f"tokens : {usage['prompt_tokens']} lus + {usage['completion_tokens']} générés · "
            f"contexte {context}")


def _show(events: Iterator[Event]) -> bool:
    """Affiche au fil de l'eau les Event du pipeline (en clair) ; True si le tour est enregistré."""
    mid_line = False                # une réponse est en cours sur la ligne
    completed = False
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
                content = event.data["content"]     # un dossier complet tient sur une ligne : abrégé
                print(f"{DIM}← {content if len(content) <= 200 else content[:200] + ' […]'}{RESET}")
            elif event.type == "sources":
                print(f"{DIM}Sources : " + " · ".join(f"[{s['citation']}] {s['title']} ({s['publisher']}, p. {s['page']})"
                                                     for s in event.data) + RESET)
            elif event.type == "usage" and event.data["prompt_tokens"]:
                print(f"{DIM}{_usage_line(event.data)}{RESET}")
            elif event.type == "error":
                print(event.data, file=sys.stderr)
            elif event.type == "done":
                completed = True
    finally:
        events.close()              # sur Ctrl+C : ferme le flux, Ollama arrête de générer
        if mid_line:
            print()
    return completed
