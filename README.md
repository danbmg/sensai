# Sensai

Assistant médical local en Python, via l'API HTTP directe d'Ollama.

La documentation complète (scénario, user stories, choix, limites, mesures) se lit avec
MkDocs, installé par `requirements.txt` :

```bash
mkdocs serve -a 127.0.0.1:8001      # http://127.0.0.1:8001
```

## Installation

Python 3.10 ou plus récent, Ollama et un modèle compatible avec les outils :

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
ollama pull qwen2.5:3b
```

Si Ollama n'est pas déjà lancé, démarrer `ollama serve` dans un autre terminal.

Facultatif : le serveur MCP tiers déclaré dans `config.toml` (`mcp-server-time`) a ses propres
dépendances et s'installe à part. Sans lui, `--mcp` le signale et continue.

```bash
python3 -m venv .sensai/mcp-time
.sensai/mcp-time/bin/pip install "mcp-server-time==2026.10.10"
```

## Interface web

```bash
python -m sensai.web --demo --mcp            # http://127.0.0.1:8000
```

Mêmes options que la CLI (`--model`, `--config`, `--db`, `--no-rag`…), plus `--port`.
La page affiche la réponse en streaming, le compteur de tokens, les sources, les appels
d'outils, le prompt exact envoyé au modèle, et ouvre une fenêtre de validation avant toute
écriture dans un dossier. Le serveur n'écoute que sur `127.0.0.1` et n'a pas
d'authentification.

## Logs et métriques

Chaque tour ajoute une ligne JSON pseudonymisée à `logs/AAAA-MM-JJ.jsonl`
(`[logging]` dans `config.toml`). Le résumé (volume, latence, taux d'erreur, par modèle et
par configuration) est sur `http://127.0.0.1:8000/metrics.html`, ou dans le terminal :

```bash
python -m sensai.obs --days 7
```

## Démo médicale

```bash
python -m sensai --demo --mcp --session consultation
```

`--demo` charge trois patients entièrement fictifs et sélectionne Mme Jeanne Dupont.
`--mcp` lance le serveur MCP médical local pour la consultation et l'ajout de notes.
Sans `--mcp`, les mêmes outils patients sont exécutés directement en Python.
Les sessions et dossiers sont sauvegardés dans `.sensai/memory.sqlite3`, ignoré par Git.

Le modèle est configurable dans `config.toml` ou avec `--model`.
Le déroulé de la démo est dans [docs/demo.md](docs/demo.md), les limites dans [docs/limites.md](docs/limites.md).

Les réglages CPU dans `config.toml` limitent le contexte à 2 048 tokens, la réponse
à 128 tokens et l'exécution à deux threads. Par défaut, le modèle est déchargé après chaque
appel pour libérer la RAM ; les appels suivants peuvent donc démarrer plus lentement.
Quand un dossier est sélectionné, seuls les schémas utiles à la demande sont
proposés au modèle (note, calcul, date/heure, ou demande explicite de `get_patient`).
Une simple question sur le dossier déjà fourni ne déclenche pas une relecture par outil.

Pour les lectures explicites du dossier, comme « Quelles allergies sont enregistrées ? »,
le mode RAG `auto` évite aussi l'appel aux embeddings et l'ajout de documents inutiles.
Une demande sur un médicament ou une question ambiguë conserve la recherche documentaire.
Les vecteurs des seize dernières questions sont gardés en cache en RAM, sans cache sur disque ;
les extraits sont toujours recherchés dans la version actuelle de l'index.

Si suffisamment de RAM est disponible, garder le modèle chargé pendant deux minutes
peut éviter son rechargement entre deux échanges :

```bash
python -m sensai --demo --mcp --session consultation --keep-alive 2m
```

Cette option concerne le modèle de conversation et consomme de la RAM entre les appels.
Elle ne garantit pas que le serveur pourra conserver simultanément les deux modèles.
Sur un PC dont la mémoire est déjà occupée, conserver le défaut `--keep-alive 0`.
Pour libérer immédiatement un modèle conservé en mémoire : `ollama stop qwen2.5:3b`.
Le réglage suit [l'API Ollama](https://docs.ollama.com/api/chat).

Commandes :

| Commande | Action |
| --- | --- |
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
| `/tools` | Affiche les outils disponibles. |
| `/reset` | Ouvre une nouvelle conversation, en conservant les anciennes en base. |
| `/quit` | Ferme le chatbot et les connexions MCP. |

Pour reprendre la démo après arrêt :

```bash
python -m sensai --demo --mcp --session consultation
```

Pour lister les sessions sans utiliser le modèle :

```bash
python -m sensai --list-sessions
```

Sans `--demo`, aucun patient fictif n'est ajouté. `--db <chemin>` sélectionne une
autre base et `--patient <référence>` choisit explicitement le dossier au démarrage.
Les nouvelles sessions conservent le patient, le profil, les filtres et les derniers
extraits utilisés. Une reprise les restaure ; demander un autre patient avec le
même identifiant est refusé. Pour les anciennes sessions sans ces métadonnées,
sélectionner explicitement le patient avec `--patient`.

## Profil médecin et documents publics

Créer ou remplacer un profil (les champs non fournis sont remis à vide) :

```bash
python -m sensai.memory.profiles set generaliste --specialty "Médecine générale" --preference "Réponses courtes" --instructions "Citer les sources disponibles"
python -m sensai --demo --mcp --profile generaliste --session consultation
```

La configuration du profil est locale et persistante. Elle est injectée via
`ContextProvider`, même sans patient sélectionné. `/reset` recharge sa dernière version.
Le profil `default`, vide au départ, permet de garder le lancement habituel.

Préparer une fois le petit corpus public ANSM/HAS, puis lancer le chatbot :

```bash
ollama pull nomic-embed-text
python -m sensai.rag fetch
python -m sensai.rag index
python -m sensai.rag search "Précautions avec l’amoxicilline en cas d’allergie à la pénicilline ?"
python -m sensai --demo --mcp --profile generaliste --session consultation
```

`fetch` est la seule étape qui télécharge les documents publics. Les recherches
et la conversation utilisent ensuite Ollama et les fichiers locaux. Le corpus de
démonstration comprend une notice et une fiche HAS datée de février 2014 ; il ne
représente pas un référentiel médical exhaustif ou systématiquement à jour.
L'index `.sensai/rag.sqlite3` est séparé des dossiers et sessions. `[rag]` dans
`config.toml` règle les seuils, le découpage et le budget de contexte ; `--no-rag`
désactive la recherche. Voir [le guide RAG](docs/rag.md) pour l'ingestion et les filtres.

## Fonctionnalités disponibles

- CLI avec réponses en streaming, historique, interruption et gestion des erreurs.
- Sessions SQLite persistantes, avec correspondances des pseudonymes.
- Profils médecins persistants : spécialité, préférences et instructions personnalisées.
- Patients SQLite : création, consultation, mise à jour, suppression et ajout de notes.
- Contexte patient local, actualisé à chaque tour, avec provenance SQLite.
- Ingestion PDF/HTML/texte public ANSM/HAS, embeddings Nomic via `/api/embed`, recherche cosinus.
- Extraits sourcés injectés via `ContextProvider`, filtres et reclassement lexical BM25.
- Outils locaux et transport MCP stdio pour les outils patients ; serveurs MCP tiers déclarés
  dans `[[mcp.servers]]` (serveur officiel `mcp-server-time` fourni en exemple).
- Confirmation humaine avant les écritures par outil ou commande `/note`.
- Détection de certaines injections et pseudonymisation avant envoi au modèle ; règles
  réglables dans `[guardrails]`.
- Interface web : streaming SSE, validation dans une fenêtre, réglages et modèle modifiables à chaud.
- Logs JSONL pseudonymisés et tableau de bord des métriques.

L'évaluation automatique par un LLM-juge (EV1) et la sortie JSON imposée (T5) ne sont pas livrées.
La pseudonymisation combine les dossiers connus et des expressions régulières ;
elle ne constitue pas une détection exhaustive de toutes les données personnelles.
La base locale et son coffre de correspondances ne sont pas chiffrés.

## Tests

```bash
python -m pytest -q
```

Les tests couvrent le socle, les protections, le stockage et l'intégration avec un
vrai serveur MCP local. Le modèle est remplacé par une doublure dans les tests
automatisés ; la qualité de génération doit également être vérifiée avec Ollama.

La démo de stockage autonome ne nécessite ni modèle ni connexion MCP :

```bash
python3 -m sensai.memory.demo
```

Mesure avec le vrai modèle, réponse avec ou sans dossier et documents (≈ 15 min sur CPU) :

```bash
python -m sensai.obs.compare --runs 2
```

## Documentation

Le site MkDocs (`mkdocs serve -a 127.0.0.1:8001`) regroupe :

- [Scénario d'usage](docs/scenario.md), [user stories](docs/user_stories.md), [traçabilité](docs/tracabilite.md)
- [Installation](docs/installation.md), [fonctionnalités](docs/fonctionnalites.md), [démo](docs/demo.md)
- [Architecture et contexte](docs/architecture.md), [choix et alternatives](docs/choix.md), [limites](docs/limites.md)
- [Mesures avec ou sans contexte](docs/mesures.md), [benchmark des modèles](docs/bench.md)
- [Mémoire](docs/memory.md), [documents publics](docs/rag.md), [vérification de la démo](docs/demo_verified.md)

### Créer et supprimer un patient par conversation

- « Ajoute un patient nommé Jean Martin, né le 1980-03-12 » appelle `create_patient`.
  Seul le nom est obligatoire ; une date inconnue reste vide. Les autres données
  peuvent ensuite être ajoutées avec les outils du dossier.
- « Supprime le patient Jean Martin » propose `delete_patient`, après identification
  avec `find_patients` ou `get_patient` si nécessaire. Un nom ambigu est refusé.

Les deux actions demandent la confirmation du médecin avant écriture, en local
comme avec `--mcp`. La suppression efface définitivement le dossier SQLite ; elle
ne supprime pas les historiques des conversations. Si le dossier sélectionné est
supprimé, sélectionner un autre patient pour poursuivre une consultation.
