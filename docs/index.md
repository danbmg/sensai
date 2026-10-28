# Sensai

Sensai est un **assistant IA 100 % local pour un cabinet médical**, écrit en Python.
Le modèle tourne sur le PC du cabinet via [Ollama](https://ollama.com) : aucune donnée
patient ne quitte la machine, et aucun framework LLM n'est utilisé (appels HTTP directs).

!!! example "Le fil rouge"
    Le Dr Martin demande : **« Mme Dupont peut-elle prendre de l'amoxicilline ? »**
    L'assistant :

    1. remplace le nom de la patiente par un pseudonyme avant l'envoi au modèle ;
    2. retrouve dans son dossier local l'allergie à la pénicilline ;
    3. cite la notice publique du médicament (ANSM) ;
    4. propose d'ajouter une note au dossier et attend la validation du médecin.

    Le détail est dans [Scénario d'usage](scenario.md).

## Fonctionnalités livrées

Les étoiles sont la difficulté donnée par le catalogue du sujet.

| Code | Fonctionnalité | Étoiles | Dans Sensai |
|---|---|---|---|
| B1 | Chatbot CLI (base obligatoire) | — | `python -m sensai` : streaming, historique, erreurs, modèle configurable |
| M1 | Sessions persistantes et profils | ⭐ | sessions SQLite reprises au redémarrage, profil médecin injecté |
| M3 | Mémoire structurée externe | ⭐⭐ | dossiers patients SQLite lus et modifiés par l'agent |
| T1 | Outils et MCP | ⭐⭐⭐ | outils patients, en local ou via notre serveur MCP (`--mcp`) ; serveurs MCP tiers déclarés dans `config.toml` |
| R1 | RAG de base | ⭐⭐ | notices ANSM / HAS découpées, vectorisées (Nomic), extraits cités |
| R2 | RAG avancé | ⭐⭐⭐ | filtres par métadonnées, reclassement BM25, seuils de pertinence |
| A3 | Validation humaine | ⭐ | toute écriture dans un dossier attend l'accord du médecin |
| EV2 | Garde-fous contenu et données personnelles | ⭐⭐⭐ | pseudonymisation avant le modèle, filtre d'entrée et masquage en sortie réglables dans `config.toml` |
| EV3 | Logs et tableau de bord | ⭐⭐ | un JSONL pseudonymisé par jour, page `/metrics.html` |
| X1 | Interface web | ⭐ | `python -m sensai.web` : streaming SSE, confirmation, réglages |

Les fonctionnalités prévues mais non livrées (EV1, T5) sont listées dans
[Traçabilité](tracabilite.md#fonctionnalites-abandonnees-ou-modifiees).

## Démarrage rapide

```bash
python3 -m venv .venv && source .venv/bin/activate
python -m pip install -r requirements.txt
ollama pull qwen2.5:3b && ollama pull nomic-embed-text
python -m sensai.rag fetch && python -m sensai.rag index     # corpus public, une seule fois
python -m sensai --demo --mcp                                # CLI
python -m sensai.web --demo --mcp                            # web : http://127.0.0.1:8000
```

Le détail, les options et les erreurs possibles sont dans [Installation](installation.md).

## Lire cette documentation en local

```bash
mkdocs serve -a 127.0.0.1:8001     # le port 8000 est celui de l'interface web Sensai
mkdocs build                       # site statique dans site/
```

## Équipe

| Membre | Bloc |
|---|---|
| Dan | socle, pipeline, CLI, interface web, validation humaine, logs |
| Timothée | mémoire (sessions, profils, patients SQLite) et RAG |
| Matteo | outils et MCP, garde-fous et pseudonymisation |
