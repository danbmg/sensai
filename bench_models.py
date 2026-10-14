"""Mesure des modèles candidats sur le scénario Dupont (étape 0).

Usage : python bench_models.py <modèle> [...] [--runs 3] [--budget 30] [--timeout 300] [--host URL]

Un tour = 2 appels /api/chat en streaming, comme le fera le pipeline :
  1. contexte déjà pseudonymisé + question -> le modèle doit appeler add_patient_note ;
  2. résultat de l'outil renvoyé -> réponse finale, qui doit parler de l'allergie.
"""
import argparse
import statistics
import sys
import time
import unicodedata
from contextlib import closing
from dataclasses import dataclass, field

import requests

from sensai.core.config import load_config
from sensai.core.interfaces import Message
from sensai.core.ollama_client import DEFAULT_HOST, ModelNotFoundError, OllamaClient

OPTIONS = {"temperature": 0, "num_ctx": 4096}

TOOL = {
    "type": "function",
    "function": {
        "name": "add_patient_note",
        "description": "Ajoute une note au dossier d'un patient (validation du médecin requise).",
        "parameters": {
            "type": "object",
            "properties": {
                "patient": {"type": "string", "description": "Patient concerné, ex. [PATIENT_1]"},
                "note": {"type": "string", "description": "Texte de la note"},
            },
            "required": ["patient", "note"],
        },
    },
}

# Contexte tel que le pipeline l'enverra : déjà passé par vault.mask().
PATIENT_RECORD = """Dossier patient — [PATIENT_1]
Née le [NAISSANCE_1]. Domicile : [ADRESSE_1].
Antécédents : hypertension artérielle traitée par amlodipine 5 mg/j ; appendicectomie (1989).
Allergies : PÉNICILLINES — urticaire généralisée et œdème de Quincke en 2019 après pénicilline V.
Traitement en cours : amlodipine 5 mg, 1 cp/j.
Dernière consultation : bilan tensionnel satisfaisant."""

# Résumés rédigés pour le bench à partir de documents publics (pas des citations).
EXTRACTS = [
    """[Notice amoxicilline — résumé, base de données publique des médicaments (ANSM)]
L'amoxicilline est un antibiotique de la famille des pénicillines (bêta-lactamines). Contre-indications :
hypersensibilité à l'amoxicilline, à l'une des pénicillines ou à l'un des excipients ; antécédent de
réaction d'hypersensibilité immédiate sévère (par exemple anaphylaxie) à une autre bêta-lactamine,
comme une céphalosporine, un carbapénème ou un monobactame. Mises en garde : avant tout traitement,
rechercher des antécédents de réaction d'hypersensibilité aux bêta-lactamines. Des réactions graves,
parfois fatales, dont des réactions anaphylactiques, ont été rapportées chez des patients traités par
pénicillines ; elles sont plus probables chez les personnes ayant des antécédents d'allergie. En cas de
réaction allergique, le traitement doit être arrêté et une prise en charge adaptée mise en place.""",
    """[Allergie aux bêta-lactamines — résumé de recommandations (HAS)]
Une allergie déclarée aux pénicillines doit être documentée dans le dossier : molécule en cause, type
de réaction, délai d'apparition et date. Une réaction immédiate (urticaire, œdème de Quincke, choc
anaphylactique) contre-indique toutes les pénicillines, y compris l'amoxicilline, sauf avis allergologique
après bilan. Le risque d'allergie croisée avec les céphalosporines est faible mais non nul et dépend
de la molécule. En cas d'allergie confirmée, l'antibiotique de remplacement est choisi selon
l'indication, par exemple un macrolide, en tenant compte des résistances locales. Une consultation
d'allergologie peut permettre de lever une étiquette d'allergie erronée.""",
    """[Notice paracétamol — résumé, base de données publique des médicaments (ANSM)]
Le paracétamol est un antalgique et antipyrétique. Chez l'adulte de plus de 50 kg, la posologie
usuelle est de 500 mg à 1 g par prise, à renouveler si besoin au bout de 4 heures minimum, sans
dépasser 3 g par jour sans avis médical. La dose maximale doit être réduite en cas d'insuffisance
hépatique, d'alcoolisme chronique, de malnutrition ou de déshydratation. Un surdosage peut provoquer
une atteinte hépatique grave. Il faut vérifier l'absence de paracétamol dans les autres médicaments
pris en même temps pour éviter un surdosage.""",
]

QUESTION = "[PATIENT_1] peut-elle prendre de l'amoxicilline ? Si non, ajoute une note à son dossier."
TOOL_RESULT = "Note ajoutée au dossier de [PATIENT_1]."


class BenchTimeout(Exception):
    pass


@dataclass
class Run:
    first_fragment_s: float
    turn_s: float
    load_s: float
    prompt_tokens: int
    prompt_tps: float
    gen_tps: float
    tool_ok: bool
    answer_ok: bool


@dataclass
class ModelResult:
    model: str
    thinking: bool = False
    status: str = ""                # vide si mesuré, sinon raison de l'absence de mesure
    runs: list[Run] = field(default_factory=list)


def build_messages(system_prompt: str, run_index: int) -> list[Message]:
    """Messages d'un tour : system prompt numéroté, dossier et extraits, question."""
    # Numéro de consultation en tête : empêche Ollama de réutiliser le cache du prompt
    # d'un tour à l'autre, pour mesurer une vraie lecture complète à chaque tour.
    system = f"Consultation n°{run_index + 1}.\n{system_prompt}"
    context = "\n\n".join([PATIENT_RECORD, *EXTRACTS])
    return [
        {"role": "system", "content": system},
        {"role": "system", "content": context},
        {"role": "user", "content": QUESTION},
    ]


def _normalize(text: str) -> str:
    """Minuscules sans accents, pour trouver un mot quelle que soit sa graphie."""
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()


def answer_ok(text: str) -> bool:
    """La réponse parle-t-elle de pénicilline ou d'allergie ?"""
    text = _normalize(text)
    return "penicilline" in text or "allerg" in text


def tool_ok(tool_calls: list[dict]) -> bool:
    """add_patient_note a-t-il été appelé pour [PATIENT_1] avec une vraie note ?"""
    for call in tool_calls:
        function = call.get("function", {})
        args = function.get("arguments")
        if function.get("name") != "add_patient_note" or not isinstance(args, dict):
            continue
        note = args.get("note")
        # Un petit modèle peut recopier le schéma JSON de l'outil à la place du texte de la note.
        note_ok = isinstance(note, str) and note.strip() and not note.strip().startswith("{")
        if str(args.get("patient", "")).strip() == "[PATIENT_1]" and note_ok:
            return True
    return False


def _stream(client: OllamaClient, messages: list[Message], start: float, deadline: float, stats: dict):
    """Un appel /api/chat ; renvoie (contenu, tool_calls) et cumule les mesures dans `stats`."""
    content, tool_calls = "", []
    with closing(client.chat_stream(messages, tools=[TOOL])) as stream:
        for chunk in stream:
            if time.monotonic() > deadline:
                raise BenchTimeout
            if stats["first"] is None and (chunk.content or chunk.thinking or chunk.tool_calls):
                stats["first"] = time.monotonic() - start
            content += chunk.content
            tool_calls += chunk.tool_calls
            if chunk.done:
                stats["load"] += chunk.load_s
                stats["prompt_tokens"] += chunk.prompt_tokens
                stats["prompt_s"] += chunk.prompt_eval_s
                stats["gen_tokens"] += chunk.completion_tokens
                stats["gen_s"] += chunk.eval_s
    return content, tool_calls


def run_turn(client: OllamaClient, system_prompt: str, run_index: int, timeout: float) -> Run:
    """Joue un tour (appel d'outil puis réponse finale) et renvoie ses mesures."""
    stats = {"first": None, "load": 0.0, "prompt_tokens": 0, "prompt_s": 0.0,
             "gen_tokens": 0, "gen_s": 0.0}
    start = time.monotonic()
    deadline = start + timeout
    messages = build_messages(system_prompt, run_index)

    content, tool_calls = _stream(client, messages, start, deadline, stats)
    first_prompt_tokens = stats["prompt_tokens"]
    answer = content
    if tool_calls:
        messages.append({"role": "assistant", "content": content, "tool_calls": tool_calls})
        for call in tool_calls:
            messages.append({"role": "tool", "tool_name": call.get("function", {}).get("name", ""),
                             "content": TOOL_RESULT})
        final, _ = _stream(client, messages, start, deadline, stats)
        answer += final

    return Run(
        first_fragment_s=stats["first"] if stats["first"] is not None else time.monotonic() - start,
        turn_s=time.monotonic() - start,
        load_s=stats["load"],
        prompt_tokens=first_prompt_tokens,
        prompt_tps=stats["prompt_tokens"] / stats["prompt_s"] if stats["prompt_s"] else 0.0,
        gen_tps=stats["gen_tokens"] / stats["gen_s"] if stats["gen_s"] else 0.0,
        tool_ok=tool_ok(tool_calls),
        answer_ok=answer_ok(answer),
    )


def bench_model(model: str, host: str, system_prompt: str, runs: int, timeout: float) -> ModelResult:
    """Vérifie les capacités du modèle puis enchaîne `runs` tours mesurés."""
    result = ModelResult(model)
    probe = OllamaClient(model, host, timeout=timeout)
    try:
        capabilities = probe.capabilities()
    except ModelNotFoundError:
        result.status = f"absent : `ollama pull {model}`"
        return result
    if "tools" not in capabilities:
        result.status = "ignoré : pas de capacité `tools`"
        return result
    result.thinking = "thinking" in capabilities

    client = OllamaClient(model, host, options=OPTIONS, timeout=timeout,
                          think=False if result.thinking else None)
    for i in range(runs):
        print(f"  {model} — tour {i + 1}/{runs}…", file=sys.stderr)
        try:
            result.runs.append(run_turn(client, system_prompt, i, timeout))
        except (BenchTimeout, requests.Timeout):
            result.status = f"❌ timeout (> {timeout:g} s)"
            break
    return result


def _ratio(flags: list[bool]) -> str:
    """✅ si tous OK, ❌ si aucun, sinon « n/total »."""
    ok = sum(flags)
    return "✅" if ok == len(flags) else "❌" if ok == 0 else f"{ok}/{len(flags)}"


def summarize(result: ModelResult, budget: float) -> list[str]:
    """Ligne du tableau d'un modèle : médianes hors tour à froid, puis verdict."""
    name = f"`{result.model}`" + (" ⚠ thinking" if result.thinking else "")
    if not result.runs or result.status:
        return [name, result.status or "aucune mesure", *[""] * 8]
    cold, warm = result.runs[0], result.runs[1:] or result.runs
    med = lambda attr: statistics.median(getattr(r, attr) for r in warm)
    tools, answers = [r.tool_ok for r in warm], [r.answer_ok for r in warm]
    verdict = all(tools) and all(answers) and med("turn_s") <= budget
    return [name, "✅" if verdict else "❌", f"{med('turn_s'):.1f}", f"{med('first_fragment_s'):.1f}",
            f"{cold.load_s:.1f}", f"{med('prompt_tps'):.0f}", f"{med('gen_tps'):.1f}",
            f"{med('prompt_tokens'):.0f}", _ratio(tools), _ratio(answers)]


HEADER = ["Modèle", "Verdict", "Tour (s)", "1er fragment (s)", "Chargement à froid (s)",
          "Lecture (tok/s)", "Génération (tok/s)", "Tokens prompt", "Outil OK", "Réponse OK"]


def format_table(results: list[ModelResult], budget: float) -> str:
    """Tableau Markdown de tous les modèles mesurés."""
    rows = [HEADER, ["---"] * len(HEADER), *(summarize(r, budget) for r in results)]
    return "\n".join("| " + " | ".join(row) + " |" for row in rows)


def main(argv: list[str] | None = None) -> int:
    """Point d'entrée : vérifie Ollama, mesure chaque modèle, affiche le tableau."""
    parser = argparse.ArgumentParser(description="Mesure les modèles candidats sur le scénario Dupont.")
    parser.add_argument("models", nargs="+", help="modèles Ollama à comparer")
    parser.add_argument("--runs", type=int, default=3, help="tours par modèle, le 1er (à froid) hors médiane")
    parser.add_argument("--budget", type=float, default=30, help="durée max d'un tour pour le verdict (s)")
    parser.add_argument("--timeout", type=float, default=300, help="abandon d'un tour au-delà (s)")
    parser.add_argument("--host", default=DEFAULT_HOST)
    args = parser.parse_args(argv)

    try:
        OllamaClient("", args.host, timeout=10).list_models()
    except requests.ConnectionError:
        print(f"Ollama ne répond pas sur {args.host} : lancez `ollama serve`.", file=sys.stderr)
        return 1

    system_prompt = load_config().system_prompt
    results = []
    try:
        for model in args.models:
            results.append(bench_model(model, args.host, system_prompt, args.runs, args.timeout))
    except requests.ConnectionError:
        print(f"Ollama a cessé de répondre pendant la mesure de {model}.", file=sys.stderr)
        return 1

    print(f"Budget {args.budget:g} s par tour · {args.runs} tour(s) par modèle · "
          f"médiane hors 1er tour · options {OPTIONS}\n")
    print(format_table(results, args.budget))
    return 0


if __name__ == "__main__":
    sys.exit(main())
