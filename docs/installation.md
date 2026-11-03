# Installation et lancement

## Prérequis

- **Python 3.10 ou plus récent** (testé en 3.12 et 3.14), avec le module `venv`. Sous
  Debian/Ubuntu, il est dans un paquet séparé : si `python3 -c "import ensurepip"` échoue,
  `sudo apt install python3-venv`.
- **[Ollama](https://ollama.com)** installé et lancé. Sous Linux :
  `curl -fsSL https://ollama.com/install.sh | sh` ; sinon [ollama.com/download](https://ollama.com/download).
  `ollama list` doit répondre ; sinon lancer `ollama serve` dans un autre terminal.
- Environ **2,2 Go** de disque pour les deux modèles : `qwen2.5:3b` (1,9 Go) et
  `nomic-embed-text` (274 Mo). Aucune carte graphique n'est nécessaire.

## Installer

Depuis la racine du dépôt :

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
ollama pull qwen2.5:3b
ollama pull nomic-embed-text
```

`requirements.txt` suffit : il contient aussi MkDocs pour cette documentation.

## Préparer les documents publics (une fois)

```bash
python -m sensai.rag fetch      # télécharge la notice ANSM et la fiche HAS (seule étape en ligne)
python -m sensai.rag index      # découpe, vectorise avec nomic-embed-text, écrit .sensai/rag.sqlite3
python -m sensai.rag search "Précautions avec l'amoxicilline en cas d'allergie à la pénicilline ?"
```

Sans index, Sensai fonctionne quand même : il répond à partir du dossier, sans citer de notice.

## Installer le serveur MCP tiers (facultatif)

`config.toml` déclare le serveur officiel `mcp-server-time`. Il a ses propres dépendances
(SDK MCP 1.x) : il s'installe dans un environnement séparé, une fois.

```bash
python3 -m venv .sensai/mcp-time
.sensai/mcp-time/bin/pip install "mcp-server-time==2026.10.10"
```

Sans cette étape, `--mcp` affiche `Serveur MCP « time » ignoré : …` et continue sans lui.

## Lancer la CLI

```bash
python -m sensai --demo --mcp
```

| Option | Effet |
|---|---|
| `--demo` | ajoute trois patients fictifs et ouvre le dossier de Mme Jeanne Dupont |
| `--mcp` | exécute les outils patients dans un serveur MCP séparé (sinon, en Python direct) |
| `--model NOM` | remplace le modèle de `config.toml` pour ce lancement |
| `--config FICHIER` | utilise un autre fichier de configuration |
| `--session ID` | crée ou reprend une session nommée |
| `--patient NOM` / `--profile ID` | choisit le dossier et le profil médecin |
| `--no-rag` | désactive la recherche documentaire pour ce lancement |
| `--keep-alive 2m` | garde le modèle en RAM entre deux questions (défaut `0` : il est libéré) |
| `--db CHEMIN` | utilise une autre base SQLite (défaut `.sensai/memory.sqlite3`) |
| `--list-sessions`, `--list-profiles` | liste sans appeler le modèle |

Dans la CLI, `/help` affiche les commandes (`/dossier`, `/note`, `/sources`, `/reset`,
`/quit`…). La liste complète est dans [Fonctionnalités](fonctionnalites.md#b1-chatbot-en-ligne-de-commande).

## Lancer l'interface web

```bash
python -m sensai.web --demo --mcp            # http://127.0.0.1:8000
python -m sensai.web --demo --port 8080      # autre port
```

Les options sont les mêmes que pour la CLI. Le serveur n'écoute que sur la machine locale
(`127.0.0.1`) : il n'a pas d'authentification. Le tableau de bord est sur
`http://127.0.0.1:8000/metrics.html`.

Variante avec uvicorn, options passées par variables d'environnement :

```bash
SENSAI_DEMO=1 SENSAI_MCP=1 uvicorn sensai.web.api:app
```

## Configurer

Tout se règle dans `config.toml`, sans toucher au code.

| Section | Clés principales | Rôle |
|---|---|---|
| `[model]` | `name`, `host`, `temperature`, `num_ctx`, `num_predict`, `num_thread`, `num_batch` | modèle de conversation et paramètres envoyés à Ollama |
| `[assistant]` | `system_prompt`, `max_tool_iterations`, `max_history_turns` | persona, relances après outil, fenêtre d'historique |
| `[rag]` | `enabled`, `search_mode`, `model`, `top_k`, `min_similarity`, `min_relevance`, `rerank`, `max_context_chars` | recherche documentaire |
| `[logging]` | `enabled`, `directory` | logs JSONL (EV3) |
| `[guardrails]` | `enabled`, `max_input_length`, `input_rules`, `output_types`, `[[guardrails.custom_rules]]` | filtres d'entrée et masquage de sortie (EV2) |
| `[[mcp.servers]]` | `name`, `command`, `args`, `tools`, `dangerous`, `keywords` | serveurs MCP tiers lancés avec `--mcp` (T1) |

### Désactiver une fonctionnalité

| Fonctionnalité | Par la configuration | Au lancement |
|---|---|---|
| RAG (R1, R2) | `[rag] enabled = false` | `--no-rag` |
| Reclassement BM25 (R2) | `[rag] rerank = false` | — |
| Logs (EV3) | `[logging] enabled = false` | — |
| Filtres d'entrée et de sortie (EV2) | `[guardrails] enabled = false` (la pseudonymisation reste active) | — |
| Un serveur MCP tiers | retirer son bloc `[[mcp.servers]]` | sans `--mcp` |
| Serveur MCP (T1) | — | sans `--mcp` : mêmes outils, en Python direct |
| Historique complet | `[assistant] max_history_turns = 0` | — |

## Vérifier

```bash
python -m pytest -q             # tests automatiques, sans vrai modèle : 356 passed (03/11)
python -m sensai.obs            # métriques calculées sur logs/
python -m sensai.obs.compare    # mesure avec / sans contexte, avec le vrai modèle (≈ 15 min sur CPU)
```

## Erreurs fréquentes

| Message | Que faire |
|---|---|
| `Ollama ne répond pas sur http://localhost:11434` | lancer `ollama serve` |
| `Modèle … absent. Installez-le avec : ollama pull …` | lancer la commande indiquée |
| `… ne sait pas appeler d'outils (capacité « tools » absente)` | choisir un modèle avec la capacité `tools` |
| `⚠ … est un modèle « thinking »` | avertissement : il fonctionne, mais trop lentement sur CPU |
| `Index documentaire illisible` | relancer `python -m sensai.rag index` |
| `MCP absent : installez requirements.txt` | réinstaller les dépendances dans le venv actif |
