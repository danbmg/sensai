"""Interface en ligne de commande."""
import argparse
import sys
import uuid
import json
import re
from dataclasses import asdict
from pathlib import Path
from typing import Iterator

from sensai.core.config import ConfigError, load_config
from sensai.core.interfaces import Event
from sensai.core.ollama_client import OLLAMA_ERRORS, OllamaClient, describe_error
from sensai.core.pipeline import Pipeline
from sensai.guardrails.input_guardrail import SensaiInputGuard
from sensai.guardrails.output_guardrail import SensaiOutputGuard
from sensai.guardrails.pii_vault import SensaiPIIVault
from sensai.memory.context import PatientContext
from sensai.memory.fixtures import seed_demo_patients
from sensai.memory.patients import PatientStore
from sensai.memory.sessions import SQLiteSessionStore
from sensai.memory.profiles import DoctorProfileStore
from sensai.rag.embeddings import OllamaEmbeddings
from sensai.rag.retrieval import Hit, Retriever, format_context, source_records
from sensai.rag.settings import load_settings, resolve_index_path
from sensai.rag.store import Filters, VectorStore
from sensai.tools.runtime import medical_tools

DIM, RESET = "\033[2m", "\033[0m"
HELP = "/reset efface la conversation, /quit pour quitter, /help pour les commandes"


def _keep_alive(value: str) -> int | str:
    if value == "0":
        return 0
    if not re.fullmatch(r"[1-9]\d*(?:s|m|h)", value):
        raise argparse.ArgumentTypeError("Durée attendue : 0, 30s, 2m ou 1h.")
    return value


def main(argv: list[str] | None = None) -> None:
    """Point d'entrée : prépare base, outils et pipeline, puis lance la conversation."""
    parser =argparse.ArgumentParser(prog="sensai", description="Assistant médical local.")
    parser.add_argument("--model", help="modèle Ollama (défaut : celui de config.toml)")
    parser.add_argument("--config", help="fichier de configuration (défaut : config.toml du projet)")
    parser.add_argument("--db", type=Path, default=Path(".sensai/memory.sqlite3"), help="base SQLite locale")
    parser.add_argument("--session", help="identifiant de session à créer ou reprendre")
    parser.add_argument("--list-sessions", action="store_true", help="lister les sessions sans appeler Ollama")
    parser.add_argument("--demo", action="store_true", help="charger les patients fictifs")
    parser.add_argument("--patient", help="nom complet ou identifiant du patient à sélectionner")
    parser.add_argument("--mcp", action="store_true", help="utiliser le serveur MCP médical pour les outils patients")
    parser.add_argument("--profile", help="profil médecin (défaut : profil de la session ou default)")
    parser.add_argument("--list-profiles", action="store_true", help="lister les profils sans appeler Ollama")
    parser.add_argument("--rag-index", type=Path, help="index documentaire séparé de la base patients")
    parser.add_argument("--no-rag", action="store_true", help="désactiver la recherche documentaire pour cette exécution")
    parser.add_argument("--keep-alive", type=_keep_alive, default=0,
                        help="garder le modèle en RAM entre les appels (ex. 2m ; défaut 0 pour libérer la RAM)")
    args = parser.parse_args(argv)

    try:
        cfg = load_config(args.config, model=args.model)
        rag = load_settings(args.config)
    except ConfigError as e:
        sys.exit(f"Configuration invalide : {e}")

    try:
        patients = PatientStore(args.db)
        sessions = SQLiteSessionStore(args.db)
        profiles = DoctorProfileStore(args.db)
        profiles.ensure_default()
        if args.demo:
            seed_demo_patients(patients)
        if args.list_sessions:
            print("\n".join(sessions.list_sessions()) or "Aucune session enregistrée.")
            return
        if args.list_profiles:
            print("\n".join(profiles.list_profiles()))
            return
        retriever = None
        index_path = args.rag_index or resolve_index_path(rag, args.db)
        if rag.enabled and not args.no_rag:
            if index_path.resolve() == args.db.resolve():
                raise ValueError("L'index RAG doit être séparé de la base patients.")
            index = VectorStore(index_path)
            if index.list_documents():
                embedder = OllamaEmbeddings(rag.model, cfg.host, rag.timeout, rag.batch_size)
                retriever = Retriever(index, embedder, top_k=rag.top_k, candidates=rag.candidates,
                                      min_similarity=rag.min_similarity, min_relevance=rag.min_relevance,
                                      rerank=rag.rerank)
        saved = sessions.load_context(args.session) if args.session else {}
        profile_id = args.profile or saved.get("profile_id") or "default"
        if saved and args.profile and args.profile != saved.get("profile_id"):
            raise ValueError("Cette session utilise un autre profil. Choisissez un nouvel identifiant de session.")
        context = PatientContext(patients, profile=profiles.load(profile_id), retriever=retriever,
                                 max_context_chars=rag.max_context_chars, profiles=profiles,
                                 search_mode=rag.search_mode)
        if saved:
            _restore_context(context, saved)
        if args.patient:
            requested = patients.resolve_patient(args.patient)
            if saved and requested["patient_id"] != saved.get("patient_id"):
                raise ValueError("Cette session appartient à un autre patient. Choisissez une nouvelle session.")
            context.select(args.patient)
        elif args.demo and not saved:
            context.select(args.patient or "demo-dupont")
    except Exception as error:
        sys.exit(f"Stockage/contexte indisponible : {error}")

    client = OllamaClient(cfg.model, cfg.host, options={"temperature": cfg.temperature,
                         "num_ctx": cfg.num_ctx, "num_predict": cfg.num_predict,
                         "num_thread": cfg.num_thread, "num_batch": cfg.num_batch},
                         timeout=cfg.timeout, keep_alive=args.keep_alive)
    _check_model(client)
    try:
        with medical_tools(patients, args.mcp) as registry:
            pipeline = Pipeline(
                client, cfg.system_prompt, cfg.max_tool_iterations,
                input_guard=SensaiInputGuard(), output_guard=SensaiOutputGuard(),
                vault_factory=lambda mapping: SensaiPIIVault(mapping, patients=patients.list_patients()),
                context=context, sessions=sessions, tools=registry,
            )
            _conversation(pipeline, context, args.session or uuid.uuid4().hex)
    except KeyboardInterrupt:
        print("\nArrêt de Sensai.")
    except Exception as error:
        sys.exit(f"Sensai indisponible : {error}")


def _conversation(pipeline: Pipeline, context: PatientContext, session_id: str) -> None:
    """Boucle de saisie : exécute les commandes /… ou envoie la question au pipeline."""
    print(f"{DIM}Sensai · {pipeline.client.model} · session {session_id} — {HELP}{RESET}")
    _save_context(pipeline, context, session_id)
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
            _refresh_context(context)
            _save_context(pipeline, context, session_id)
            print(f"{DIM}Conversation effacée.{RESET}")
            continue
        if text.startswith("/"):
            try:
                command, _, value = text.partition(" ")
                value = value.strip()
                if command == "/help":
                    print("/patients, /patient <nom complet ou id>, /dossier, /note <texte>, "
                          "/sessions, /session <id>, /history, /profile [id], /profiles, "
                          "/rag, /search <question>, /sources, /rag-filter <JSON ou all>, /tools, /reset, /quit")
                elif command == "/profiles":
                    print("\n".join(context.profiles.list_profiles()))
                elif command == "/profile":
                    if value:
                        context.profile = context.profiles.load(value)
                        session_id = uuid.uuid4().hex
                        _refresh_context(context)
                        _save_context(pipeline, context, session_id)
                    print(json.dumps(asdict(context.profile), ensure_ascii=False, indent=2))
                elif command == "/rag":
                    print("RAG actif" if context.retriever else "RAG inactif : aucun index chargé ou recherche désactivée.")
                    print(f"Mode de recherche : {context.search_mode}")
                    print(json.dumps(asdict(context.filters), ensure_ascii=False))
                elif command == "/rag-filter":
                    filters = Filters() if value == "all" else Filters(**json.loads(value))
                    filters.validate()
                    context.filters, context.last_hits = filters, []
                    _save_context(pipeline, context, session_id)
                    print("Filtres documentaires mis à jour.")
                elif command == "/sources":
                    print(json.dumps(source_records(context.last_hits), ensure_ascii=False, indent=2))
                elif command == "/search" and value:
                    if context.retriever is None:
                        raise ValueError("Aucun index documentaire chargé. Utilisez python -m sensai.rag index.")
                    state = pipeline.sessions.load(session_id)
                    masked = pipeline.vault_factory(state.pii_map).mask(value)
                    hits = context.retriever.search(masked, context.filters)
                    text, context.last_hits = format_context(hits, context.max_context_chars)
                    _save_context(pipeline, context, session_id)
                    print(text)
                elif command == "/patients":
                    for patient in context.patients.list_patients():
                        print(f"{patient['patient_id']} : {patient['name']}")
                elif command == "/patient" and value:
                    previous = context.patient_id
                    patient = context.select(value)
                    if previous != context.patient_id:
                        session_id = uuid.uuid4().hex
                        _refresh_context(context)
                        _save_context(pipeline, context, session_id)
                    print(f"Patient sélectionné : {patient['name']} · session {session_id}")
                elif command == "/dossier":
                    if context.patient_id is None:
                        raise ValueError("Sélectionnez un patient avec /patient.")
                    print(json.dumps(context.patients.get_patient(context.patient_id), ensure_ascii=False, indent=2))
                elif command == "/note" and value:
                    if context.patient_id is None:
                        raise ValueError("Sélectionnez un patient avec /patient.")
                    tool_args = {"patient": context.patient_id, "note": value}
                    if _confirm(uuid.uuid4().hex, "add_patient_note", tool_args):
                        result = pipeline.tools.call("add_patient_note", tool_args)
                        print(result.content)
                    else:
                        print("Action refusée par le médecin.")
                elif command == "/sessions":
                    print("\n".join(pipeline.sessions.list_sessions()) or "Aucune session enregistrée.")
                elif command == "/history":
                    print(json.dumps(pipeline.sessions.load(session_id).history, ensure_ascii=False, indent=2))
                elif command == "/session" and value:
                    saved = pipeline.sessions.load_context(value)
                    if saved:
                        _restore_context(context, saved)
                    else:
                        _refresh_context(context)
                    session_id = value
                    _save_context(pipeline, context, session_id)
                    print(f"Session {session_id} : {len(pipeline.sessions.load(session_id).history)} messages")
                elif command == "/tools":
                    for schema in pipeline.tools.schemas():
                        function = schema["function"]
                        print(f"{function['name']} : {function.get('description', '')}")
                else:
                    print(f"Commande inconnue : {text} ({HELP})")
            except (KeyboardInterrupt, EOFError):
                print("\nCommande interrompue ; aucune nouvelle confirmation donnée.")
            except Exception as error:
                print(f"Commande refusée : {error}", file=sys.stderr)
            continue

        try:
            previous_hits = context.last_hits
            tool_names = _requested_tools(text) if context.patient_id else None
            guard = pipeline.input_guard.check(text)
            if guard.blocked:
                print(guard.reason, file=sys.stderr)
                continue
            if context.patient_id:
                print(f"{DIM}Génération locale en cours (Ctrl+C pour interrompre)…{RESET}")
            if _show(pipeline.run(text, session_id, _confirm, tool_names=tool_names)):
                _save_context(pipeline, context, session_id)
            else:
                context.last_hits = previous_hits
            if context.rag_error:
                print(f"RAG : {context.rag_error}", file=sys.stderr)
        except KeyboardInterrupt:   # le tour n'est pas enregistré : la session reste intacte
            context.last_hits = previous_hits
            print(f"{DIM}Génération interrompue.{RESET}")


def _save_context(pipeline: Pipeline, context: PatientContext, session_id: str) -> None:
    pipeline.sessions.save_context(session_id, {
        "patient_id": context.patient_id,
        "profile_id": context.profile.profile_id if context.profile else "default",
        "filters": asdict(context.filters),
        "sources": [asdict(hit) for hit in context.last_hits],
    })


def _refresh_context(context: PatientContext) -> None:
    if context.profiles and context.profile:
        context.profile = context.profiles.load(context.profile.profile_id)
    context.last_hits, context.rag_error = [], ""


def _restore_context(context: PatientContext, saved: dict) -> None:
    # Tout valider avant de remplacer le contexte de la conversation courante.
    profile = context.profiles.load(saved["profile_id"])
    patient_id = saved.get("patient_id")
    if patient_id:
        context.patients.get_patient(patient_id)
    filters = Filters(**saved.get("filters", {}))
    filters.validate()
    hits = [Hit(**record) for record in saved.get("sources", [])]
    context.profile, context.patient_id = profile, patient_id
    context.filters, context.last_hits, context.rag_error = filters, hits, ""


def _requested_tools(text: str) -> set[str]:
    """Choisit par mots-clés les outils proposés au modèle pour ce tour."""
    query = text.casefold()
    names = set()
    if "note" in query and any(word in query for word in ("ajout", "écri", "ecri", "enregistr", "consign")):
        names.add("add_patient_note")
    if "calcul" in query or re.search(r"\d\s*[+*/-]\s*\d", query):
        names.add("calculator")
    if "heure" in query or "date actuelle" in query or "aujourd'hui" in query:
        names.add("get_current_time")
    if "get_patient" in query:
        names.add("get_patient")
    return names


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


def _confirm(call_id: str, tool: str, args: dict) -> bool:
    """Demande au médecin de valider l'action (arguments en clair) ; refus par défaut."""
    print(f"Action proposée : {tool}({json.dumps(args, ensure_ascii=False)})")
    try:
        return input("Confirmer ? [o/N] ").strip().casefold() in {"o", "oui"}
    except (KeyboardInterrupt, EOFError):
        return False


def _show(events: Iterator[Event]) -> bool:
    """Affiche au fil de l'eau les Event du pipeline (en clair)."""
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
                print(f"{DIM}← {event.data['content']}{RESET}")
            elif event.type == "error":
                print(event.data, file=sys.stderr)
            elif event.type == "done":
                completed = True
    finally:
        events.close()              # sur Ctrl+C : ferme le flux, Ollama arrête de générer
        if mid_line:
            print()
    return completed
