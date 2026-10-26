# Choix techniques et alternatives

Pour chaque décision : ce qui a été choisi, ce qui a été écarté, pourquoi, et l'effet
observé. Quand un effet n'a pas été mesuré, c'est écrit.

## Modèle local plutôt qu'une API en ligne

- **Choix** : Ollama sur le PC du cabinet, appelé par HTTP direct (`requests`).
- **Écarté** : une API distante (plus rapide, meilleurs modèles) ; un framework LLM
  (LangChain, LlamaIndex), interdit par le sujet.
- **Pourquoi** : des données de santé ne sortent pas du cabinet ; sans framework, chaque
  appel est lisible dans `sensai/core/ollama_client.py`.
- **Impact** : la latence. Un tour coûte de 20 s (dossier seul) à 59 s (dossier + notices) sur CPU ([Mesures](mesures.md)) ;
  c'est la contrainte qui a guidé toutes les décisions suivantes.

## Le modèle : `qwen2.5:3b`

| Modèle | Tour | Outil appelé correctement | Verdict |
|---|---|---|---|
| **`qwen2.5:3b`** | 69 s | ✅ à chaque tour | **retenu** : seul fiable, le plus rapide des fiables |
| `llama3.2:1b` | 28,5 s | ❌ recopie le schéma JSON dans la note | écarté : inacceptable dans un dossier |
| `qwen3:4b-instruct` | 149 s | 1 fois sur 2 | écarté |
| `llama3.2:3b` | 171 s | ✅ | écarté : trop lent |
| `qwen3:4b` | > 4 min | — | écarté : modèle « thinking », réfléchit même avec `think: false` |

Mesuré par `bench_models.py` le 05/10, sur le même scénario ([détail](bench.md)).
**Impact** : un modèle qui écrit correctement dans un dossier, au prix d'une latence de 20 à
60 s par tour selon le contexte ([Mesures](mesures.md)).

## Le pipeline comme seule frontière des données personnelles

- **Choix** (contrat v2) : le pipeline masque et ré-identifie, avec un `PIIVault` par
  session dont la table est sauvegardée avec l'historique.
- **Écarté** (contrat v1) : chaque module masque ce qu'il reçoit, garde-fou sans état.
- **Pourquoi** : la v1 avait trois trous — le contexte recevait un texte masqué (impossible
  de chercher « Dupont » dans SQLite), personne ne ré-identifiait les arguments d'outils,
  et `[PATIENT_1]` pouvait changer de personne d'un tour à l'autre.
- **Impact** : un seul test de frontière couvre tout le trajet (`tests/core/test_pipeline.py`) :
  ni le modèle, ni l'embedding, ni l'historique, ni les logs ne contiennent « Dupont » ;
  l'outil et le médecin reçoivent « Jeanne Dupont ».

## Pseudonymiser plutôt qu'anonymiser

- **Choix** : remplacer par `[PATIENT_1]`, de façon réversible pour la session.
- **Écarté** : supprimer ou anonymiser définitivement.
- **Pourquoi** : le médecin doit lire le vrai nom, et l'outil doit écrire dans le bon dossier.
- **Impact** : la table des correspondances est une donnée sensible, stockée en local au
  même niveau que la base patients, **non chiffrée** ([Limites](limites.md)).

## Masquer la réponse complète, pas chaque fragment

- **Choix** : à l'affichage, un tampon retient un pseudonyme en cours d'écriture (24
  caractères au plus) ; au stockage, `OutputGuard` s'applique sur la **réponse complète**.
- **Écarté** : filtrer chaque fragment au fil de l'eau.
- **Pourquoi** : un nom coupé en deux fragments (« Dup » + « ont ») passerait.
- **Impact** : testé avec un faux modèle qui écrit « Mme Dup » puis « ont » ; un `[` isolé
  ne bloque pas le flux.

## Budget de contexte

- **Choix** : `num_ctx = 2048`, `num_predict = 128`, 4 tours d'historique, 3 extraits et
  2 600 caractères de documents, schémas d'outils filtrés, mode RAG `auto`.
- **Écarté** : tout envoyer (historique complet, tous les outils, extraits à chaque question).
- **Pourquoi** : le temps d'un tour est surtout la **lecture** du prompt (≈ 40 tokens/s sur ce CPU).
- **Impact mesuré** ([Mesures](mesures.md)) : la latence suit les tokens lus — 20 s pour
  310 tokens (dossier), 59 s pour 1 040 (dossier + 3 extraits). Le mode `auto` réduit le
  contexte d'une question sur le dossier de 2 989 à 613 caractères. Baisser `num_predict` de
  128 à 32 ne fait gagner que 3 à 4,5 s et coupe toutes les réponses : 128 est gardé.

## RAG : SQLite + NumPy, reclassement BM25

- **Choix** : vecteurs dans SQLite, similarité cosinus calculée avec NumPy, puis 70 % cosinus
  + 30 % BM25.
- **Écarté** : une base vectorielle (Chroma, Qdrant) ; un reranker neuronal.
- **Pourquoi** : deux documents publics ; aucun service à installer ; BM25 favorise les mots
  exacts (« amoxicilline ») sans charger un second modèle.
- **Impact** : simple à expliquer et à installer ; ne passerait pas à des milliers de documents
  (recherche en mémoire). Détails : [Documents publics](rag.md).

## Validation humaine dans le pipeline

- **Choix** : chaque outil d'écriture est marqué dangereux (`is_dangerous`) ; le pipeline
  attend la décision du médecin ; pas de réponse = refus.
- **Écarté** : demander au modèle de « demander la permission » dans sa réponse.
- **Pourquoi** : une consigne au modèle peut être ignorée ; un contrôle dans le code, non.
- **Impact** : vérifié en réel (refus → dossier inchangé, accord → note écrite).

## Serveurs MCP tiers : un processus et un environnement chacun

- **Choix** : chaque serveur tiers est décrit dans `[[mcp.servers]]` (commande, arguments,
  outils retenus, mots-clés) et lancé dans son propre environnement.
- **Écarté** : l'installer dans le venv de Sensai (impossible : `mcp-server-time` exige le
  SDK MCP 1.x, Sensai utilise le 2.x) ; écrire un adaptateur en Python par serveur.
- **Pourquoi** : c'est le principe de MCP — un serveur est un programme indépendant qui ne
  parle que le protocole ; le cabinet ajoute un outil sans toucher au code.
- **Impact** : préfixe des noms (`time_…`) contre les collisions, liste blanche d'outils pour
  garder un prompt court, serveur absent signalé puis ignoré.

## Règles des garde-fous dans la configuration

- **Choix** : familles de règles intégrées, types masqués en sortie et règles propres au
  cabinet dans `[guardrails]`.
- **Écarté** : règles écrites en dur dans le code (version d'avant le 28/10) ; un classifieur
  par modèle (un appel de plus par tour, sur 20 à 60 s déjà).
- **Pourquoi** : bloquer un contournement découvert ne doit pas attendre une nouvelle version.
- **Impact** : « Oublie ce qu'on t'a dit avant… » bloqué par deux règles de config, sans
  faux positif sur 7 questions médicales ; d'autres reformulations passent encore
  ([Limites](limites.md#garde-fous-dentree)).

## Web : SSE lu avec `fetch`, JavaScript sans framework

- **Choix** : `POST /api/chat` renvoie un flux `text/event-stream`, lu avec
  `fetch` + `ReadableStream` ; HTML et JS servis tels quels par FastAPI.
- **Écarté** : `EventSource` (ne fait que du GET, or la question part dans le corps) ;
  WebSocket (bidirectionnel, inutile : la confirmation passe par un simple POST) ;
  React ou Vue (étape de build, dépendances npm).
- **Pourquoi** : un seul sens de flux suffit ; pas d'outillage front à installer au cabinet.
- **Impact** : le backend est partagé avec la CLI (`sensai/app/`), testé avec un faux
  serveur Ollama.

## Logs : JSONL construits depuis le tour pseudonymisé

- **Choix** : une ligne JSON par tour, un fichier par jour, écrite depuis le `TurnRecord`.
- **Écarté** : écrire les logs à partir des événements d'affichage (en clair) ; un outil
  externe (Langfuse) ; une table SQLite.
- **Pourquoi** : les événements contiennent le vrai nom ; un fichier texte se relit et se
  supprime facilement ; aucun service en plus.
- **Impact** : aucune donnée patient en clair dans `logs/` (vérifié le 28/10) ; les métriques
  se recalculent depuis les fichiers.

## Modèle déchargé entre deux questions (`keep_alive = 0`)

- **Choix** : par défaut, Ollama libère la RAM après chaque appel ; `--keep-alive 2m` en option.
- **Écarté** : garder le modèle chargé en permanence.
- **Pourquoi** : pendant le bench, les 15 Go de RAM du PC étaient déjà saturés (7 Go de swap) ; garder en plus le modèle d'embedding chargé aggrave la situation.
- **Impact** : chaque tour recharge le modèle ; gain de `--keep-alive` non mesuré en génération.
