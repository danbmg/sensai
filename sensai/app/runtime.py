"""Assemblage de Sensai, partagé par la CLI et le web.

C'est le seul endroit qui construit les modules des trois membres et les relie au
pipeline : stockage et RAG (Timothée), guards, coffre PII et outils (Matteo), modèle,
pipeline et logs (Dan). Le Runtime porte ce qui est commun à toutes les sessions ;
chaque Consultation porte l'état d'une session.
"""
import argparse
import os
import re
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterator

from sensai.app.consultation import Consultation
from sensai.core.config import Config, load_config, validate_config
from sensai.core.interfaces import Message, PIIVault
from sensai.core.ollama_client import OLLAMA_ERRORS, OllamaClient, describe_error
from sensai.core.pipeline import Pipeline, TurnRecord
from sensai.guardrails.input_guardrail import SensaiInputGuard
from sensai.guardrails.output_guardrail import SensaiOutputGuard
from sensai.guardrails.pii_vault import SensaiPIIVault
from sensai.memory.context import PatientContext
from sensai.memory.fixtures import seed_demo_patients
from sensai.memory.patients import PatientStore
from sensai.memory.profiles import DoctorProfileStore
from sensai.memory.sessions import SQLiteSessionStore
from sensai.obs.logger import TurnLogger, short_hash
from sensai.obs.settings import LogSettings, load_log_settings
from sensai.rag.embeddings import OllamaEmbeddings
from sensai.rag.retrieval import Retriever
from sensai.rag.settings import RAGSettings, load_settings, resolve_index_path
from sensai.rag.store import VectorStore
from sensai.tools.runtime import medical_tools

DEMO_PATIENT = "demo-dupont"
# Réglages modifiables pendant l'exécution (web : PUT /api/config).
EDITABLE = ("model", "temperature", "num_ctx", "num_predict", "max_history_turns", "max_tool_iterations")


class StartupError(RuntimeError):
    """Base locale ou index documentaire inutilisable au démarrage."""


class ModelUnusable(RuntimeError):
    """Modèle injoignable, absent, ou incapable d'appeler des outils."""


@dataclass
class RuntimeOptions:
    """Choix faits au lancement : arguments de la CLI, ou variables d'environnement du web."""
    config: str | None = None
    model: str | None = None
    db: Path = Path(".sensai/memory.sqlite3")
    demo: bool = False
    mcp: bool = False
    rag_index: Path | None = None
    no_rag: bool = False
    keep_alive: int | str = 0

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "RuntimeOptions":
        """Pour `uvicorn sensai.web.api:app` : SENSAI_CONFIG, SENSAI_MODEL, SENSAI_DB, SENSAI_DEMO…"""
        env = os.environ if env is None else env

        def flag(name: str) -> bool:
            return env.get(name, "").strip().lower() in {"1", "true", "oui", "yes"}
        return cls(config=env.get("SENSAI_CONFIG") or None, model=env.get("SENSAI_MODEL") or None,
                   db=Path(env.get("SENSAI_DB") or cls.db), demo=flag("SENSAI_DEMO"),
                   mcp=flag("SENSAI_MCP"), rag_index=Path(env["SENSAI_RAG_INDEX"]) if env.get("SENSAI_RAG_INDEX") else None,
                   no_rag=flag("SENSAI_NO_RAG"), keep_alive=env.get("SENSAI_KEEP_ALIVE") or 0)

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> "RuntimeOptions":
        """Relit les options ajoutées par add_runtime_arguments()."""
        return cls(config=args.config, model=args.model, db=args.db, demo=args.demo, mcp=args.mcp,
                   rag_index=args.rag_index, no_rag=args.no_rag, keep_alive=args.keep_alive)


def parse_keep_alive(value: str) -> int | str:
    """--keep-alive : 0, ou une durée Ollama (30s, 2m, 1h)."""
    if value == "0":
        return 0
    if not re.fullmatch(r"[1-9]\d*(?:s|m|h)", value):
        raise argparse.ArgumentTypeError("Durée attendue : 0, 30s, 2m ou 1h.")
    return value


def add_runtime_arguments(parser: argparse.ArgumentParser) -> None:
    """Options communes à la CLI et au web ; RuntimeOptions.from_args() les relit."""
    parser.add_argument("--model", help="modèle Ollama (défaut : celui de config.toml)")
    parser.add_argument("--config", help="fichier de configuration (défaut : config.toml du projet)")
    parser.add_argument("--db", type=Path, default=RuntimeOptions.db, help="base SQLite locale")
    parser.add_argument("--demo", action="store_true", help="charger les patients fictifs")
    parser.add_argument("--mcp", action="store_true", help="utiliser le serveur MCP médical pour les outils patients")
    parser.add_argument("--rag-index", type=Path, help="index documentaire séparé de la base patients")
    parser.add_argument("--no-rag", action="store_true", help="désactiver la recherche documentaire pour cette exécution")
    parser.add_argument("--keep-alive", type=parse_keep_alive, default=0,
                        help="garder le modèle en RAM entre les appels (ex. 2m ; défaut 0 pour libérer la RAM)")


@dataclass
class Settings:
    model: Config               # [model] et [assistant]
    rag: RAGSettings            # [rag]
    logs: LogSettings           # [logging]

    @classmethod
    def load(cls, options: RuntimeOptions) -> "Settings":
        """Lève ConfigError si config.toml est absent ou invalide."""
        return cls(load_config(options.config, model=options.model), load_settings(options.config),
                   load_log_settings(options.config))


@dataclass
class Stores:
    """Les trois tables SQLite de Timothée, dans la même base locale."""
    patients: PatientStore
    sessions: SQLiteSessionStore
    profiles: DoctorProfileStore

    @classmethod
    def open(cls, db: Path, demo: bool = False) -> "Stores":
        try:
            stores = cls(PatientStore(db), SQLiteSessionStore(db), DoctorProfileStore(db))
            stores.profiles.ensure_default()
            if demo:
                seed_demo_patients(stores.patients)
        except (OSError, ValueError, sqlite3.Error) as error:
            raise StartupError(str(error)) from error
        return stores


def make_client(cfg: Config, keep_alive: int | str = 0) -> OllamaClient:
    return OllamaClient(cfg.model, cfg.host, options={
        "temperature": cfg.temperature, "num_ctx": cfg.num_ctx, "num_predict": cfg.num_predict,
        "num_thread": cfg.num_thread, "num_batch": cfg.num_batch,
    }, timeout=cfg.timeout, keep_alive=keep_alive)


def check_model(client: OllamaClient) -> str:
    """/api/show : lève ModelUnusable si le modèle ne convient pas ; renvoie un avertissement ou ""."""
    try:
        capabilities = client.capabilities()
    except OLLAMA_ERRORS as e:
        raise ModelUnusable(describe_error(e, client)) from e
    if "tools" not in capabilities:
        raise ModelUnusable(f"{client.model} ne sait pas appeler d'outils (capacité « tools » absente) : "
                            "choisissez un autre modèle.")
    if "thinking" in capabilities:
        return (f"⚠ {client.model} est un modèle « thinking » : il raisonne avant de répondre, "
                "trop lent sur CPU pour la démo.")
    return ""


def build_retriever(settings: Settings, options: RuntimeOptions) -> tuple[Retriever | None, int]:
    """Le RAG, s'il est activé et que l'index contient des documents ; et ce nombre de documents."""
    rag = settings.rag
    if not rag.enabled or options.no_rag:
        return None, 0
    index_path = options.rag_index or resolve_index_path(rag, options.db)
    if index_path.resolve() == options.db.resolve():
        raise StartupError("L'index RAG doit être séparé de la base patients.")
    try:
        index = VectorStore(index_path)
        documents = len(index.list_documents())
    except (OSError, ValueError, sqlite3.Error) as error:
        raise StartupError(f"Index documentaire illisible : {error}") from error
    if not documents:
        return None, 0
    embedder = OllamaEmbeddings(rag.model, settings.model.host, rag.timeout, rag.batch_size)
    return Retriever(index, embedder, top_k=rag.top_k, candidates=rag.candidates,
                     min_similarity=rag.min_similarity, min_relevance=rag.min_relevance,
                     rerank=rag.rerank), documents


class _SessionContexts:
    """ContextProvider du pipeline : passe la main au contexte de la session demandée."""

    def __init__(self, runtime: "Runtime"):
        self.runtime = runtime

    def provide(self, query: str, masked_query: str, session_id: str) -> list[Message]:
        return self.runtime.consultation(session_id).context.provide(query, masked_query, session_id)


class Runtime:
    def __init__(self, options: RuntimeOptions, settings: Settings, stores: Stores, tools, *,
                 retriever: Retriever | None = None, rag_documents: int = 0):
        self.options, self.settings, self.stores, self.tools = options, settings, stores, tools
        self.retriever, self.rag_documents = retriever, rag_documents
        self.client = make_client(settings.model, options.keep_alive)
        self.logger = TurnLogger(settings.logs.directory, self.describe) if settings.logs.enabled else None
        self.last_records: dict[str, TurnRecord] = {}
        self._consultations: dict[str, Consultation] = {}
        self._lock = threading.RLock()
        cfg = settings.model
        self.pipeline = Pipeline(
            self.client, cfg.system_prompt, cfg.max_tool_iterations,
            max_history_turns=cfg.max_history_turns,
            input_guard=SensaiInputGuard(), output_guard=SensaiOutputGuard(),
            vault_factory=self.vault, context=_SessionContexts(self),
            sessions=stores.sessions, tools=tools, on_turn=self._on_turn,
        )

    # --- Modules partagés ---

    def vault(self, pii_map: dict[str, str]) -> PIIVault:
        """Le coffre d'une session : pseudonymes déjà attribués + patients connus de la base."""
        return SensaiPIIVault(pii_map, patients=self.stores.patients.list_patients())

    def make_context(self, profile_id: str) -> PatientContext:
        rag = self.settings.rag
        return PatientContext(self.stores.patients, profile=self.stores.profiles.load(profile_id),
                              retriever=self.retriever, max_context_chars=rag.max_context_chars,
                              profiles=self.stores.profiles, search_mode=rag.search_mode)

    def _on_turn(self, record: TurnRecord) -> None:
        self.last_records[record.session_id] = record      # /prompt : dernier prompt envoyé
        if self.logger:
            self.logger(record)

    def describe(self) -> dict:
        """Configuration en vigueur, jointe à chaque log : un changement crée une nouvelle version."""
        cfg = self.settings.model
        return {"model": self.client.model, "temperature": cfg.temperature, "num_ctx": cfg.num_ctx,
                "num_predict": cfg.num_predict, "max_history_turns": cfg.max_history_turns,
                "max_tool_iterations": cfg.max_tool_iterations,
                "prompt_version": short_hash(cfg.system_prompt), "rag": self.retriever is not None}

    def check_model(self) -> str:
        return check_model(self.client)

    def configure(self, **changes) -> str:
        """Change modèle ou paramètres à chaud ; lève ConfigError / ModelUnusable sans rien changer."""
        unknown = set(changes) - set(EDITABLE)
        if unknown:
            raise ValueError(f"Réglage non modifiable : {', '.join(sorted(unknown))}")
        cfg = replace(self.settings.model, **changes)
        validate_config(cfg)
        client = make_client(cfg, self.options.keep_alive)
        warning = check_model(client) if cfg.model != self.client.model else ""
        with self._lock:
            self.settings = replace(self.settings, model=cfg)
            self.client = self.pipeline.client = client
            self.pipeline.max_tool_iterations = cfg.max_tool_iterations
            self.pipeline.max_history_turns = cfg.max_history_turns
        return warning

    # --- Consultations ---

    def open_consultation(self, session_id: str | None = None, *, patient: str | None = None,
                          profile: str | None = None, default_patient: str | None = None) -> Consultation:
        """Reprend `session_id` s'il existe, sinon ouvre une nouvelle consultation.

        Une session reste liée à son patient et à son profil : en demander d'autres lève
        ValueError, pour ne jamais mélanger deux dossiers dans un même historique.
        """
        session_id = session_id or uuid.uuid4().hex
        with self._lock:
            saved = self.stores.sessions.load_context(session_id)
            if saved or session_id in self._consultations:
                consultation = self._consultations.get(session_id) or Consultation.restore(self, session_id, saved)
                if profile and profile != consultation.profile_id:
                    raise ValueError("Cette session utilise un autre profil. "
                                     "Choisissez un nouvel identifiant de session.")
                if patient and self.stores.patients.resolve_patient(patient)["patient_id"] != consultation.patient_id:
                    raise ValueError("Cette session appartient à un autre patient. Choisissez une nouvelle session.")
            else:
                consultation = Consultation.new(self, session_id, profile=profile or "default",
                                                patient=patient or default_patient)
            consultation.save()
            self._consultations[session_id] = consultation
            return consultation

    def consultation(self, session_id: str) -> Consultation:
        """Consultation ouverte, ou reprise depuis la base ; KeyError si la session est inconnue."""
        with self._lock:
            if session_id in self._consultations:
                return self._consultations[session_id]
            if not self.stores.sessions.load_context(session_id):
                raise KeyError(session_id)
            return self.open_consultation(session_id)

    def fork(self, consultation: Consultation, *, session_id: str | None = None,
             patient: str | None = None, profile: str | None = None) -> Consultation:
        """Nouvelle session qui garde le patient, le profil (relu en base) et les filtres."""
        new = Consultation.new(self, session_id or uuid.uuid4().hex,
                               profile=profile or consultation.profile_id,
                               patient=patient or consultation.patient_id,
                               filters=consultation.context.filters)
        new.save()
        with self._lock:
            self._consultations[new.session_id] = new
        return new

    def list_consultations(self) -> list[dict]:
        """Sessions enregistrées et ouvertes, la plus récente d'abord (noms de patients EN CLAIR)."""
        with self._lock:
            ids = set(self.stores.sessions.list_sessions()) | set(self._consultations)
        items = []
        for session_id in ids:
            saved = self.stores.sessions.load_context(session_id)
            name = None
            if saved.get("patient_id"):
                try:
                    name = self.stores.patients.get_patient(saved["patient_id"])["name"]
                except LookupError:
                    name = None
            items.append({"session_id": session_id, "patient_id": saved.get("patient_id"),
                          "patient_name": name, "profile_id": saved.get("profile_id", "default"),
                          "messages": len(self.stores.sessions.load(session_id).history),
                          "updated_at": saved.get("updated_at", "")})
        return sorted(items, key=lambda item: (item["updated_at"], item["session_id"]), reverse=True)


@contextmanager
def open_runtime(options: RuntimeOptions, *, settings: Settings | None = None,
                 stores: Stores | None = None) -> Iterator[Runtime]:
    """Construit le Runtime ; à la sortie, ferme les outils (processus MCP compris).

    Erreurs : ConfigError (config.toml), StartupError (base, index), RuntimeError (MCP).
    Le modèle n'est pas contrôlé ici : la CLI s'arrête s'il manque, le web l'affiche.
    """
    settings = settings or Settings.load(options)
    stores = stores or Stores.open(options.db, options.demo)
    retriever, documents = build_retriever(settings, options)
    with medical_tools(stores.patients, options.mcp) as tools:
        yield Runtime(options, settings, stores, tools, retriever=retriever, rag_documents=documents)
