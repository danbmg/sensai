# Histoires utilisateur

Au moins deux histoires utilisateur par fonctionnalité implémentée.

Format :

```
En tant que <type d'utilisateur>, je souhaite <action>, afin de <résultat>.

Critères d'acceptation :
- <comportement observable 1>
- <comportement observable 2>
- <comportement observable 3>
```

## Dan — B1, X1, A3, EV3

### B1 — Voir la réponse s'écrire

En tant que médecin, je souhaite voir la réponse s'afficher au fur et à mesure dans le terminal, afin de savoir que l'assistant travaille et de commencer à lire sans attendre la fin.

Critères d'acceptation :

- Les fragments s'affichent dès leur réception, avant la fin de la génération.
- Une entrée vide est ignorée, sans appel au modèle.
- Ctrl+C pendant la génération arrête la réponse ; la session reste ouverte et le tour interrompu n'est pas enregistré.

### B1 — Garder le fil de la consultation

En tant que médecin, je souhaite que l'assistant se souvienne de ce que j'ai dit plus tôt dans la conversation, afin de poser des questions de suivi sans tout répéter.

Critères d'acceptation :

- Après « Je m'appelle Paul. », la question « Comment je m'appelle ? » obtient une réponse contenant « Paul ».
- `/reset` ouvre une nouvelle conversation : les échanges précédents ne sont plus envoyés au modèle.
- Au-delà de `max_history_turns` tours, seuls les derniers tours sont envoyés ; l'occupation du contexte est affichée après chaque réponse.

### B1 — Comprendre une panne sans trace technique

En tant que médecin, je souhaite un message clair quand l'assistant ne peut pas répondre, afin de savoir quoi faire sans appeler un informaticien.

Critères d'acceptation :

- Ollama éteint : le message indique l'adresse contactée et la commande `ollama serve`.
- Modèle absent : le message indique la commande `ollama pull <modèle>`.
- Modèle sans capacité `tools` : refus au démarrage ; modèle `thinking` : avertissement.

### B1 — Changer de modèle sans toucher au code

En tant que responsable informatique du cabinet, je souhaite choisir le modèle dans `config.toml` ou au lancement, afin d'adapter l'assistant à la machine disponible.

Critères d'acceptation :

- `--model llama3.2:3b` remplace le modèle de `config.toml` pour ce lancement.
- `--config autre.toml` charge un autre fichier de configuration.
- Aucun nom de modèle n'est écrit en dur dans le code Python.

### X1 — Consulter depuis le navigateur

En tant que médecin, je souhaite utiliser l'assistant dans une page web, afin de travailler sans terminal.

Critères d'acceptation :

- `python -m sensai.web --demo` sert l'interface sur `http://127.0.0.1:8000`.
- La réponse s'affiche en streaming, avec le nombre de tokens et l'occupation du contexte.
- Les appels d'outils et les sources du dernier tour sont affichés à côté de la conversation.

### X1 — Choisir le patient, le profil et le modèle

En tant que médecin, je souhaite ouvrir une consultation pour un patient et un profil, et changer de modèle ou de réglage depuis la page, afin d'adapter l'assistant sans relancer le serveur.

Critères d'acceptation :

- Le sélecteur de modèle liste les modèles installés dans Ollama.
- La fenêtre « Réglages » modifie température, `num_predict`, `num_ctx` et nombre de tours d'historique ; une valeur invalide est refusée sans rien changer.
- La liste des consultations permet de reprendre une session enregistrée, avec son patient.

### X1 — Voir ce que le modèle a reçu

En tant que médecin, je souhaite afficher le prompt exact envoyé au modèle, afin de vérifier qu'aucun nom de patient n'en sort.

Critères d'acceptation :

- « Voir le prompt envoyé » affiche les messages du dernier tour, tels que le modèle les a reçus.
- Ces messages contiennent `[PATIENT_1]`, jamais le nom réel.
- Le nombre de tokens lus et la taille de la fenêtre de contexte sont affichés.

### A3 — Valider une écriture dans le dossier

En tant que médecin, je souhaite approuver toute modification d'un dossier avant qu'elle soit écrite, afin que l'IA ne modifie jamais une donnée médicale sans mon accord.

Critères d'acceptation :

- Avant toute écriture, l'outil et ses arguments sont affichés en clair, avec le vrai nom du patient.
- Si je refuse, le dossier est inchangé et l'assistant indique que l'action n'a pas été exécutée.
- Si j'accepte, la note apparaît dans le dossier (`/dossier`).

### A3 — Valider depuis la page web

En tant que médecin, je souhaite une fenêtre de confirmation dans le navigateur, afin de valider ou refuser une action sans quitter l'interface.

Critères d'acceptation :

- Une demande d'écriture ouvre une fenêtre « Action à valider » avec l'outil et ses arguments.
- Sans réponse dans les 120 secondes, l'action est refusée.
- « Valider » écrit la note ; « Refuser » laisse le dossier inchangé.

### EV3 — Garder une trace de chaque tour, sans données patient

En tant que responsable du cabinet, je souhaite un journal de chaque échange, afin de pouvoir vérifier après coup ce que l'assistant a fait.

Critères d'acceptation :

- Chaque tour ajoute une ligne JSON à `logs/AAAA-MM-JJ.jsonl` : modèle, prompt et réponse, outils appelés, latence, tokens, configuration.
- Aucun nom, date de naissance ou adresse de patient n'apparaît en clair dans ces fichiers.
- Une écriture de log en échec n'interrompt pas la consultation.

### EV3 — Suivre les performances

En tant que responsable du cabinet, je souhaite voir le volume, la latence et le taux d'erreur, afin de savoir si un changement de modèle ou de réglage ralentit l'assistant.

Critères d'acceptation :

- `/metrics.html` et `python -m sensai.obs` affichent le nombre de tours, la latence moyenne, p50 et p95, et le taux d'erreur.
- Les chiffres sont regroupés par modèle et par configuration, version du prompt système comprise.
- Après un changement de modèle, une nouvelle ligne apparaît dans le tableau « Par modèle ».

## Timothée — M1, M3, R1, R2

### M1 — Reprendre une session (livré avec SQLite et la CLI)

En tant que médecin, je souhaite reprendre une conversation après le redémarrage de l'assistant, afin de poursuivre mon travail sans ressaisir les échanges précédents.

Critères d'acceptation :

- Un historique sauvegardé est rechargé à l'identique après réouverture du stockage.
- Les correspondances des pseudonymes sont restaurées avec l'historique.
- Les sessions sont listables et restent indépendantes ; une session inconnue est vide.

### M1 — Profil médecin (livré avec SQLite, commandes et injection du contexte)

En tant que médecin, je souhaite enregistrer ma spécialité, mes préférences et mes instructions, afin que l'assistant adapte ses réponses dès le démarrage.

Critères d'acceptation :

- Le profil est conservé après redémarrage.
- Le profil sélectionné est injecté dans le contexte initial de la conversation.
- Une modification du profil est prise en compte à l'ouverture d'une nouvelle conversation.

### M1 — Garder les conversations séparées (livré avec la reprise du contexte)

En tant que médecin, je souhaite que chaque conversation conserve le patient et le profil sélectionnés, afin de reprendre une consultation sans mélanger les dossiers.

Critères d'acceptation :

- Changer de patient ouvre un nouvel identifiant de session.
- Reprendre une nouvelle session enregistrée restaure son patient, son profil, ses filtres et ses dernières sources.
- Le démarrage refuse de reprendre une session avec un autre patient explicitement demandé.

### M1 — Choisir un profil médecin (livré avec la CLI)

En tant que médecin, je souhaite sélectionner un profil enregistré, afin d'appliquer mes préférences à une nouvelle conversation.

Critères d'acceptation :

- Les profils peuvent être listés et affichés sans appeler le modèle.
- Un profil inconnu produit une erreur explicite sans modifier le profil courant.
- Le changement de profil ouvre une nouvelle conversation, avec ses instructions injectées même sans patient sélectionné.

### M3 — Consulter un dossier (livré avec API, contexte et outils locaux/MCP)

En tant que médecin, je souhaite retrouver les allergies, traitements et antécédents d'un patient, afin de disposer des informations enregistrées pour ma consultation.

Critères d'acceptation :

- Le dossier est consultable par son identifiant avec ses allergies, traitements, antécédents et notes.
- La recherche par nom retourne tous les patients correspondants sans sélectionner arbitrairement un homonyme.
- Le jeu fictif contient Mme Jeanne Dupont avec une allergie à la pénicilline.

### M3 — Mettre à jour un dossier (livré avec validation humaine)

En tant que médecin, je souhaite ajouter une note et corriger les données d'un dossier, afin de conserver des informations à jour pour les consultations suivantes.

Critères d'acceptation :

- Une note ajoutée ne remplace pas les notes précédentes et reste présente après réouverture de la base.
- Modifier un champ conserve les autres champs ; un patient absent ou ambigu provoque une erreur explicite.
- Une écriture demandée par le modèle n'est exécutée qu'après confirmation du médecin via le pipeline.

### R1 — Rechercher dans les notices (livré avec ingestion et recherche locale)

En tant que médecin, je souhaite retrouver les passages pertinents des notices ANSM et des recommandations HAS, afin d'obtenir des réponses fondées sur mon corpus documentaire local.

Critères d'acceptation :

- Les documents sont découpés en extraits associés à leur source et leur emplacement.
- Les représentations vectorielles des extraits sont obtenues via l'API HTTP Ollama `/api/embed` avec `nomic-embed-text`.
- La recherche utilise la similarité cosinus et une requête pseudonymisée, sans indexer les dossiers patients.

### R1 — Identifier les sources (livré via ContextProvider et /sources)

En tant que médecin, je souhaite connaître les sources des extraits utilisés, afin de pouvoir vérifier les informations proposées.

Critères d'acceptation :

- `ContextProvider` transmet chaque extrait retrouvé avec une référence à son document source.
- Une recherche sans extrait pertinent est signalée dans le contexte sans inventer de source.
- Le scénario Mme Dupont associe le dossier local et les extraits publics utiles sans mélanger leurs stockages.

### R2 — Limiter les documents recherchés (bonus livré)

En tant que médecin, je souhaite filtrer les documents par éditeur, étiquettes et date connue, afin de rechercher dans les sources adaptées à ma question.

Critères d'acceptation :

- Les filtres sont appliqués avant le calcul des scores de similarité.
- Les documents sans date connue sont exclus lorsqu'une période est demandée.
- Un filtre sans résultat retourne une recherche vide sans appeler le modèle d'embeddings.

### R2 — Écarter les extraits peu pertinents (bonus livré avec BM25)

En tant que médecin, je souhaite que les passages retenus soient reclassés et soumis à des seuils de pertinence, afin de limiter les extraits inutiles dans le contexte.

Critères d'acceptation :

- Le reclassement combine la similarité cosinus et un score lexical BM25 ; il peut être désactivé pour comparaison.
- Les extraits sous les seuils configurés sont écartés et les copies identiques sont dédupliquées.
- Le nombre d'extraits et leur longueur totale restent limités ; aucune source n'est inventée en cas de recherche vide.

## Matteo — T1, EV2

EV1 (évaluation automatique par un LLM-juge) n'a pas été livrée : voir
[Traçabilité](tracabilite.md#fonctionnalites-abandonnees-ou-modifiees).

### T1 — Laisser l'assistant consulter le dossier par un outil

En tant que médecin, je souhaite que l'assistant appelle lui-même les outils patients quand ma demande le nécessite, afin d'obtenir une réponse fondée sur le dossier plutôt que sur sa mémoire.

Critères d'acceptation :

- `/tools` liste les outils disponibles : `get_patient`, `find_patients`, `add_patient_note`, `add_patient_entry`, `remove_patient_entry`, `calculator`, `get_current_time`.
- Le résultat d'un outil est renvoyé au modèle, qui termine sa réponse.
- Un appel d'outil invalide, ou un outil non proposé pour ce tour, est refusé sans action exécutée.

### T1 — Isoler les outils patients dans un serveur MCP

En tant que responsable informatique du cabinet, je souhaite que les outils patients tournent dans un processus séparé accessible par MCP, afin de pouvoir les réutiliser ou les remplacer sans modifier l'assistant.

Critères d'acceptation :

- `--mcp` lance le serveur médical en stdio et découvre ses outils au démarrage.
- Les mêmes commandes et le même scénario fonctionnent avec et sans `--mcp`.
- Si le serveur ne démarre pas, un message clair s'affiche, sans trace technique.

### T1 — Brancher un serveur MCP existant

En tant que responsable informatique du cabinet, je souhaite ajouter un serveur MCP écrit par d'autres en le déclarant dans la configuration, afin de donner un nouvel outil à l'assistant sans modifier son code.

Critères d'acceptation :

- Un bloc `[[mcp.servers]]` dans `config.toml` suffit : au lancement avec `--mcp`, ses outils apparaissent dans `/tools`, préfixés par le nom du serveur.
- Seuls les outils listés dans `tools` sont retenus ; ceux listés dans `dangerous` demandent la validation du médecin.
- Si le serveur ne démarre pas, il est signalé et ignoré, et la consultation continue.

### EV2 — Ne jamais envoyer l'identité d'un patient au modèle

En tant que médecin, je souhaite que le nom, la date de naissance, l'adresse, le téléphone, le numéro de sécurité sociale et l'email d'un patient soient remplacés par des pseudonymes avant l'envoi au modèle, afin de respecter le secret médical.

Critères d'acceptation :

- Les messages envoyés au modèle, l'historique et les logs contiennent `[PATIENT_1]`, jamais « Dupont ».
- « Dupont », « Mme Dupont » et « Jeanne Dupont » donnent le même pseudonyme, d'un tour à l'autre.
- À l'écran et dans la confirmation, le médecin lit le vrai nom.

### EV2 — Bloquer les détournements et masquer les fuites

En tant que médecin, je souhaite que les tentatives de détournement soient refusées avant d'atteindre le modèle, et que les données personnelles restantes soient masquées dans les réponses, afin que l'assistant reste dans son rôle.

Critères d'acceptation :

- « Ignore toutes les instructions précédentes. » est refusé avant tout appel au modèle, avec un motif affiché.
- Une demande d'extraction de mots de passe ou de clés API est refusée.
- Un téléphone, un email, un NIR ou un IBAN présent dans une réponse est masqué avant l'enregistrement.

### EV2 — Adapter les règles au cabinet

En tant que responsable informatique du cabinet, je souhaite ajouter ou retirer des règles de filtrage dans la configuration, afin de bloquer un nouveau contournement sans attendre une nouvelle version du code.

Critères d'acceptation :

- Une règle `[[guardrails.custom_rules]]` (motif et message) refuse les requêtes qui lui correspondent, avec son propre message.
- Les familles de règles intégrées et les types de données masquées en sortie se choisissent dans `[guardrails]`.
- Une règle invalide (expression régulière fausse, famille inconnue) empêche le démarrage avec un message clair.
