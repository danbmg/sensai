"""Backend web (X1) : une API HTTP au-dessus du même Runtime que la CLI.

Le web ne contient aucune logique métier : chaque route appelle le Runtime ou une
Consultation (sensai.app), exactement comme la CLI. Lancement :
    python -m sensai.web --demo          (ou : uvicorn sensai.web.api:app, réglages par SENSAI_*)
"""
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from sensai.app.consultation import Consultation
from sensai.app.runtime import EDITABLE, ModelUnusable, Runtime, RuntimeOptions, open_runtime
from sensai.core.config import ConfigError
from sensai.core.ollama_client import OLLAMA_ERRORS, describe_error
from sensai.obs.metrics import load_entries, summarize
from sensai.rag.store import Filters
from sensai.web.confirmations import Confirmations
from sensai.web.streaming import BUSY, EventStream

STATIC = Path(__file__).parent / "static"
CONFIRM_TIMEOUT = 120.0     # sans clic du médecin, l'action est refusée
# Après « Arrêter », le tour abandonné libère la session au fragment suivant d'Ollama :
# un nouveau message envoyé aussitôt attend ce délai avant d'être refusé (409).
BUSY_WAIT = 5.0

api = APIRouter(prefix="/api")


class ChatRequest(BaseModel):
    session_id: str
    message: str


class ConfirmRequest(BaseModel):
    approved: bool


class SessionRequest(BaseModel):
    patient: str | None = None
    profile: str | None = None


class FiltersRequest(BaseModel):
    publisher: str | None = None
    tags: list[str] = Field(default_factory=list)
    since: str = ""
    until: str = ""


class SearchRequest(BaseModel):
    query: str


def _runtime(request: Request) -> Runtime:
    return request.app.state.runtime


def _consultation(request: Request, session_id: str) -> Consultation:
    try:
        return _runtime(request).consultation(session_id)
    except KeyError:
        raise HTTPException(404, "Session inconnue.") from None


def _refused(error: Exception) -> HTTPException:
    """Erreur attendue (patient introuvable, filtre invalide…) : message lisible, code 400."""
    return HTTPException(400, str(error) or type(error).__name__)


# --- État, modèle et configuration ---

@api.get("/status")
def status(request: Request) -> dict:
    runtime = _runtime(request)
    try:
        model = {"ok": True, "warning": runtime.check_model()}
    except ModelUnusable as error:
        model = {"ok": False, "error": str(error)}
    logger = runtime.logger
    return {
        "model": {"name": runtime.client.model, **model},
        "rag": {"enabled": runtime.settings.rag.enabled and not runtime.options.no_rag,
                "active": runtime.retriever is not None, "documents": runtime.rag_documents,
                "search_mode": runtime.settings.rag.search_mode},
        "tools": [{"name": schema["function"]["name"], "description": schema["function"].get("description", ""),
                   "dangerous": runtime.tools.is_dangerous(schema["function"]["name"])}
                  for schema in runtime.tools.schemas()],
        "mcp": runtime.options.mcp,
        "confirm_timeout": request.app.state.confirmations.timeout,
        "logs": {"enabled": logger is not None, "directory": str(logger.directory) if logger else None,
                 "error": logger.last_error if logger else ""},
    }


@api.get("/models")
def models(request: Request) -> dict:
    """Relaie /api/tags d'Ollama : modèles installés, et celui en service."""
    runtime = _runtime(request)
    try:
        names = runtime.client.list_models()
    except OLLAMA_ERRORS as error:
        raise HTTPException(503, describe_error(error, runtime.client)) from None
    return {"current": runtime.client.model, "models": names}


@api.get("/config")
def get_config(request: Request) -> dict:
    runtime = _runtime(request)
    cfg = asdict(runtime.settings.model)
    return {**cfg, "editable": list(EDITABLE)}


@api.put("/config")
def put_config(request: Request, changes: dict[str, Any]) -> dict:
    """Change le modèle (agent) ou un paramètre à chaud ; un modèle sans outils est refusé."""
    try:
        warning = _runtime(request).configure(**changes)
    except (ConfigError, ModelUnusable, ValueError, TypeError) as error:
        raise _refused(error) from None
    return {**get_config(request), "warning": warning}


# --- Patients et profils (lecture seule : les écritures passent par les outils confirmés) ---

@api.get("/patients")
def patients(request: Request) -> list[dict]:
    return [{key: patient[key] for key in ("patient_id", "name", "birth_date")}
            for patient in _runtime(request).stores.patients.list_patients()]


@api.get("/patients/{patient_id}")
def patient(request: Request, patient_id: str) -> dict:
    try:
        return _runtime(request).stores.patients.get_patient(patient_id)
    except LookupError:
        raise HTTPException(404, "Patient inconnu.") from None


@api.get("/profiles")
def profiles(request: Request) -> list[dict]:
    store = _runtime(request).stores.profiles
    return [asdict(store.load(profile_id)) for profile_id in store.list_profiles()]


# --- Sessions ---

@api.get("/sessions")
def sessions(request: Request) -> list[dict]:
    return _runtime(request).list_consultations()


@api.post("/sessions", status_code=201)
def create_session(request: Request, body: SessionRequest) -> dict:
    try:
        consultation = _runtime(request).open_consultation(patient=body.patient or None,
                                                           profile=body.profile or None)
    except (ValueError, LookupError) as error:
        raise _refused(error) from None
    return consultation.describe()


@api.get("/sessions/{session_id}")
def session(request: Request, session_id: str) -> dict:
    """La session pour l'affichage : historique ré-identifié (côté clair), sources, filtres."""
    consultation = _consultation(request, session_id)
    return {**consultation.describe(), "history": consultation.history(revealed=True),
            "sources": consultation.sources()}


@api.put("/sessions/{session_id}/filters")
def set_filters(request: Request, session_id: str, body: FiltersRequest) -> dict:
    consultation = _consultation(request, session_id)
    try:
        consultation.set_filters(Filters(body.publisher or None, tuple(body.tags), body.since, body.until))
    except (ValueError, TypeError) as error:
        raise _refused(error) from None
    return consultation.describe()


@api.get("/sessions/{session_id}/prompt")
def prompt(request: Request, session_id: str) -> dict:
    """Le prompt exact du dernier tour, tel que reçu par le modèle (pseudonymisé)."""
    last = _consultation(request, session_id).last_prompt()
    if last is None:
        raise HTTPException(404, "Aucun prompt envoyé dans cette session depuis le lancement du serveur.")
    return last


@api.post("/sessions/{session_id}/search")
def search(request: Request, session_id: str, body: SearchRequest) -> dict:
    consultation = _consultation(request, session_id)
    try:
        text = consultation.search(body.query)
    except Exception as error:      # index absent, embeddings indisponibles…
        raise _refused(error) from None
    return {"text": text, "sources": consultation.sources()}


# --- Conversation ---

@api.post("/chat")
def chat(request: Request, body: ChatRequest) -> StreamingResponse:
    """Un tour en streaming SSE : token, tool_call, confirm, tool_result, usage, sources, error, done."""
    if not body.message.strip():
        raise HTTPException(400, "Message vide.")
    consultation = _consultation(request, body.session_id)
    wait = request.app.state.busy_wait
    # Session occupée (autre onglet) : un 409 clair. Le flux reprend ensuite le verrou lui-même.
    if not consultation.busy.acquire(timeout=wait):
        raise HTTPException(409, BUSY)
    consultation.busy.release()
    confirmations: Confirmations = request.app.state.confirmations
    stream = EventStream(consultation.ask(body.message, confirmations.wait), confirmations,
                         consultation.busy, wait)
    return StreamingResponse(stream, media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@api.post("/confirm/{call_id}")
def confirm(request: Request, call_id: str, body: ConfirmRequest) -> dict:
    if not request.app.state.confirmations.resolve(call_id, body.approved):
        raise HTTPException(404, "Aucune action en attente avec cet identifiant (délai dépassé ?).")
    return {"id": call_id, "approved": body.approved}


# --- Métriques EV3 ---

@api.get("/metrics")
def metrics(request: Request, days: int | None = None) -> dict:
    logger = _runtime(request).logger
    if logger is None:
        return {"enabled": False}
    entries, skipped = load_entries(logger.directory, days)
    return {"enabled": True, "skipped": skipped, **summarize(entries)}


def create_app(options: RuntimeOptions | None = None, *,
               confirm_timeout: float = CONFIRM_TIMEOUT, busy_wait: float = BUSY_WAIT) -> FastAPI:
    """Application FastAPI ; le Runtime est ouvert au démarrage du serveur et fermé à l'arrêt."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        with open_runtime(options or RuntimeOptions.from_env()) as runtime:
            app.state.runtime = runtime
            app.state.confirmations = Confirmations(confirm_timeout)
            app.state.busy_wait = busy_wait
            yield

    app = FastAPI(title="Sensai", lifespan=lifespan)
    app.include_router(api)
    app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")
    return app


app = create_app()
