"""Contrat partagé Sensai — v2, validé à 3 le 2026-10-05 (Dan, Timothée, Matteo).

Par rapport à la v1 : un PIIVault par session remplace GuardResult.mapping, et le
contrat précise ce qui est en clair et ce qui est pseudonymisé.

Frontière PII : le pipeline (Dan) est le SEUL endroit qui pseudonymise et ré-identifie.
- Côté clair (local)   : ContextProvider (recherche patient), ToolRegistry.call(),
                         affichage CLI/web, tous les Event.
- Côté pseudonymisé    : messages envoyés au modèle de chat, requête d'embedding RAG,
                         historique stocké (SessionState.history), logs.

Pseudonymes : [TYPE_N], TYPE = un seul mot parmi PSEUDONYM_TYPES (ex. [PATIENT_1]).
"""
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Protocol

Message = dict[str, Any]  # format Ollama : {"role", "content", "tool_calls"?, "tool_name"?}

PSEUDONYM_TYPES = ("PATIENT", "NAISSANCE", "ADRESSE", "TEL", "NIR", "EMAIL")
PSEUDONYM_RE = re.compile(r"\[(?:%s)_\d+\]" % "|".join(PSEUDONYM_TYPES))


@dataclass
class GuardResult:
    blocked: bool = False                       # requête refusée (hors périmètre) ?
    reason: str = ""                            # motif affiché si bloquée


class InputGuard(Protocol):                     # Matteo (EV2) — filtre de périmètre, sans état
    def check(self, text: str) -> GuardResult: ...


class PIIVault(Protocol):                       # Matteo (EV2) — UNE instance par session
    def mask(self, text: str) -> str: ...       # clair -> [TYPE_N] ; idempotent ; réutilise les pseudonymes
    def reveal(self, text: str) -> str: ...     # [TYPE_N] -> clair (pseudonymes inconnus laissés tels quels)
    def reveal_args(self, args: dict) -> dict: ...  # idem, récursif sur les arguments d'outils
    def export(self) -> dict[str, str]: ...     # pseudonyme -> valeur réelle, pour la persistance


VaultFactory = Callable[[dict[str, str]], PIIVault]  # recrée le coffre à partir de export()


class OutputGuard(Protocol):                    # Matteo (EV2)
    # Appelé sur la RÉPONSE COMPLÈTE déjà passée par vault.mask(), avant l'écriture
    # dans l'historique et les logs. Masque toute PII brute restante (regex).
    def check(self, text: str) -> str: ...


class ContextProvider(Protocol):                # Timothée (profil M1, patients M3, RAG R1)
    def provide(self, query: str, masked_query: str, session_id: str) -> list[Message]: ...
    # query        : EN CLAIR, uniquement pour la recherche patient dans SQLite ;
    # masked_query : seule entrée autorisée pour l'embedding RAG ;
    # retour       : EN CLAIR (le pipeline applique vault.mask sur chaque "content").
    # Le corpus RAG ne contient que des documents publics : jamais de dossier patient indexé.


@dataclass
class SessionState:
    history: list[Message] = field(default_factory=list)   # pseudonymisé (ce que le modèle a vu)
    pii_map: dict[str, str] = field(default_factory=dict)  # PIIVault.export(), stocké en local


class SessionStore(Protocol):                   # Timothée (M1)
    def load(self, session_id: str) -> SessionState: ...   # session inconnue -> SessionState() vide
    def save(self, session_id: str, state: SessionState) -> None: ...
    # Pas « list » : en 3.14 l'annotation list[str] désignerait la méthode elle-même.
    def list_sessions(self) -> list[str]: ...


@dataclass
class ToolResult:
    content: str
    is_error: bool = False


class ToolRegistry(Protocol):                   # Matteo (T1) — arguments et résultats EN CLAIR
    def schemas(self) -> list[dict]: ...        # format "tools" d'Ollama
    def is_dangerous(self, name: str) -> bool: ...  # True => validation humaine (A3)
    def call(self, name: str, args: dict) -> ToolResult: ...


@dataclass
class Event:                                    # émis par le pipeline, lu par CLI et web
    type: Literal["token", "tool_call", "tool_result", "confirm",
                  "usage", "sources", "error", "done"]  # sources : ajouté par sensai.app
    data: Any = None                            # EN CLAIR : ne jamais logger à partir des Event


ConfirmFn = Callable[[str, str, dict], bool]    # (id, outil, args EN CLAIR) -> accepté ?
