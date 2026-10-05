# Choix du modèle de chat — bench du 2026-10-05

**Proposition (à valider à 3) : `qwen2.5:3b`**, le seul modèle à la fois fiable (outil et réponse corrects à chaque tour) et le plus rapide des modèles fiables.

Reproduire : `python bench_models.py qwen3:4b-instruct qwen2.5:3b llama3.2:3b llama3.2:1b`

## Scénario mesuré

Un tour = la question Dupont, avec un contexte déjà pseudonymisé (dossier de `[PATIENT_1]` + 3 extraits ANSM/HAS, ~1 100 tokens) :

1. le modèle doit appeler `add_patient_note(patient="[PATIENT_1]", note=<texte>)` ;
2. on lui renvoie le résultat de l'outil ; sa réponse finale doit parler de l'allergie.

`temperature 0`, `num_ctx 4096`, 3 tours par modèle, médiane hors 1er tour (chargement à froid). Budget : 30 s par tour.

## Résultats

| Modèle | Tour (s) | 1er fragment (s) | Lecture (tok/s) | Génération (tok/s) | Outil OK | Réponse OK |
| --- | --- | --- | --- | --- | --- | --- |
| **`qwen2.5:3b`** | **69** | 59 | 42 | 9.4 | ✅ | ✅ |
| `qwen3:4b-instruct` | 149 | 82 | 27 | 4.8 | 1/2 | ✅ |
| `llama3.2:3b` | 171 | 74 | 33 | 6.2 | ✅ | ✅ |
| `llama3.2:1b` | 28.5 | 21 | 120 | 12.9 | ❌ | ✅ |

- `llama3.2:1b` tient le budget mais écrit dans la note le schéma JSON de l'outil (`{"type":"string","description":"..."}`) au lieu d'un texte : inacceptable pour un dossier médical.
- `qwen3:4b-instruct` et `llama3.2:3b` ont été mesurés avant l'ajout de ce contrôle de la note ; ils sont de toute façon éliminés par la durée.
- `qwen3:4b` nu (= Qwen3-4B-Thinking) est exclu d'office : il réfléchit toujours, plus de 4 min sans réponse.

## Limite : aucun modèle ne tient 30 s sur cette machine

Machine du bench : Intel Core 5 120U (portable basse consommation), pas de GPU utilisable par Ollama, 15 Go de RAM saturés pendant la mesure (7 Go de swap). La lecture du contexte (~1 100 tokens à ~40 tok/s) coûte à elle seule ~30 s.

Pistes, à trancher en réunion :

- relancer le bench sur un PC de l'équipe avec GPU NVIDIA ;
- réduire le contexte (moins d'extraits RAG) ;
- enregistrer la démo du tour complet à l'avance.
