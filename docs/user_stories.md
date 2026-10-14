# User stories

Au moins 2 user stories par feature implémentée.

Format :

```
As a <type d'utilisateur>, I want to <action>, so that <résultat>.
Acceptance criteria:
- <comportement observable 1>
- <comportement observable 2>
- <comportement observable 3>
```

## Dan — B1, X1, A3, EV3

## Timothée — M1, M3, R1, R2

### M1 — Reprendre une session (livré avec SQLite et la CLI)

As a médecin, I want to reprendre une conversation après redémarrage, so that je puisse poursuivre mon travail sans ressaisir les échanges précédents.
Acceptance criteria:
- Un historique sauvegardé est rechargé à l'identique après réouverture du stockage.
- Les correspondances des pseudonymes sont restaurées avec l'historique.
- Les sessions sont listables et restent indépendantes ; une session inconnue est vide.

### M1 — Profil médecin (à implémenter)

As a médecin, I want to enregistrer ma spécialité, mes préférences et mes instructions, so that l'assistant adapte ses réponses dès le démarrage.
Acceptance criteria:
- Le profil est conservé après redémarrage.
- Le profil sélectionné est injecté dans le contexte initial de la conversation.
- Une modification du profil est prise en compte à l'ouverture d'une nouvelle conversation.

### M3 — Consulter un dossier (livré avec API, contexte et outils locaux/MCP)

As a médecin, I want to retrouver les allergies, traitements et antécédents d'un patient, so that je dispose des informations enregistrées pour ma consultation.
Acceptance criteria:
- Le dossier est consultable par son identifiant avec ses allergies, traitements, antécédents et notes.
- La recherche par nom retourne tous les patients correspondants sans sélectionner arbitrairement un homonyme.
- Le jeu fictif contient Mme Jeanne Dupont avec une allergie à la pénicilline.

### M3 — Mettre à jour un dossier (livré avec validation humaine)

As a médecin, I want to ajouter une note et corriger les données d'un dossier, so that les informations restent disponibles lors des consultations suivantes.
Acceptance criteria:
- Une note ajoutée ne remplace pas les notes précédentes et reste présente après réouverture de la base.
- Modifier un champ conserve les autres champs ; un patient absent ou ambigu provoque une erreur explicite.
- Une écriture demandée par le modèle n'est exécutée qu'après confirmation du médecin via le pipeline.

### R1 — Rechercher dans les notices (à implémenter)

As a médecin, I want to retrouver les passages pertinents de notices ANSM et recommandations HAS, so that les réponses reposent sur mon corpus documentaire local.
Acceptance criteria:
- Les documents sont découpés en extraits associés à leur source et leur emplacement.
- Les embeddings sont obtenus via l'API HTTP Ollama `/api/embed` avec `nomic-embed-text`.
- La recherche utilise la similarité cosinus et une requête pseudonymisée, sans indexer les dossiers patients.

### R1 — Identifier les sources (à implémenter)

As a médecin, I want to connaître les sources des extraits utilisés, so that je puisse vérifier les informations proposées.
Acceptance criteria:
- `ContextProvider` transmet chaque extrait retrouvé avec une référence à son document source.
- Une recherche sans extrait pertinent est signalée dans le contexte sans inventer de source.
- Le scénario Mme Dupont associe le dossier local et les extraits publics utiles sans mélanger leurs stockages.

## Matteo — T1, EV1, EV2
