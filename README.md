# Sensai

Assistant médical local en Python, via l'API HTTP directe d'Ollama.

## Installation

Python 3.10 ou plus récent, Ollama et un modèle compatible avec les outils :

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
ollama pull qwen2.5:3b
```

Si Ollama n'est pas déjà lancé, démarrer `ollama serve` dans un autre terminal.

## Démo médicale

```bash
python -m sensai --demo --mcp --session midterm
```

`--demo` charge trois patients entièrement fictifs et sélectionne Mme Jeanne Dupont.
`--mcp` lance le serveur MCP médical local pour la consultation et l'ajout de notes.
Sans `--mcp`, les mêmes outils patients sont exécutés directement en Python.
Les sessions et dossiers sont sauvegardés dans `.sensai/memory.sqlite3`, ignoré par Git.

Le modèle est configurable dans `config.toml` ou avec `--model`.
Le scénario conseillé et les limites se trouvent dans [docs/midterm.md](docs/midterm.md).

Les réglages CPU dans `config.toml` limitent le contexte à 2 048 tokens, la réponse
à 128 tokens et l'exécution à deux threads. Le modèle est déchargé après chaque
appel pour libérer la RAM ; les appels suivants peuvent donc démarrer plus lentement.
Quand un dossier est sélectionné, seuls les schémas utiles à la demande sont
proposés au modèle (note, calcul, date/heure, ou demande explicite de `get_patient`).
Une simple question sur le dossier déjà fourni ne déclenche pas une relecture par outil.

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
| `/tools` | Affiche les outils disponibles. |
| `/reset` | Ouvre une nouvelle conversation, en conservant les anciennes en base. |
| `/quit` | Ferme le chatbot et les connexions MCP. |

Pour reprendre la démo après arrêt :

```bash
python -m sensai --demo --mcp --session midterm
```

Pour lister les sessions sans utiliser le modèle :

```bash
python -m sensai --list-sessions
```

Sans `--demo`, aucun patient fictif n'est ajouté. `--db <chemin>` sélectionne une
autre base et `--patient <référence>` choisit explicitement le dossier au démarrage.
Le choix du patient reste explicite à la reprise ; il n'est pas stocké dans la session.

## Fonctionnalités disponibles

- CLI avec réponses en streaming, historique, interruption et gestion des erreurs.
- Sessions SQLite persistantes, avec correspondances des pseudonymes.
- Patients SQLite : création, consultation, mise à jour, suppression et ajout de notes.
- Contexte patient local, actualisé à chaque tour, avec provenance SQLite.
- Outils locaux et transport MCP stdio pour les outils patients.
- Confirmation humaine avant les écritures par outil ou commande `/note`.
- Détection de certaines injections et pseudonymisation avant envoi au modèle.

Le profil médecin, le RAG sur les documents ANSM/HAS, le reranking, l'évaluation
automatique, l'interface web et le monitoring restent à développer.
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

## Documentation

- [Scénario de soutenance](docs/midterm.md)
- [API de stockage et choix techniques](docs/memory.md)
- [User stories](docs/user_stories.md)
- [Benchmark des modèles](docs/bench.md)
