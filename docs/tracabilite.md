# Traçabilité

Comment chaque fonctionnalité livrée se rattache à une user story, puis au
[scénario d'usage](scenario.md) (étapes S0 à S5), et où la vérifier.

## Fonctionnalité → user stories → scénario

| Fonctionnalité | User stories ([liste](user_stories.md)) | Étape | Code | Vérification |
|---|---|---|---|---|
| **B1** CLI | Voir la réponse s'écrire · Garder le fil · Comprendre une panne · Changer de modèle | S0 | `sensai/cli.py`, `sensai/core/ollama_client.py`, `sensai/core/config.py` | `tests/core/test_cli.py`, `test_ollama_client.py`, `test_config.py` |
| **M1** sessions et profils | Reprendre une session · Profil médecin · Conversations séparées · Choisir un profil | S0 | `sensai/memory/sessions.py`, `profiles.py` | `tests/memory/test_profiles.py`, `test_storage.py` |
| **M3** dossiers SQLite | Consulter un dossier · Mettre à jour un dossier | S2 | `sensai/memory/patients.py`, `context.py` | `tests/memory/test_storage.py`, `tests/tools/test_patient_tools.py` |
| **T1** outils et MCP | Consulter par un outil · Serveur MCP · Brancher un serveur existant | S2, S4 | `sensai/tools/` | `tests/tools/test_patient_tools.py`, `test_third_party_mcp.py`, `tests/test_integration.py` (vrai serveur MCP) |
| **R1** RAG | Rechercher dans les notices · Identifier les sources | S3 | `sensai/rag/documents.py`, `embeddings.py`, `store.py`, `retrieval.py` | `tests/rag/` |
| **R2** RAG avancé | Limiter les documents · Écarter les extraits peu pertinents | S3 | `sensai/rag/retrieval.py`, `routing.py` | `tests/rag/test_retrieval.py`, `test_context.py` |
| **A3** validation humaine | Valider une écriture · Valider depuis le web | S4 | `sensai/core/pipeline.py` (`_run_tool`), `sensai/web/confirmations.py` | `tests/core/test_pipeline.py`, `tests/web/test_api.py`, `test_live.py` |
| **EV2** garde-fous | Ne jamais envoyer l'identité · Bloquer et masquer · Adapter les règles | S1 | `sensai/guardrails/`, frontière dans `sensai/core/pipeline.py` | `tests/guardrails/` (dont `test_settings.py`), test de frontière dans `tests/core/test_pipeline.py` |
| **EV3** logs et métriques | Garder une trace · Suivre les performances | S5 | `sensai/obs/` | `tests/obs/test_obs.py` |
| **X1** web | Consulter depuis le navigateur · Choisir patient, profil, modèle · Voir ce que le modèle a reçu | S0, S4 | `sensai/web/` | `tests/web/` (faux serveur Ollama) |

Chaque user story renvoie à au moins une étape du scénario par cette table ; chaque étape
du scénario est couverte par au moins une fonctionnalité livrée.

Toutes les vérifications automatiques se relancent avec `python -m pytest -q`
(348 tests au 28/10, sans vrai modèle). Les vérifications avec le vrai modèle sont
consignées dans [Vérification de la démo](demo_verified.md) et [Mesures](mesures.md).

## Fonctionnalités abandonnées ou modifiées

| Élément | Prévu au départ | Ce qui a été fait | Raison | User stories concernées |
|---|---|---|---|---|
| **EV1** évaluation par LLM-juge (⭐⭐⭐, issue #29) | bonus de Matteo | **non livrée** | non commencée au 28/10 ; un juge LLM ajouterait un second appel de modèle par tour, sur une latence déjà de 20 à 60 s sur CPU. Le catalogue privilégie peu de fonctionnalités bien intégrées | aucune écrite |
| **T5** sortie JSON imposée (⭐, issue #28) | bonus | **non livrée** | non commencée au 28/10 ; le besoin est en partie couvert : arguments d'outils validés par leur schéma JSON, note qui recopie un schéma refusée (`_text` dans `tools/patient_tools.py`) | aucune écrite |
| Budget d'un tour en 30 s | critère de choix du modèle (bench du 05/10) | **abandonné** : 20 à 60 s mesurés selon le contexte | aucun modèle fiable ne le tient sur un CPU portable ; le scénario vise des vérifications ponctuelles, pas une conversation rapide ([Scénario](scenario.md#le-scenario-est-il-realiste-avec-un-modele-local)) | B1 « Voir la réponse s'écrire » |
| Contrat d'interfaces v1 | `GuardResult.mapping` sans état | **remplacé** par la v2 : un `PIIVault` par session, frontière unique dans le pipeline | la v1 ne permettait ni la recherche patient en clair, ni la ré-identification des arguments d'outils, ni des pseudonymes stables d'un tour à l'autre | EV2 « Ne jamais envoyer l'identité » |
| Règles des garde-fous écrites dans le code | EV2 | **rendues réglables** dans `[guardrails]` (28/10) | le catalogue demande des règles configurables ; un contournement trouvé en test (« Oublie ce qu'on t'a dit… ») se bloque désormais par la configuration | EV2 « Adapter les règles au cabinet » |
| Un seul serveur MCP, le nôtre | T1 | **étendu** aux serveurs tiers déclarés dans `[[mcp.servers]]` (28/10) | T1 doit fonctionner avec un serveur MCP existant, pas seulement le nôtre | T1 « Brancher un serveur MCP existant » |
| A3 sur `add_patient_note` seul | un outil dangereux | **étendu** à `add_patient_entry` et `remove_patient_entry` | toute écriture dans un dossier doit passer par le médecin | A3 « Valider une écriture » |
| Recherche documentaire à chaque question | R1 | **modifiée** : mode `auto` (21/10) | une question sur le dossier seul n'a pas besoin de notice : contexte réduit de 2 989 à 613 caractères | R2 « Limiter les documents recherchés » |
| `SessionStore.list()` | contrat v2 | **renommé** `list_sessions()` | en Python 3.14, l'annotation `list[str]` désignait la méthode elle-même | M1 « Reprendre une session » |
| Interface web | chat, tokens, modèle, sessions, outils, confirmation | **étendue** : prompt exact, réglages à chaud, filtres documentaires | montrer ce que le modèle reçoit, sans terminal | X1 « Voir ce que le modèle a reçu » |

## Historique des user stories

| Date | Commit | Ajout |
|---|---|---|
| 05/10 | `dd5e9c7` | gabarit et répartition des fonctionnalités par membre (B1, X1, A3, EV3 / M1, M3, R1, R2 / T1, EV1, EV2) |
| 13/10 | `14cc95c` | M1 ×2, M3 ×2, R1 ×2 ; M1 « Profil médecin » et les deux R1 sont marquées « à implémenter » (code livré le 23/10 : `5812df9`, `37e8f47`, `22868b6`) |
| 14/10 | `855b0f5` | passage au français |
| 23/10 | `7962388` | M1 ×2, R2 ×2 ; statuts « livré » mis à jour |
| 28/10 | branche `feat/docs-mkdocs` | B1, X1, A3, EV3, T1, EV2, rédigées après leur code ; T1 « Brancher un serveur MCP existant » et EV2 « Adapter les règles au cabinet », rédigées avec leur code |
