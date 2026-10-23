"""Métriques EV3 calculées sur les logs JSONL : volume, latence, taux d'erreur, dérive.

La dérive se lit dans `by_config` et `by_day` : un prompt système modifié ou un paramètre
changé crée une nouvelle configuration, dont la latence se compare aux précédentes.
"""
import json
import math
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path
from statistics import mean

from sensai.obs.logger import short_hash

RECENT = 20


def load_entries(directory: str | Path, days: int | None = None,
                 today: date | None = None) -> tuple[list[dict], int]:
    """Entrées des `days` derniers jours (None : toutes) et nombre de lignes illisibles ignorées."""
    directory = Path(directory)
    first = (today or date.today()) - timedelta(days=days - 1) if days else None
    entries, skipped = [], 0
    for path in sorted(directory.glob("*.jsonl")) if directory.is_dir() else []:
        try:
            day = date.fromisoformat(path.stem)
        except ValueError:
            continue
        if first and day < first:
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                skipped += 1        # ligne coupée (arrêt brutal pendant l'écriture)
                continue
            if isinstance(entry, dict) and "status" in entry:
                entries.append(entry)
            else:
                skipped += 1
    entries.sort(key=lambda entry: entry.get("timestamp", ""))
    return entries, skipped


def percentile(values: list[float], q: float) -> float:
    """Percentile par rang le plus proche (pas d'interpolation : simple à expliquer)."""
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = math.ceil(q / 100 * len(ordered))       # p95 de 20 valeurs : la 19e
    return ordered[min(len(ordered), max(rank, 1)) - 1]


def config_key(entry: dict) -> str:
    return short_hash(json.dumps(entry.get("config", {}), sort_keys=True))


def _group(entries: list[dict]) -> dict:
    """Résumé d'un groupe de tours ; la latence ne compte que les tours aboutis."""
    latencies = [e["latency_s"] for e in entries if e["status"] == "ok"]
    answered = [e for e in entries if e["status"] != "blocked"]
    return {
        "turns": len(entries),
        "errors": sum(e["status"] == "error" for e in entries),
        "blocked": sum(e["status"] == "blocked" for e in entries),
        # Un refus de l'InputGuard n'est pas une panne : il est compté à part.
        "error_rate": round(sum(e["status"] == "error" for e in answered) / len(answered), 3) if answered else 0.0,
        "latency_mean": round(mean(latencies), 2) if latencies else 0.0,
        "latency_p50": round(percentile(latencies, 50), 2),
        "latency_p95": round(percentile(latencies, 95), 2),
        "prompt_tokens_mean": round(mean(e["prompt_tokens"] for e in answered), 1) if answered else 0.0,
        "completion_tokens_mean": round(mean(e["completion_tokens"] for e in answered), 1) if answered else 0.0,
        "context_tokens_max": max((e.get("context_tokens", 0) for e in entries), default=0),
    }


def summarize(entries: list[dict]) -> dict:
    by_model, by_config, by_day = defaultdict(list), defaultdict(list), defaultdict(list)
    configs = {}
    tools = Counter()
    for entry in entries:
        by_model[entry.get("model", "?")].append(entry)
        key = config_key(entry)
        by_config[key].append(entry)
        configs.setdefault(key, entry.get("config", {}))
        by_day[entry.get("timestamp", "")[:10]].append(entry)
        tools.update(call.get("name", "") for call in entry.get("tool_calls", []))
    return {
        **_group(entries),
        "tool_calls": dict(tools.most_common()),
        "by_model": [{"model": model, **_group(group)} for model, group in sorted(by_model.items())],
        # Ordre d'apparition : la dernière configuration est celle en vigueur.
        "by_config": [{"config_id": key, "config": configs[key], "since": group[0].get("timestamp", ""),
                       **_group(group)} for key, group in by_config.items()],
        "by_day": [{"day": day, **_group(group)} for day, group in sorted(by_day.items())],
        "recent": [{"timestamp": e.get("timestamp", ""), "model": e.get("model", ""),
                    "status": e["status"], "error": e.get("error", ""),
                    "latency_s": e["latency_s"], "prompt_tokens": e["prompt_tokens"],
                    "completion_tokens": e["completion_tokens"],
                    "tools": [call.get("name", "") for call in e.get("tool_calls", [])]}
                   for e in entries[-RECENT:]][::-1],
    }


def _seconds(value: float) -> str:
    return f"{value:.1f} s".replace(".", ",")


def render(summary: dict, skipped: int = 0) -> str:
    """Texte lisible du résumé de summarize()."""
    if not summary["turns"]:
        return "Aucun tour enregistré dans les logs."
    lines = [
        f"Tours : {summary['turns']} (erreurs {summary['errors']} · bloqués {summary['blocked']}) — "
        f"taux d'erreur {summary['error_rate']:.1%}".replace(".", ","),
        f"Latence : moyenne {_seconds(summary['latency_mean'])} · p50 {_seconds(summary['latency_p50'])}"
        f" · p95 {_seconds(summary['latency_p95'])}",
        f"Tokens moyens : prompt {summary['prompt_tokens_mean']:g} · réponse "
        f"{summary['completion_tokens_mean']:g} · contexte max {summary['context_tokens_max']}".replace(".", ","),
    ]
    if summary["tool_calls"]:
        lines.append("Outils : " + ", ".join(f"{name} ×{count}" for name, count in summary["tool_calls"].items()))
    lines.append("\nPar modèle :")
    lines += [f"  {g['model']:<24} {g['turns']:>4} tours · {_seconds(g['latency_mean'])} · "
              f"erreurs {g['error_rate']:.0%}" for g in summary["by_model"]]
    lines.append("\nPar configuration (prompt et paramètres) :")
    lines += [f"  {g['config_id']} depuis {g['since']} · {g['turns']} tours · {_seconds(g['latency_mean'])}"
              f" · {json.dumps(g['config'], ensure_ascii=False)}" for g in summary["by_config"]]
    lines.append("\nPar jour :")
    lines += [f"  {g['day']} · {g['turns']:>4} tours · {_seconds(g['latency_mean'])} · "
              f"erreurs {g['error_rate']:.0%}" for g in summary["by_day"]]
    if skipped:
        lines.append(f"\n{skipped} ligne(s) illisible(s) ignorée(s).")
    return "\n".join(lines)
