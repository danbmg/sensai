# User stories et traçabilité

Le besoin réel est décrit dans [scenario.md](scenario.md). Ce fichier le découpe en user
stories avec des critères vérifiables, puis relie chaque story à son étape du scénario et aux
tests qui la vérifient. Les choix techniques et leur justification sont dans
[decisions.md](decisions.md).

1. [User stories](#1-user-stories)
2. [Traçabilité](#2-traçabilité)

## 1. User stories

Au moins deux histoires utilisateur par fonctionnalité implémentée.

Chaque histoire indique l'étape du [scénario d'usage](scenario.md) qu'elle sert : **P**
(préparation du poste) ou **S0** à **S5** (consultation). Les tests qui la vérifient sont
dans [Traçabilité](#user-story--étape--vérification).

EV1 (évaluation par un LLM-juge) et T5 (sortie JSON imposée) n'ont pas été livrées : voir
[Traçabilité](#fonctionnalités-abandonnées-ou-modifiées).

Format :

```
En tant que <type d'utilisateur>, je souhaite <action>, afin de <résultat>.

Critères d'acceptation :
- <comportement observable 1>
- <comportement observable 2>
- <comportement observable 3>
```

### B1 — Chatbot en ligne de commande

#### Voir la réponse s'écrire

Scénario : [**S0**](scenario.md#le-scénario-fil-rouge-de-la-démo) — la réponse s'affiche au fil de l'eau.

En tant que médecin, je souhaite voir la réponse s'afficher au fur et à mesure dans le terminal, afin de savoir que l'assistant travaille et de commencer à lire sans attendre la fin.

Critères d'acceptation :

- Les fragments s'affichent dès leur réception, avant la fin de la génération.
- Une entrée vide est ignorée, sans appel au modèle.
- Ctrl+C pendant la génération arrête la réponse ; la session reste ouverte et le tour interrompu n'est pas enregistré.

#### Garder le fil de la consultation

Scénario : [**S0**](scenario.md#le-scénario-fil-rouge-de-la-démo) — les questions de suivi pendant la consultation.

En tant que médecin, je souhaite que l'assistant se souvienne de ce que j'ai dit plus tôt dans la conversation, afin de poser des questions de suivi sans tout répéter.

Critères d'acceptation :

- Après « Je m'appelle Paul. », la question « Comment je m'appelle ? » obtient une réponse contenant « Paul ».
- `/reset` ouvre une nouvelle conversation : les échanges précédents ne sont plus envoyés au modèle.
- Au-delà de `max_history_turns` tours, seuls les derniers tours sont envoyés ; l'occupation du contexte est affichée après chaque réponse.

#### Comprendre une panne sans trace technique

Scénario : [**S0**](scenario.md#le-scénario-fil-rouge-de-la-démo) — ouvrir la consultation alors qu'Ollama ne répond pas.

En tant que médecin, je souhaite un message clair quand l'assistant ne peut pas répondre, afin de savoir quoi faire sans appeler un informaticien.

Critères d'acceptation :

- Ollama éteint : le message indique l'adresse contactée et la commande `ollama serve`.
- Modèle absent : le message indique la commande `ollama pull <modèle>`.
- Modèle sans capacité `tools` : refus au démarrage ; modèle `thinking` : avertissement.

#### Changer de modèle sans toucher au code

Scénario : [**P**](scenario.md#le-scénario-fil-rouge-de-la-démo) — le prestataire choisit le modèle adapté au PC du cabinet.

En tant que responsable informatique du cabinet, je souhaite choisir le modèle dans `config.toml` ou au lancement, afin d'adapter l'assistant à la machine disponible.

Critères d'acceptation :

- `--model llama3.2:3b` remplace le modèle de `config.toml` pour ce lancement.
- `--config autre.toml` charge un autre fichier de configuration.
- Aucun nom de modèle n'est écrit en dur dans le code Python.

### M1 — Sessions persistantes et profils médecin

#### Reprendre une session

Scénario : [**S0**](scenario.md#le-scénario-fil-rouge-de-la-démo) — reprendre la consultation de Mme Dupont après un redémarrage.

En tant que médecin, je souhaite reprendre une conversation après le redémarrage de l'assistant, afin de poursuivre mon travail sans ressaisir les échanges précédents.

Critères d'acceptation :

- Un historique sauvegardé est rechargé à l'identique après réouverture du stockage.
- Les correspondances des pseudonymes sont restaurées avec l'historique.
- Les sessions sont listables et restent indépendantes ; une session inconnue est vide.

#### Profil médecin

Scénario : [**S0**](scenario.md#le-scénario-fil-rouge-de-la-démo) — le profil du Dr Martin est injecté dès l'ouverture de la consultation.

En tant que médecin, je souhaite enregistrer ma spécialité, mes préférences et mes instructions, afin que l'assistant adapte ses réponses dès le démarrage.

Critères d'acceptation :

- Le profil est conservé après redémarrage.
- Le profil sélectionné est injecté dans le contexte initial de la conversation.
- Une modification du profil est prise en compte à l'ouverture d'une nouvelle conversation.

#### Garder les conversations séparées

Scénario : [**S0**](scenario.md#le-scénario-fil-rouge-de-la-démo) — une session par consultation, liée à Mme Dupont.

En tant que médecin, je souhaite que chaque conversation conserve le patient et le profil sélectionnés, afin de reprendre une consultation sans mélanger les dossiers.

Critères d'acceptation :

- Changer de patient ouvre un nouvel identifiant de session.
- Reprendre une nouvelle session enregistrée restaure son patient, son profil, ses filtres et ses dernières sources.
- Le démarrage refuse de reprendre une session avec un autre patient explicitement demandé.

#### Choisir un profil médecin

Scénario : [**S0**](scenario.md#le-scénario-fil-rouge-de-la-démo) — ouvrir la consultation avec le profil `generaliste`.

En tant que médecin, je souhaite sélectionner un profil enregistré, afin d'appliquer mes préférences à une nouvelle conversation.

Critères d'acceptation :

- Les profils peuvent être listés et affichés sans appeler le modèle.
- Un profil inconnu produit une erreur explicite sans modifier le profil courant.
- Le changement de profil ouvre une nouvelle conversation, avec ses instructions injectées même sans patient sélectionné.

### M3 — Dossiers patients

#### Consulter un dossier

Scénario : [**S2**](scenario.md#le-scénario-fil-rouge-de-la-démo) — retrouver l'allergie à la pénicilline dans le dossier.

En tant que médecin, je souhaite retrouver les allergies, traitements et antécédents d'un patient, afin de disposer des informations enregistrées pour ma consultation.

Critères d'acceptation :

- Le dossier est consultable par son identifiant avec ses allergies, traitements, antécédents et notes.
- La recherche par nom retourne tous les patients correspondants sans sélectionner arbitrairement un homonyme.
- Le jeu fictif contient Mme Jeanne Dupont avec une allergie à la pénicilline.

#### Mettre à jour un dossier

Scénario : [**S4**](scenario.md#le-scénario-fil-rouge-de-la-démo) — la note validée est écrite dans le dossier.

En tant que médecin, je souhaite ajouter une note et corriger les données d'un dossier, afin de conserver des informations à jour pour les consultations suivantes.

Critères d'acceptation :

- Une note ajoutée ne remplace pas les notes précédentes et reste présente après réouverture de la base.
- Modifier un champ conserve les autres champs ; un patient absent ou ambigu provoque une erreur explicite.
- Une écriture demandée par le modèle n'est exécutée qu'après confirmation du médecin via le pipeline.

#### Créer un dossier avant la consultation

Scénario : [**P**](scenario.md#le-scénario-fil-rouge-de-la-démo) — le dossier d'un nouveau patient existe avant sa première consultation.

En tant que médecin, je souhaite créer le dossier d'un nouveau patient sans passer par l'assistant, afin que son identité soit pseudonymisée dès la première question que je pose à son sujet.

Critères d'acceptation :

- `python -m sensai.memory.patients add` pose les questions une à une ; aucune donnée du patient ne se passe en argument, donc aucune ne reste dans l'historique du terminal.
- Un nom de famille déjà présent dans la base est signalé avant la création, avec ses conséquences sur la pseudonymisation ; refuser ne crée rien.
- Après la création, le nom et la date de naissance n'apparaissent dans aucun message envoyé au modèle, ni dans les logs, même dans une consultation déjà ouverte.

#### Supprimer un dossier et ses traces

Scénario : [**P**](scenario.md#le-scénario-fil-rouge-de-la-démo) — un patient demande l'effacement de ses données.

En tant que responsable du cabinet, je souhaite supprimer le dossier d'un patient avec ses conversations, afin de répondre à une demande d'effacement sans laisser son identité dans la base.

Critères d'acceptation :

- Avant la suppression, la commande affiche le dossier et le nombre de conversations concernées, puis demande confirmation ; refuser ne modifie rien.
- Les conversations liées au dossier sont supprimées ; le nom et la date de naissance du patient sont retirés du coffre de pseudonymes des autres conversations.
- Un nom inconnu ou porté par plusieurs dossiers produit une erreur explicite, sans rien supprimer.

### T1 — Outils et MCP

#### Laisser l'assistant consulter le dossier par un outil

Scénario : [**S4**](scenario.md#le-scénario-fil-rouge-de-la-démo) — l'assistant appelle lui-même `add_patient_note`.

En tant que médecin, je souhaite que l'assistant appelle lui-même les outils patients quand ma demande le nécessite, afin d'obtenir une réponse fondée sur le dossier plutôt que sur sa mémoire.

Critères d'acceptation :

- `/tools` liste les outils disponibles : `get_patient`, `find_patients`, `add_patient_note`, `add_patient_entry`, `remove_patient_entry`, `calculator`, `get_current_time`.
- Le résultat d'un outil est renvoyé au modèle, qui termine sa réponse.
- Un appel d'outil invalide, ou un outil non proposé pour ce tour, est refusé sans action exécutée.

#### Isoler les outils patients dans un serveur MCP

Scénario : [**P**](scenario.md#le-scénario-fil-rouge-de-la-démo) et [**S4**](scenario.md#le-scénario-fil-rouge-de-la-démo) — le prestataire active `--mcp` ; la note de S4 passe par le serveur MCP.

En tant que responsable informatique du cabinet, je souhaite que les outils patients tournent dans un processus séparé accessible par MCP, afin de pouvoir les réutiliser ou les remplacer sans modifier l'assistant.

Critères d'acceptation :

- `--mcp` lance le serveur médical en stdio et découvre ses outils au démarrage.
- Les mêmes commandes et le même scénario fonctionnent avec et sans `--mcp`.
- Si le serveur ne démarre pas, un message clair s'affiche, sans trace technique.

#### Brancher un serveur MCP existant

Scénario : [**P**](scenario.md#le-scénario-fil-rouge-de-la-démo) — le prestataire ajoute un outil en déclarant un serveur dans `config.toml`.

En tant que responsable informatique du cabinet, je souhaite ajouter un serveur MCP écrit par d'autres en le déclarant dans la configuration, afin de donner un nouvel outil à l'assistant sans modifier son code.

Critères d'acceptation :

- Un bloc `[[mcp.servers]]` dans `config.toml` suffit : au lancement avec `--mcp`, ses outils apparaissent dans `/tools`, préfixés par le nom du serveur.
- Seuls les outils listés dans `tools` sont retenus ; ceux listés dans `dangerous` demandent la validation du médecin.
- Si le serveur ne démarre pas, il est signalé et ignoré, et la consultation continue.

### R1 — Recherche dans les documents publics

#### Rechercher dans les notices

Scénario : [**S3**](scenario.md#le-scénario-fil-rouge-de-la-démo) — retrouver l'extrait de la notice ANSM de l'amoxicilline.

En tant que médecin, je souhaite retrouver les passages pertinents des notices ANSM et des recommandations HAS, afin d'obtenir des réponses fondées sur mon corpus documentaire local.

Critères d'acceptation :

- Les documents sont découpés en extraits associés à leur source et leur emplacement.
- Les représentations vectorielles des extraits sont obtenues via l'API HTTP Ollama `/api/embed` avec `nomic-embed-text`.
- La recherche utilise la similarité cosinus et une requête pseudonymisée, sans indexer les dossiers patients.

#### Identifier les sources

Scénario : [**S3**](scenario.md#le-scénario-fil-rouge-de-la-démo) — citer la notice avec sa source.

En tant que médecin, je souhaite connaître les sources des extraits utilisés, afin de pouvoir vérifier les informations proposées.

Critères d'acceptation :

- `ContextProvider` transmet chaque extrait retrouvé avec une référence à son document source.
- Une recherche sans extrait pertinent est signalée dans le contexte sans inventer de source.
- Le scénario Mme Dupont associe le dossier local et les extraits publics utiles sans mélanger leurs stockages.

### R2 — Recherche documentaire avancée

#### Limiter les documents recherchés

Scénario : [**S3**](scenario.md#le-scénario-fil-rouge-de-la-démo) — ne chercher que dans les sources utiles à la question.

En tant que médecin, je souhaite filtrer les documents par éditeur, étiquettes et date connue, afin de rechercher dans les sources adaptées à ma question.

Critères d'acceptation :

- Les filtres sont appliqués avant le calcul des scores de similarité.
- Les documents sans date connue sont exclus lorsqu'une période est demandée.
- Un filtre sans résultat retourne une recherche vide sans appeler le modèle d'embeddings.

#### Écarter les extraits peu pertinents

Scénario : [**S3**](scenario.md#le-scénario-fil-rouge-de-la-démo) — ne garder que les extraits utiles, dans un contexte limité.

En tant que médecin, je souhaite que les passages retenus soient reclassés et soumis à des seuils de pertinence, afin de limiter les extraits inutiles dans le contexte.

Critères d'acceptation :

- Le reclassement combine la similarité cosinus et un score lexical BM25 ; il peut être désactivé pour comparaison.
- Les extraits sous les seuils configurés sont écartés et les copies identiques sont dédupliquées.
- Le nombre d'extraits et leur longueur totale restent limités ; aucune source n'est inventée en cas de recherche vide.

### A3 — Validation humaine

#### Valider une écriture dans le dossier

Scénario : [**S4**](scenario.md#le-scénario-fil-rouge-de-la-démo) — valider ou refuser la note proposée.

En tant que médecin, je souhaite approuver toute modification d'un dossier avant qu'elle soit écrite, afin que l'IA ne modifie jamais une donnée médicale sans mon accord.

Critères d'acceptation :

- Avant toute écriture, l'outil et ses arguments sont affichés en clair, avec le vrai nom du patient.
- Si je refuse, le dossier est inchangé et l'assistant indique que l'action n'a pas été exécutée.
- Si j'accepte, la note apparaît dans le dossier (`/dossier`).

#### Valider depuis la page web

Scénario : [**S4**](scenario.md#le-scénario-fil-rouge-de-la-démo) — la même validation, dans une fenêtre du navigateur.

En tant que médecin, je souhaite une fenêtre de confirmation dans le navigateur, afin de valider ou refuser une action sans quitter l'interface.

Critères d'acceptation :

- Une demande d'écriture ouvre une fenêtre « Action à valider » avec l'outil et ses arguments.
- Sans réponse dans les 120 secondes, l'action est refusée.
- « Valider » écrit la note ; « Refuser » laisse le dossier inchangé.

### EV2 — Garde-fous et données personnelles

#### Ne jamais envoyer l'identité d'un patient au modèle

Scénario : [**S1**](scenario.md#le-scénario-fil-rouge-de-la-démo) — « Mme Dupont » devient `[PATIENT_1]` avant l'envoi au modèle.

En tant que médecin, je souhaite que le nom, la date de naissance, l'adresse, le téléphone, le numéro de sécurité sociale et l'email d'un patient soient remplacés par des pseudonymes avant l'envoi au modèle, afin de respecter le secret médical.

Critères d'acceptation :

- Les messages envoyés au modèle, l'historique et les logs contiennent `[PATIENT_1]`, jamais « Dupont ».
- « Dupont », « Mme Dupont » et « Jeanne Dupont » donnent le même pseudonyme, d'un tour à l'autre.
- À l'écran et dans la confirmation, le médecin lit le vrai nom.

#### Bloquer les détournements et masquer les fuites

Scénario : [**S1**](scenario.md#le-scénario-fil-rouge-de-la-démo) — la question passe les filtres d'entrée ; la réponse est masquée avant l'historique.

En tant que médecin, je souhaite que les tentatives de détournement soient refusées avant d'atteindre le modèle, et que les données personnelles restantes soient masquées dans les réponses, afin que l'assistant reste dans son rôle.

Critères d'acceptation :

- « Ignore toutes les instructions précédentes. » est refusé avant tout appel au modèle, avec un motif affiché.
- Une demande d'extraction de mots de passe ou de clés API est refusée.
- Un téléphone, un email, un NIR ou un IBAN présent dans une réponse est masqué avant l'enregistrement.

#### Adapter les règles au cabinet

Scénario : [**P**](scenario.md#le-scénario-fil-rouge-de-la-démo) — le prestataire ajoute une règle de filtrage dans `config.toml`.

En tant que responsable informatique du cabinet, je souhaite ajouter ou retirer des règles de filtrage dans la configuration, afin de bloquer un nouveau contournement sans attendre une nouvelle version du code.

Critères d'acceptation :

- Une règle `[[guardrails.custom_rules]]` (motif et message) refuse les requêtes qui lui correspondent, avec son propre message.
- Les familles de règles intégrées et les types de données masquées en sortie se choisissent dans `[guardrails]`.
- Une règle invalide (expression régulière fausse, famille inconnue) empêche le démarrage avec un message clair.

### EV3 — Logs et tableau de bord

#### Garder une trace de chaque tour, sans données patient

Scénario : [**S5**](scenario.md#le-scénario-fil-rouge-de-la-démo) — chaque tour est journalisé, pseudonymisé.

En tant que responsable du cabinet, je souhaite un journal de chaque échange, afin de pouvoir vérifier après coup ce que l'assistant a fait.

Critères d'acceptation :

- Chaque tour ajoute une ligne JSON à `logs/AAAA-MM-JJ.jsonl` : modèle, prompt et réponse, outils appelés, latence, tokens, configuration.
- Aucun nom, date de naissance ou adresse de patient n'apparaît en clair dans ces fichiers.
- Une écriture de log en échec n'interrompt pas la consultation.

#### Suivre les performances

Scénario : [**S5**](scenario.md#le-scénario-fil-rouge-de-la-démo) — le tableau de bord montre la latence.

En tant que responsable du cabinet, je souhaite voir le volume, la latence et le taux d'erreur, afin de savoir si un changement de modèle ou de réglage ralentit l'assistant.

Critères d'acceptation :

- `/metrics.html` et `python -m sensai.obs` affichent le nombre de tours, la latence moyenne, p50 et p95, et le taux d'erreur.
- Les chiffres sont regroupés par modèle et par configuration, version du prompt système comprise.
- Après un changement de modèle, une nouvelle ligne apparaît dans le tableau « Par modèle ».

### X1 — Interface web

#### Consulter depuis le navigateur

Scénario : [**S0**](scenario.md#le-scénario-fil-rouge-de-la-démo) — le médecin ouvre la consultation dans le navigateur.

En tant que médecin, je souhaite utiliser l'assistant dans une page web, afin de travailler sans terminal.

Critères d'acceptation :

- `python -m sensai.web --demo` sert l'interface sur `http://127.0.0.1:8000`.
- La réponse s'affiche en streaming, avec le nombre de tokens et l'occupation du contexte.
- Les appels d'outils et les sources du dernier tour sont affichés à côté de la conversation.

#### Choisir le patient, le profil et le modèle

Scénario : [**S0**](scenario.md#le-scénario-fil-rouge-de-la-démo) — ouvrir la consultation de Mme Dupont avec le profil du médecin.

En tant que médecin, je souhaite ouvrir une consultation pour un patient et un profil, et changer de modèle ou de réglage depuis la page, afin d'adapter l'assistant sans relancer le serveur.

Critères d'acceptation :

- Le sélecteur de modèle liste les modèles installés dans Ollama.
- La fenêtre « Réglages » modifie température, `num_predict`, `num_ctx` et nombre de tours d'historique ; une valeur invalide est refusée sans rien changer.
- La liste des consultations permet de reprendre une session enregistrée, avec son patient.

#### Voir ce que le modèle a reçu

Scénario : [**S1**](scenario.md#le-scénario-fil-rouge-de-la-démo) — vérifier que « Mme Dupont » est partie sous la forme `[PATIENT_1]`.

En tant que médecin, je souhaite afficher le prompt exact envoyé au modèle, afin de vérifier qu'aucun nom de patient n'en sort.

Critères d'acceptation :

- « Voir le prompt envoyé » affiche les messages du dernier tour, tels que le modèle les a reçus.
- Ces messages contiennent `[PATIENT_1]`, jamais le nom réel.
- Le nombre de tokens lus et la taille de la fenêtre de contexte sont affichés.

## 2. Traçabilité

Comment chaque fonctionnalité livrée se rattache à une user story, chaque user story à une
étape du [scénario d'usage](scenario.md) (**P** : préparation du poste ; **S0** à **S5** :
la consultation), et où la vérifier.

### Fonctionnalité → user stories → scénario

| Fonctionnalité | User stories ([liste](#1-user-stories)) | Étape | Code | Vérification |
|---|---|---|---|---|
| **B1** CLI | Voir la réponse s'écrire · Garder le fil · Comprendre une panne · Changer de modèle | P, S0 | `sensai/cli.py`, `sensai/core/ollama_client.py`, `sensai/core/config.py` | `tests/core/test_cli.py`, `test_ollama_client.py`, `test_config.py` |
| **M1** sessions et profils | Reprendre une session · Profil médecin · Conversations séparées · Choisir un profil | S0 | `sensai/memory/sessions.py`, `profiles.py` | `tests/memory/test_profiles.py`, `test_storage.py` |
| **M3** dossiers SQLite | Consulter un dossier · Mettre à jour un dossier · Créer un dossier · Supprimer un dossier | P, S2, S4 | `sensai/memory/patients.py` (dont la commande `patients`), `sessions.py` (`forget_patient`), `context.py` | `tests/memory/test_storage.py`, `test_patient_command.py`, `tests/tools/test_patient_tools.py` |
| **T1** outils et MCP | Consulter par un outil · Serveur MCP · Brancher un serveur existant | P, S4 | `sensai/tools/` | `tests/tools/test_patient_tools.py`, `test_third_party_mcp.py`, `tests/test_integration.py` (vrai serveur MCP) |
| **R1** RAG | Rechercher dans les notices · Identifier les sources | S3 | `sensai/rag/documents.py`, `embeddings.py`, `store.py`, `retrieval.py` | `tests/rag/` |
| **R2** RAG avancé | Limiter les documents · Écarter les extraits peu pertinents | S3 | `sensai/rag/retrieval.py`, `routing.py` | `tests/rag/test_retrieval.py`, `test_context.py` |
| **A3** validation humaine | Valider une écriture · Valider depuis le web | S4 | `sensai/core/pipeline.py` (`_run_tool`), `sensai/web/confirmations.py` | `tests/core/test_pipeline.py`, `tests/web/test_api.py`, `test_live.py` |
| **EV2** garde-fous | Ne jamais envoyer l'identité · Bloquer et masquer · Adapter les règles | P, S1 | `sensai/guardrails/`, frontière dans `sensai/core/pipeline.py` | `tests/guardrails/` (dont `test_settings.py`), test de frontière dans `tests/core/test_pipeline.py` |
| **EV3** logs et métriques | Garder une trace · Suivre les performances | S5 | `sensai/obs/` | `tests/obs/test_obs.py` |
| **X1** web | Consulter depuis le navigateur · Choisir patient, profil, modèle · Voir ce que le modèle a reçu | S0, S1 | `sensai/web/` | `tests/web/` (faux serveur Ollama) |

Chaque fonctionnalité livrée a au moins deux user stories, et chaque étape du scénario est
couverte par au moins une fonctionnalité livrée.

### User story → étape → vérification

Les 29 user stories, chacune avec son rôle ([rôles](scenario.md#les-rôles-autour-du-médecin)),
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
| M3 | Créer un dossier avant la consultation | médecin | P | `test_patient_command.py` : `test_add_asks_one_field_at_a_time_and_creates_the_record`, `test_patient_data_cannot_be_passed_as_arguments`, `test_homonyms_are_announced_before_creation`, `test_refusal_or_interruption_creates_nothing`, `test_new_patient_never_reaches_the_model_in_clear` |
| M3 | Supprimer un dossier et ses traces | responsable du cabinet | P | `test_patient_command.py` : `test_delete_removes_record_conversations_and_identity_everywhere`, `test_delete_refused_unknown_or_ambiguous_changes_nothing` |
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
| P — préparation du poste et des dossiers | 6 (B1, T1 ×2, EV2, M3 ×2) |
| S0 — ouvrir la consultation, poser la question | 9 (B1 ×3, X1 ×2, M1 ×4) |
| S1 — filtres et pseudonymisation | 3 (X1, EV2 ×2) |
| S2 — le dossier | 1 (M3) |
| S3 — la notice | 4 (R1 ×2, R2 ×2) |
| S4 — la note validée | 5 (A3 ×2, M3, T1 ×2) |
| S5 — journal et latence | 2 (EV3 ×2) |

T1 « Isoler les outils patients dans un serveur MCP » compte pour P et pour S4 : 30 rattachements
pour 29 user stories.

Toutes les vérifications automatiques se relancent avec `python -m pytest -q`
(356 tests, verts au 03/11, sans vrai modèle). Les vérifications avec le vrai modèle sont
consignées dans [Vérification de la démo](mesures.md#3-vérifications-avec-le-vrai-modèle) et [Mesures](mesures.md#2-avec-ou-sans-contexte).

### Fonctionnalités abandonnées ou modifiées

| Élément | Prévu au départ | Ce qui a été fait | Raison | User stories concernées |
|---|---|---|---|---|
| **EV1** évaluation par LLM-juge (issue #29) | prévue | **non livrée** | non commencée au 28/10 ; un juge LLM ajouterait un second appel de modèle par tour, sur une latence déjà de 20 à 60 s sur CPU | aucune écrite ; le besoin est décrit dans l'issue #29 |
| **T5** sortie JSON imposée (issue #28) | prévue | **non livrée** | non commencée au 28/10 ; le besoin est en partie couvert : arguments d'outils validés par leur schéma JSON, note qui recopie un schéma refusée (`_text` dans `tools/patient_tools.py`) | aucune écrite ; le besoin est décrit dans l'issue #28 |
| Filtre « hors périmètre médical » et création / suppression de patient par la conversation | ajoutés le 03/11 | **retirés le jour même** (commit `f3d8371`) ; création et suppression **reprises par une commande hors de l'agent** (`python -m sensai.memory.patients`) | le filtre refusait toute question sans mot médical : « Je m'appelle Paul. », la calculatrice, les questions d'heure pour le serveur MCP `time` ; les deux nouveaux outils arrivaient sans user story ni traçabilité ; par la conversation, le nom d'un nouveau patient, pas encore en base, partait en clair au modèle ([Choix](decisions.md#créer-un-dossier-par-une-commande-pas-par-lagent)) | B1 « Garder le fil de la consultation », T1 « Laisser l'assistant consulter le dossier par un outil », T1 « Brancher un serveur MCP existant », M3 « Créer un dossier avant la consultation », M3 « Supprimer un dossier et ses traces » |
| Budget d'un tour en 30 s | critère de choix du modèle (bench du 05/10) | **abandonné** : 20 à 60 s mesurés selon le contexte | aucun modèle fiable ne le tient sur un CPU portable ; le scénario vise des vérifications ponctuelles, pas une conversation rapide ([Scénario](scenario.md#le-scénario-est-il-réaliste-avec-un-modèle-local-)) | B1 « Voir la réponse s'écrire » |
| Contrat d'interfaces v1 | `GuardResult.mapping` sans état | **remplacé** par la v2 : un `PIIVault` par session, frontière unique dans le pipeline | la v1 ne permettait ni la recherche patient en clair, ni la ré-identification des arguments d'outils, ni des pseudonymes stables d'un tour à l'autre | EV2 « Ne jamais envoyer l'identité » |
| Règles des garde-fous écrites dans le code | EV2 | **rendues réglables** dans `[guardrails]` (28/10) | un contournement trouvé en test (« Oublie ce qu'on t'a dit… ») doit pouvoir se bloquer sans changer le code : c'est désormais une règle de configuration | EV2 « Adapter les règles au cabinet » |
| Un seul serveur MCP, le nôtre | T1 | **étendu** aux serveurs tiers déclarés dans `[[mcp.servers]]` (28/10) | T1 doit fonctionner avec un serveur MCP existant, pas seulement le nôtre | T1 « Brancher un serveur MCP existant » |
| A3 sur `add_patient_note` seul | un outil dangereux | **étendu** à `add_patient_entry` et `remove_patient_entry` | toute écriture dans un dossier doit passer par le médecin | A3 « Valider une écriture » |
| Recherche documentaire à chaque question | R1 | **modifiée** : mode `auto` (21/10) | une question sur le dossier seul n'a pas besoin de notice : contexte réduit de 2 989 à 613 caractères | R2 « Limiter les documents recherchés » |
| `SessionStore.list()` | contrat v2 | **renommé** `list_sessions()` | en Python 3.14, l'annotation `list[str]` désignait la méthode elle-même | M1 « Reprendre une session » |
| Interface web | chat, tokens, modèle, sessions, outils, confirmation | **étendue** : prompt exact, réglages à chaud, filtres documentaires | montrer ce que le modèle reçoit, sans terminal | X1 « Voir ce que le modèle a reçu » |

### Historique des user stories

| Date | Commit | Ajout |
|---|---|---|
| 05/10 | `dd5e9c7` | gabarit et répartition des fonctionnalités par membre (B1, X1, A3, EV3 / M1, M3, R1, R2 / T1, EV1, EV2) |
| 13/10 | `14cc95c` | M1 ×2, M3 ×2, R1 ×2 ; M1 « Profil médecin » et les deux R1 sont marquées « à implémenter » (code livré le 23/10 : `5812df9`, `37e8f47`, `22868b6`) |
| 14/10 | `855b0f5` | passage au français |
| 23/10 | `7962388` | M1 ×2, R2 ×2 ; statuts « livré » mis à jour |
| 28/10 | branche `feat/docs-mkdocs` | B1, X1, A3, EV3, T1, EV2, rédigées après leur code ; T1 « Brancher un serveur MCP existant » et EV2 « Adapter les règles au cabinet », rédigées avec leur code |
| 03/11 | — | étape du scénario ajoutée à chaque story ; rôles et préparation du poste (P) explicités dans le [scénario](scenario.md#les-rôles-autour-du-médecin) |
| 03/11 | — | M3 « Créer un dossier avant la consultation » et « Supprimer un dossier et ses traces », rédigées le même jour que la commande |
