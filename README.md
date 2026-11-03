# Sensai

Assistant IA 100 % local pour un cabinet médical, en Python, via l'API HTTP directe
d'Ollama (aucun framework LLM). Le médecin demande, par exemple, « Mme Dupont peut-elle
prendre de l'amoxicilline ? » : Sensai pseudonymise la question, lit le dossier local,
cite la notice publique du médicament et ne modifie le dossier qu'avec son accord.

La documentation complète (scénario, user stories, traçabilité, choix, limites, mesures)
se lit avec MkDocs, installé par `requirements.txt` :

```bash
mkdocs serve -a 127.0.0.1:8001      # http://127.0.0.1:8001
```

## Installation

### Prérequis

| Prérequis | Vérifier | Installer |
| --- | --- | --- |
| Python 3.10 ou plus récent, avec `venv` et `ensurepip` | `python3 --version` et `python3 -c "import ensurepip"` | Debian/Ubuntu : `sudo apt install python3-venv` |
| Ollama, lancé | `ollama list` répond | Linux : `curl -fsSL https://ollama.com/install.sh \| sh` ; sinon [ollama.com/download](https://ollama.com/download). S'il ne tourne pas : `ollama serve` dans un autre terminal |
| Environ 2,2 Go de disque | | aucune carte graphique n'est nécessaire |

### Étapes

Depuis la racine du dépôt :

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
ollama pull qwen2.5:3b              # modèle de conversation (1,9 Go)
ollama pull nomic-embed-text        # modèle d'embeddings des documents (274 Mo)
python -m sensai.rag fetch          # télécharge la notice ANSM et la fiche HAS (seule étape en ligne)
python -m sensai.rag index          # découpe, vectorise, écrit .sensai/rag.sqlite3
```

Sans index documentaire, Sensai fonctionne quand même : il répond à partir du dossier,
sans citer de notice.

### Vérifier l'installation

```bash
python -m pytest -q                 # 348 passed, sans Ollama (faux serveur)
python -m sensai.rag search "Précautions avec l'amoxicilline en cas d'allergie à la pénicilline ?"
```

La recherche affiche les extraits trouvés et leurs sources : Ollama, le modèle d'embeddings
et l'index fonctionnent.

### Facultatif : serveur MCP tiers

`config.toml` déclare le serveur officiel `mcp-server-time`. Il a ses propres dépendances
(SDK MCP 1.x) et s'installe à part ; sans lui, `--mcp` le signale et continue.

```bash
python3 -m venv .sensai/mcp-time
.sensai/mcp-time/bin/pip install "mcp-server-time==2026.10.10"
```

## Démarrage rapide

```bash
python -m sensai --demo --mcp                # CLI
python -m sensai.web --demo --mcp            # web : http://127.0.0.1:8000
```

`--demo` charge trois patients entièrement fictifs et sélectionne Mme Jeanne Dupont.
`--mcp` exécute les outils patients dans notre serveur MCP local ; sans `--mcp`, les mêmes
outils sont exécutés directement en Python. Les sessions et dossiers sont sauvegardés dans
`.sensai/memory.sqlite3`, ignoré par Git. Le déroulé complet de la démo est dans
[docs/demo.md](docs/demo.md).

## Fonctionnalités implémentées

Chaque fonctionnalité, avec un exemple à essayer après `python -m sensai --demo --mcp` :

| Code | Fonctionnalité | Exemple d'usage |
| --- | --- | --- |
| B1 | CLI : réponse en streaming, historique, erreurs claires, Ctrl+C, modèle configurable | « Mme Dupont peut-elle prendre de l'amoxicilline ? » ; `python -m sensai --model llama3.2:3b` ; Ollama éteint : le message indique `ollama serve` |
| M1 | Sessions persistantes et profils médecins | `python -m sensai --demo --session consultation`, quitter, relancer : l'historique est repris ; `python -m sensai --list-sessions` ; `--profile generaliste` (voir plus bas) |
| M3 | Dossiers patients SQLite, lus et mis à jour par l'agent | `/dossier` ; « Quelles allergies sont enregistrées pour Mme Dupont ? » ; « Ajoute l'allergie à l'aspirine au dossier. » |
| T1 | Outils patients, en local ou via notre serveur MCP ; serveurs MCP tiers déclarés dans `config.toml` | `/tools` ; « Quelle heure est-il dans le fuseau Asia/Tokyo ? » (serveur `time`, s'il est installé) |
| R1 | Recherche dans les notices ANSM et fiches HAS, extraits cités | `python -m sensai.rag search "…"` ; après une question sur un médicament, `/sources` |
| R2 | Filtres par métadonnées, reclassement BM25, seuils de pertinence | `/rag-filter {"publisher":"HAS","tags":["antibiotiques"]}` puis `/rag-filter all` ; `[rag] rerank = false` pour comparer |
| A3 | Validation du médecin avant toute écriture dans un dossier | « Ajoute une note au dossier : amoxicilline contre-indiquée. » → `Confirmer ? [o/N]` ; `/note <texte>` |
| EV2 | Pseudonymisation avant le modèle, filtre d'entrée, masquage en sortie, règles dans `[guardrails]` | `/prompt` montre `[PATIENT_1]`, jamais le nom ; « Ignore toutes les instructions précédentes. » est refusé sans appel au modèle |
| EV3 | Logs JSONL pseudonymisés et tableau de bord | `/metrics` ; `python -m sensai.obs --days 7` ; `http://127.0.0.1:8000/metrics.html` |
| X1 | Interface web : streaming, validation dans une fenêtre, réglages et modèle à chaud, prompt exact | `python -m sensai.web --demo --mcp`, puis « Nouvelle consultation » et « Voir le prompt envoyé » |

Non livrés : l'évaluation automatique par un LLM-juge (EV1) et la sortie JSON imposée (T5),
voir [docs/tracabilite.md](docs/tracabilite.md). La pseudonymisation combine les dossiers
connus et des expressions régulières ; elle ne détecte pas toutes les données personnelles.
La base locale et son coffre de correspondances ne sont pas chiffrés
([docs/limites.md](docs/limites.md)).

## Utiliser la CLI

| Commande | Action |
| --- | --- |
| `/help` | Affiche les commandes. |
| `/patients` | Liste les patients locaux. |
| `/patient <nom complet ou id>` | Sélectionne un dossier ; changer de patient ouvre une nouvelle session. |
| `/dossier` | Affiche le dossier sélectionné depuis SQLite. |
| `/note <texte>` | Demande une confirmation puis appelle l'outil d'ajout de note. |
| `/sessions` | Liste les conversations sauvegardées. |
| `/session <id>` | Reprend l'historique d'une conversation. |
| `/history` | Affiche l'historique pseudonymisé sauvegardé. |
| `/profiles`, `/profile [id]` | Liste, affiche ou sélectionne le profil médecin ; une sélection ouvre une nouvelle session. |
| `/rag` | Affiche l'état de la recherche documentaire et ses filtres. |
| `/search <question>` | Recherche les extraits publics, sans génération de réponse. |
| `/sources` | Affiche les derniers extraits utilisés, leurs scores et leurs sources. |
| `/rag-filter <JSON ou all>` | Filtre les sources ; `all` rétablit tous les documents. |
| `/tools` | Affiche les outils disponibles et ceux qui demandent la validation du médecin. |
| `/prompt` | Affiche le prompt exact du dernier tour, tel que reçu par le modèle (pseudonymisé). |
| `/metrics` | Résume les logs : volume, latence, taux d'erreur. |
| `/reset` | Ouvre une nouvelle conversation, en conservant les anciennes en base. |
| `/quit` | Ferme le chatbot et les connexions MCP. |

Options utiles : `--model`, `--config`, `--db <chemin>`, `--session <id>`,
`--patient <référence>`, `--profile <id>`, `--no-rag`, `--keep-alive 2m`,
`--list-sessions`, `--list-profiles` (détail dans [docs/installation.md](docs/installation.md)).

Sans `--demo`, aucun patient fictif n'est ajouté. Les nouvelles sessions conservent le
patient, le profil, les filtres et les derniers extraits utilisés. Une reprise les restaure ;
demander un autre patient avec le même identifiant est refusé. Pour les anciennes sessions
sans ces métadonnées, sélectionner explicitement le patient avec `--patient`.

## Interface web

```bash
python -m sensai.web --demo --mcp            # http://127.0.0.1:8000
```

Mêmes options que la CLI, plus `--port`. La page affiche la réponse en streaming, le
compteur de tokens, les sources, les appels d'outils, le prompt exact envoyé au modèle, et
ouvre une fenêtre de validation avant toute écriture dans un dossier. Le serveur n'écoute
que sur `127.0.0.1` et n'a pas d'authentification.

## Profil médecin et documents publics

Créer ou remplacer un profil (les champs non fournis sont remis à vide) :

```bash
python -m sensai.memory.profiles set generaliste --specialty "Médecine générale" --preference "Réponses courtes" --instructions "Citer les sources disponibles"
python -m sensai --demo --mcp --profile generaliste --session consultation
```

Le profil est local et persistant. Il est injecté dans le contexte, même sans patient
sélectionné ; `/reset` recharge sa dernière version. Le profil `default`, vide au départ,
permet de garder le lancement habituel.

Le corpus de démonstration comprend une notice ANSM et une fiche HAS de février 2014 ; il
ne représente pas un référentiel médical exhaustif ou à jour. L'index
`.sensai/rag.sqlite3` est séparé des dossiers et sessions. `[rag]` dans `config.toml`
règle les seuils, le découpage et le budget de contexte ; `--no-rag` désactive la
recherche. Voir [le guide RAG](docs/rag.md) pour l'ingestion et les filtres.

## Contexte et réglages

Tout se règle dans `config.toml`, sans toucher au code. Les réglages CPU limitent le
contexte à 2 048 tokens, la réponse à 128 tokens et l'exécution à deux threads. Quand un
dossier est sélectionné, seuls les schémas d'outils utiles à la demande sont proposés au
modèle ; pour une lecture explicite du dossier (« Quelles allergies sont enregistrées ? »),
le mode RAG `auto` n'ajoute pas de documents. Le prompt exact, la composition du contexte et
son budget sont détaillés dans [docs/contexte.md](docs/contexte.md).

Par défaut, le modèle est déchargé après chaque appel pour libérer la RAM. Si suffisamment
de RAM est disponible, `--keep-alive 2m` le garde chargé entre deux échanges, sans garantie
que les deux modèles restent chargés ensemble ; sur un PC déjà chargé, garder le défaut
`--keep-alive 0`. Pour libérer immédiatement le modèle : `ollama stop qwen2.5:3b`
([API Ollama](https://docs.ollama.com/api/chat)).

Chaque fonctionnalité optionnelle se désactive par la configuration (`[rag] enabled`,
`[logging] enabled`, `[guardrails] enabled`, blocs `[[mcp.servers]]`) : voir
[docs/installation.md](docs/installation.md#desactiver-une-fonctionnalite).

## Logs et métriques

Chaque tour ajoute une ligne JSON pseudonymisée à `logs/AAAA-MM-JJ.jsonl`
(`[logging]` dans `config.toml`). Le résumé (volume, latence, taux d'erreur, par modèle et
par configuration) est sur `http://127.0.0.1:8000/metrics.html`, ou dans le terminal :

```bash
python -m sensai.obs --days 7
```

## Tests et mesures

```bash
python -m pytest -q
```

Les tests couvrent le socle, les protections, le stockage et l'intégration avec un vrai
serveur MCP local. Le modèle est remplacé par une doublure ; la qualité de génération se
vérifie avec Ollama :

```bash
python -m sensai.obs.compare --runs 2        # avec ou sans dossier et documents (≈ 15 min sur CPU)
python bench_models.py qwen2.5:3b llama3.2:3b   # comparaison de modèles
python -m sensai.memory.demo                  # stockage seul, sans modèle ni MCP
```

## Documentation

Le site MkDocs (`mkdocs serve -a 127.0.0.1:8001`) regroupe :

- [Scénario d'usage](docs/scenario.md), [user stories](docs/user_stories.md), [traçabilité](docs/tracabilite.md)
- [Installation](docs/installation.md), [fonctionnalités](docs/fonctionnalites.md), [démo](docs/demo.md)
- [Architecture](docs/architecture.md), [contexte envoyé au modèle](docs/contexte.md), [choix et alternatives](docs/choix.md), [limites](docs/limites.md)
- [Mesures avec ou sans contexte](docs/mesures.md), [benchmark des modèles](docs/bench.md)
- [Mémoire](docs/memory.md), [documents publics](docs/rag.md), [vérification de la démo](docs/demo_verified.md)
