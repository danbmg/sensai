"""Mesure relançable : une feature contre sa baseline, et l'effet d'un réglage.

python -m sensai.obs.compare [--runs 2] [--only NOM] [--out FICHIER.json]

Chaque variante rejoue les mêmes questions par le vrai chemin de l'appli (Runtime, garde-fous,
contexte patient, RAG, pipeline), avec le modèle de config.toml. La base de démo est jetable :
la base du cabinet n'est pas touchée, aucune écriture d'outil n'est validée, rien n'entre dans
logs/. Les réponses conservées sont celles de l'historique, donc pseudonymisées.
"""
import argparse
import json
import re
import statistics
import sys
import tempfile
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path

from sensai.app.runtime import (DEMO_PATIENT, ModelUnusable, RuntimeOptions, Settings, Stores,
                                check_model, make_client, open_runtime)
from sensai.core.config import ConfigError
from sensai.core.pipeline import TurnRecord
from sensai.obs.settings import LogSettings
from sensai.rag.settings import resolve_index_path


@dataclass(frozen=True)
class Variant:
    name: str
    patient: bool = True        # dossier de Mme Dupont sélectionné (M3)
    rag: bool = True            # recherche dans les documents publics (R1)
    changes: dict = field(default_factory=dict)     # réglages modifiés (Runtime.configure)


VARIANTS = (
    Variant("sans contexte", patient=False, rag=False),     # baseline : le modèle seul
    Variant("dossier", rag=False),                          # + M3
    Variant("dossier + RAG"),                               # + M3 + R1
    Variant("dossier, num_predict 32", rag=False, changes={"num_predict": 32}),     # réglage vs « dossier »
)

# Chaque question a son critère : la contre-indication pour le scénario, un extrait cité pour la notice.
QUESTIONS = {
    "scénario": ("Mme Dupont peut-elle prendre de l'amoxicilline ?", "risque"),
    "notice": ("Que dit la notice de l'amoxicilline en cas d'allergie à la pénicilline ? Cite la source.", "extrait"),
}
CRITERION_LABELS = {"risque": "risque nommé", "extrait": "extrait cité"}
COUNTED = ("met", "abstains", "truncated")

ABSTAINS = re.compile(r"je (?:ne peux pas|n'ai pas accès|ne trouve pas|ne dispose pas)", re.I)


def score(answer: str) -> dict[str, bool]:
    """Critères vérifiés sur chaque réponse : définis ici pour que la mesure se relance telle quelle.

    Les mots de la question ne comptent pas : « notice » ou « dossier » dans « je n'ai pas accès
    aux notices » ne sont pas une source. Une source, c'est un extrait [S1] ou son éditeur.
    """
    abstains = bool(ABSTAINS.search(answer))
    return {
        # La question du scénario ne parle pas d'allergie : la nommer vient du contexte.
        "risque": bool(re.search(r"allergi|p[ée]nicilline", answer, re.I))
                  and not re.match(r"\W*oui\b", answer, re.I) and not abstains,
        "extrait": bool(re.search(r"\[S\d+\]|ANSM|BDPM|SANDOZ", answer, re.I) or re.search(r"\bHAS\b", answer)),
        "abstains": abstains,
    }


def answer_of(record: TurnRecord) -> str:
    """Dernière réponse du modèle, telle qu'enregistrée (pseudonymisée)."""
    return next((m["content"] for m in reversed(record.messages)
                 if m.get("role") == "assistant" and m.get("content")), "")


def _refuse(*_) -> bool:
    return False        # une mesure n'écrit jamais dans un dossier


def run_variant(variant: Variant, options: RuntimeOptions, settings: Settings, stores: Stores,
                runs: int, progress=print) -> list[dict]:
    with open_runtime(replace(options, no_rag=not variant.rag), settings=settings, stores=stores) as runtime:
        if variant.rag and runtime.retriever is None:
            raise SystemExit("Index documentaire vide : lancez python -m sensai.rag fetch puis index.")
        if variant.changes:
            runtime.configure(**variant.changes)
        num_predict = runtime.settings.model.num_predict
        rows = []
        for question_id, (question, criterion) in QUESTIONS.items():
            for run in range(1, runs + 1):
                # Une session neuve par essai : aucun historique ne passe d'un essai à l'autre.
                consultation = runtime.open_consultation(patient=DEMO_PATIENT if variant.patient else None)
                errors = [event.data for event in consultation.ask(question, _refuse) if event.type == "error"]
                record = runtime.last_records.get(consultation.session_id)
                answer = answer_of(record) if record else ""
                row = {"variant": variant.name, "question": question_id, "run": run, "answer": answer,
                       "latency_s": round(record.latency_s, 1) if record else None,
                       "prompt_tokens": record.prompt_tokens if record else None,
                       "completion_tokens": record.completion_tokens if record else None,
                       "truncated": bool(record) and record.completion_tokens >= num_predict,
                       "error": "; ".join(map(str, errors)) or (record.error if record else "aucun tour"),
                       **score(answer)}
                row["met"] = row[criterion]
                rows.append(row)
                progress(f"{variant.name} · {question_id} · essai {run} : {row['latency_s']} s"
                         + (f" — erreur : {row['error']}" if row["error"] else ""))
        return rows


def summarize(rows: list[dict]) -> list[dict]:
    """Une ligne par (variante, question) : taux de chaque critère, médianes de latence et de tokens."""
    groups: dict[tuple[str, str], list[dict]] = {}
    for row in rows:
        groups.setdefault((row["variant"], row["question"]), []).append(row)
    lines = []
    for (variant, question), items in groups.items():
        ok = [row for row in items if not row["error"]]
        median = (lambda key, digits: round(statistics.median(row[key] for row in ok), digits) if ok else None)
        lines.append({"variant": variant, "question": question, "runs": len(items), "errors": len(items) - len(ok),
                      "criterion": QUESTIONS[question][1], **{key: sum(row[key] for row in ok) for key in COUNTED},
                      "latency_s": median("latency_s", 1), "prompt_tokens": median("prompt_tokens", None)})
    return lines


def render(lines: list[dict]) -> str:
    out = ["| Variante | Question | Critère | Atteint | S'abstient | Tronquée "
           "| Latence médiane (s) | Tokens lus (médiane) | Erreurs |",
           "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for line in lines:
        valid = line["runs"] - line["errors"]
        rates = " | ".join(f"{line[key]}/{valid}" for key in COUNTED)
        out.append(f"| {line['variant']} | {line['question']} | {CRITERION_LABELS[line['criterion']]} | {rates} "
                   f"| {line['latency_s']} | {line['prompt_tokens']} | {line['errors']} |")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m sensai.obs.compare", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", help="fichier de configuration (défaut : config.toml du projet)")
    parser.add_argument("--rag-index", type=Path, help="index documentaire (défaut : .sensai/rag.sqlite3)")
    parser.add_argument("--runs", type=int, default=2, help="essais par question et par variante")
    parser.add_argument("--only", action="append", choices=[v.name for v in VARIANTS], metavar="VARIANTE",
                        help="ne lancer que cette variante (répétable) : " + ", ".join(f"« {v.name} »" for v in VARIANTS))
    parser.add_argument("--out", type=Path, help="enregistrer réponses et mesures dans ce fichier JSON")
    args = parser.parse_args(argv)
    variants = [v for v in VARIANTS if not args.only or v.name in args.only]
    if args.runs < 1:
        parser.exit(1, "--runs doit valoir au moins 1.\n")
    try:
        settings = Settings.load(RuntimeOptions(config=args.config))
    except ConfigError as error:
        parser.exit(1, f"{error}\n")
    settings = replace(settings, logs=LogSettings(enabled=False))
    try:
        warning = check_model(make_client(settings.model))
    except ModelUnusable as error:
        parser.exit(1, f"{error}\n")
    if warning:
        print(warning, file=sys.stderr)

    rows = []
    with tempfile.TemporaryDirectory() as directory:
        options = RuntimeOptions(config=args.config, db=Path(directory) / "memory.sqlite3", demo=True,
                                 rag_index=args.rag_index or resolve_index_path(settings.rag, RuntimeOptions.db))
        stores = Stores.open(options.db, demo=True)
        for variant in variants:
            rows += run_variant(variant, options, settings, stores, args.runs,
                                progress=lambda text: print(text, file=sys.stderr, flush=True))
    lines = summarize(rows)
    print(render(lines))
    if args.out:
        cfg = settings.model
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps({
            "date": datetime.now().isoformat(timespec="seconds"), "model": cfg.model,
            "settings": {"temperature": cfg.temperature, "num_ctx": cfg.num_ctx, "num_predict": cfg.num_predict},
            "runs": args.runs, "questions": {key: text for key, (text, _) in QUESTIONS.items()}, "summary": lines, "results": rows,
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
