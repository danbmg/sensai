# Traçabilité

Comment chaque fonctionnalité livrée se rattache à une user story, chaque user story à une
étape du [scénario d'usage](scenario.md) (**P** : préparation du poste ; **S0** à **S5** :
la consultation), et où la vérifier.

## Fonctionnalité → user stories → scénario

| Fonctionnalité | User stories ([liste](user_stories.md)) | Étape | Code | Vérification |
|---|---|---|---|---|
| **B1** CLI | Voir la réponse s'écrire · Garder le fil · Comprendre une panne · Changer de modèle | P, S0 | `sensai/cli.py`, `sensai/core/ollama_client.py`, `sensai/core/config.py` | `tests/core/test_cli.py`, `test_ollama_client.py`, `test_config.py` |
| **M1** sessions et profils | Reprendre une session · Profil médecin · Conversations séparées · Choisir un profil | S0 | `sensai/memory/sessions.py`, `profiles.py` | `tests/memory/test_profiles.py`, `test_storage.py` |
| **M3** dossiers SQLite | Consulter un dossier · Mettre à jour un dossier | S2, S4 | `sensai/memory/patients.py`, `context.py` | `tests/memory/test_storage.py`, `tests/tools/test_patient_tools.py` |
| **T1** outils et MCP | Consulter par un outil · Serveur MCP · Brancher un serveur existant | P, S4 | `sensai/tools/` | `tests/tools/test_patient_tools.py`, `test_third_party_mcp.py`, `tests/test_integration.py` (vrai serveur MCP) |
| **R1** RAG | Rechercher dans les notices · Identifier les sources | S3 | `sensai/rag/documents.py`, `embeddings.py`, `store.py`, `retrieval.py` | `tests/rag/` |
| **R2** RAG avancé | Limiter les documents · Écarter les extraits peu pertinents | S3 | `sensai/rag/retrieval.py`, `routing.py` | `tests/rag/test_retrieval.py`, `test_context.py` |
| **A3** validation humaine | Valider une écriture · Valider depuis le web | S4 | `sensai/core/pipeline.py` (`_run_tool`), `sensai/web/confirmations.py` | `tests/core/test_pipeline.py`, `tests/web/test_api.py`, `test_live.py` |
| **EV2** garde-fous | Ne jamais envoyer l'identité · Bloquer et masquer · Adapter les règles | P, S1 | `sensai/guardrails/`, frontière dans `sensai/core/pipeline.py` | `tests/guardrails/` (dont `test_settings.py`), test de frontière dans `tests/core/test_pipeline.py` |
| **EV3** logs et métriques | Garder une trace · Suivre les performances | S5 | `sensai/obs/` | `tests/obs/test_obs.py` |
| **X1** web | Consulter depuis le navigateur · Choisir patient, profil, modèle · Voir ce que le modèle a reçu | S0, S1 | `sensai/web/` | `tests/web/` (faux serveur Ollama) |

Chaque fonctionnalité livrée a au moins deux user stories, et chaque étape du scénario est
couverte par au moins une fonctionnalité livrée.

## User story → étape → vérification

Les 27 user stories, chacune avec son rôle ([rôles](scenario.md#les-roles-autour-du-medecin)),
son étape du scénario et les tests qui vérifient ses critères d'acceptation.

| Fonctionnalité | User story | Rôle | Étape | Tests |
|---|---|---|---|---|
| B1 | Voir la réponse s'écrire | médecin | S0 | `test_cli.py` : `test_prints_streamed_answer`, `test_empty_input_ignored`, `test_ctrl_c_during_generation_drops_turn_and_keeps_session` |
| B1 | Garder le fil de la consultation | médecin | S0 | `test_cli.py` : `test_previous_turns_sent_to_model`, `test_reset_clears_history_but_keeps_system_prompt`, `test_usage_line_after_answer` ; `test_pipeline.py` : `test_only_last_history_turns_are_sent_but_all_are_stored` |
| B1 | Comprendre une panne sans trace technique | médecin | S0 | `test_cli.py` : `test_ollama_down_at_startup_exits_with_message`, `test_missing_model_suggests_pull`, `test_model_without_tools_refused`, `test_thinking_model_warns_but_runs` |
| B1 | Changer de modèle sans toucher au code | responsable informatique | P | `test_cli.py` : `test_model_flag_overrides_config`, `test_uses_config_file` ; `test_config.py` : `test_project_config_is_valid_and_avoids_thinking_tag` |
| X1 | Consulter depuis le navigateur | médecin | S0 | `test_api.py` : `test_chat_streams_events_and_keeps_pii_on_the_clear_side`, `test_static_pages_are_served` |
| X1 | Choisir le patient, le profil et le modèle | médecin | S0 | `test_api.py` : `test_models_relays_ollama_tags`, `test_config_changes_parameters_live`, `test_config_refuses_invalid_changes`, `test_sessions_are_created_listed_and_reloaded` |
| X1 | Voir ce que le modèle a reçu | médecin | S1 | `test_runtime.py` : `test_ask_reveals_for_display_and_records_the_prompt` ; `test_cli.py` : `test_prompt_command_shows_exact_pseudonymized_prompt` |
| A3 | Valider une écriture dans le dossier | médecin | S4 | `test_pipeline.py` : `test_dangerous_tool_emits_confirm_before_asking`, `test_refused_tool_not_called_and_model_not_relaunched` ; `test_integration.py` : `test_pipeline_patient_note_confirmation_and_persistence` |
| A3 | Valider depuis la page web | médecin | S4 | `test_live.py` : `test_doctor_decides_in_the_browser`, `test_no_answer_before_timeout_means_refused` ; `test_streaming.py` : `test_confirmation_waits_for_the_decision_and_times_out` |
| EV3 | Garder une trace de chaque tour, sans données patient | responsable du cabinet | S5 | `test_obs.py` : `test_logger_writes_one_line_per_turn`, `test_logger_failure_is_reported_not_raised` ; `test_pipeline.py` : `test_pii_never_leaves_the_clear_side`, `test_failing_log_hook_does_not_break_the_turn` |
| EV3 | Suivre les performances | responsable du cabinet | S5 | `test_obs.py` : `test_summary_separates_errors_from_refusals_and_shows_drift`, `test_render_and_command_line` ; `test_api.py` : `test_metrics_summarize_logged_turns` |
| M1 | Reprendre une session | médecin | S0 | `test_storage.py` : `test_session_restores_history_tool_calls_and_pii_map`, `test_patient_and_session_survive_a_new_process` ; `test_integration.py` : `test_resume_cli_session_and_manual_note` |
| M1 | Profil médecin | médecin | S0 | `test_profiles.py` : `test_profile_survives_restart_and_is_injected_without_a_patient` ; `test_cli.py` : `test_reset_reloads_modified_profile_at_next_conversation` |
| M1 | Garder les conversations séparées | médecin | S0 | `test_cli.py` : `test_restart_restores_patient_and_profile_and_rejects_mixed_patient`, `test_session_switch_restores_associated_patient` ; `test_runtime.py` : `test_a_session_keeps_its_patient_and_profile` |
| M1 | Choisir un profil médecin | médecin | S0 | `test_profiles.py` : `test_default_profile_preserves_preferences_and_unknown_profile_is_explicit`, `test_profile_management_command` |
| M3 | Consulter un dossier | médecin | S2 | `test_storage.py` : `test_crud_survives_reopening`, `test_homonyms_require_id_and_partial_name_cannot_modify_record`, `test_exact_name_resolves_to_id` ; `test_integration.py` : `test_context_reads_current_patient_without_exposing_others` |
| M3 | Mettre à jour un dossier | médecin | S4 | `test_storage.py` : `test_concurrent_note_additions_are_preserved`, `test_validation_rejects_invalid_updates_without_modifying_record` ; `test_runtime.py` : `test_model_updates_record_after_doctor_approval` |
| R1 | Rechercher dans les notices | médecin | S3 | `test_documents.py` : `test_chunk_boundaries_overlap_and_page_references` ; `test_embeddings.py` : `test_direct_embed_api_batching_prefixes_and_cpu_limits` ; `test_context.py` : `test_pipeline_injects_profile_and_sources_but_embeds_only_masked_question` |
| R1 | Identifier les sources | médecin | S3 | `test_retrieval.py` : `test_context_budget_and_source_references_are_consistent` ; `test_context.py` : `test_no_results_or_embedding_failure_clears_sources_without_losing_patient` ; `test_cli.py` : `test_document_commands_and_source_persistence` |
| R2 | Limiter les documents recherchés | médecin | S3 | `test_retrieval.py` : `test_metadata_filters_apply_before_embedding_and_ranking`, `test_empty_index_does_not_call_embedding_server` |
| R2 | Écarter les extraits peu pertinents | médecin | S3 | `test_retrieval.py` : `test_cosine_search_reranking_and_relevance_threshold`, `test_context_budget_and_source_references_are_consistent` |
| T1 | Laisser l'assistant consulter le dossier par un outil | médecin | S4 | `test_patient_tools.py` : `test_agent_tools_read_search_and_update` ; `test_pipeline.py` : `test_tool_schemas_sent_to_model`, `test_safe_tool_runs_without_confirmation_then_model_relaunched` ; `test_integration.py` : `test_malformed_tool_and_storage_failure_do_not_crash` |
| T1 | Isoler les outils patients dans un serveur MCP | responsable informatique | P, S4 | `test_integration.py` : `test_pipeline_patient_note_confirmation_and_persistence` (variante `mcp-stdio`, vrai serveur MCP) |
| T1 | Brancher un serveur MCP existant | responsable informatique | P | `test_third_party_mcp.py` : `test_third_party_tools_are_prefixed_filtered_and_callable`, `test_third_party_write_tool_can_require_the_doctor`, `test_unavailable_third_party_server_is_skipped` |
| EV2 | Ne jamais envoyer l'identité d'un patient au modèle | médecin | S1 | `test_pipeline.py` : `test_pii_never_leaves_the_clear_side` ; `test_integration.py` : `test_patient_aliases_dates_addresses_and_phone_stream` ; `test_pii_vault.py` : `test_export_and_restore_session` |
| EV2 | Bloquer les détournements et masquer les fuites | médecin | S1 | `test_input_guardrail.py` : `test_prompt_injection`, `test_sensitive_extraction`, `test_blocked_request_never_calls_ollama` ; `test_output_guardrail.py` : `test_phone_is_masked`, `test_nir_is_masked` |
| EV2 | Adapter les règles au cabinet | responsable informatique | P | `test_settings.py` : `test_custom_rule_shows_its_own_reason`, `test_families_and_output_types_can_be_narrowed`, `test_invalid_rules_are_refused`, `test_project_config_blocks_the_bypass_found_in_testing` |

Chaque étape du scénario est servie par au moins une user story :

| Étape | User stories |
|---|---|
| P — préparation du poste | 4 (B1, T1 ×2, EV2) |
| S0 — ouvrir la consultation, poser la question | 9 (B1 ×3, X1 ×2, M1 ×4) |
| S1 — filtres et pseudonymisation | 3 (X1, EV2 ×2) |
| S2 — le dossier | 1 (M3) |
| S3 — la notice | 4 (R1 ×2, R2 ×2) |
| S4 — la note validée | 5 (A3 ×2, M3, T1 ×2) |
| S5 — journal et latence | 2 (EV3 ×2) |

T1 « Isoler les outils patients dans un serveur MCP » compte pour P et pour S4 : 28 rattachements
pour 27 user stories.

Toutes les vérifications automatiques se relancent avec `python -m pytest -q`
(348 tests, verts au 03/11, sans vrai modèle). Les vérifications avec le vrai modèle sont
consignées dans [Vérification de la démo](demo_verified.md) et [Mesures](mesures.md).

## Fonctionnalités abandonnées ou modifiées

| Élément | Prévu au départ | Ce qui a été fait | Raison | User stories concernées |
|---|---|---|---|---|
| **EV1** évaluation par LLM-juge (issue #29) | prévue (Matteo) | **non livrée** | non commencée au 28/10 ; un juge LLM ajouterait un second appel de modèle par tour, sur une latence déjà de 20 à 60 s sur CPU | aucune écrite ; le besoin est décrit dans l'issue #29 |
| **T5** sortie JSON imposée (issue #28) | prévue | **non livrée** | non commencée au 28/10 ; le besoin est en partie couvert : arguments d'outils validés par leur schéma JSON, note qui recopie un schéma refusée (`_text` dans `tools/patient_tools.py`) | aucune écrite ; le besoin est décrit dans l'issue #28 |
| Filtre « hors périmètre médical » et création / suppression de patient par la conversation | ajoutés le 03/11 | **retirés le jour même** (commit `f3d8371`) | le filtre refusait toute question sans mot médical : « Je m'appelle Paul. », la calculatrice, les questions d'heure pour le serveur MCP `time` ; les deux nouveaux outils arrivaient sans user story ni traçabilité | B1 « Garder le fil de la consultation », T1 « Laisser l'assistant consulter le dossier par un outil », T1 « Brancher un serveur MCP existant » |
| Budget d'un tour en 30 s | critère de choix du modèle (bench du 05/10) | **abandonné** : 20 à 60 s mesurés selon le contexte | aucun modèle fiable ne le tient sur un CPU portable ; le scénario vise des vérifications ponctuelles, pas une conversation rapide ([Scénario](scenario.md#le-scenario-est-il-realiste-avec-un-modele-local)) | B1 « Voir la réponse s'écrire » |
| Contrat d'interfaces v1 | `GuardResult.mapping` sans état | **remplacé** par la v2 : un `PIIVault` par session, frontière unique dans le pipeline | la v1 ne permettait ni la recherche patient en clair, ni la ré-identification des arguments d'outils, ni des pseudonymes stables d'un tour à l'autre | EV2 « Ne jamais envoyer l'identité » |
| Règles des garde-fous écrites dans le code | EV2 | **rendues réglables** dans `[guardrails]` (28/10) | un contournement trouvé en test (« Oublie ce qu'on t'a dit… ») doit pouvoir se bloquer sans changer le code : c'est désormais une règle de configuration | EV2 « Adapter les règles au cabinet » |
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
| 03/11 | — | étape du scénario ajoutée à chaque story ; rôles et préparation du poste (P) explicités dans le [scénario](scenario.md#les-roles-autour-du-medecin) |
