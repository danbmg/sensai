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

## Timothée — M1, M3, R1, R2

### M1 — Reprendre une session (livré avec SQLite et la CLI)

En tant que médecin, je souhaite reprendre une conversation après le redémarrage de l'assistant, afin de poursuivre mon travail sans ressaisir les échanges précédents.

Critères d'acceptation :

- Un historique sauvegardé est rechargé à l'identique après réouverture du stockage.
- Les correspondances des pseudonymes sont restaurées avec l'historique.
- Les sessions sont listables et restent indépendantes ; une session inconnue est vide.

### M1 — Profil médecin (à implémenter)

En tant que médecin, je souhaite enregistrer ma spécialité, mes préférences et mes instructions, afin que l'assistant adapte ses réponses dès le démarrage.

Critères d'acceptation :

- Le profil est conservé après redémarrage.
- Le profil sélectionné est injecté dans le contexte initial de la conversation.
- Une modification du profil est prise en compte à l'ouverture d'une nouvelle conversation.

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

### R1 — Rechercher dans les notices (à implémenter)

En tant que médecin, je souhaite retrouver les passages pertinents des notices ANSM et des recommandations HAS, afin d'obtenir des réponses fondées sur mon corpus documentaire local.

Critères d'acceptation :

- Les documents sont découpés en extraits associés à leur source et leur emplacement.
- Les représentations vectorielles des extraits sont obtenues via l'API HTTP Ollama `/api/embed` avec `nomic-embed-text`.
- La recherche utilise la similarité cosinus et une requête pseudonymisée, sans indexer les dossiers patients.

### R1 — Identifier les sources (à implémenter)

En tant que médecin, je souhaite connaître les sources des extraits utilisés, afin de pouvoir vérifier les informations proposées.

Critères d'acceptation :

- `ContextProvider` transmet chaque extrait retrouvé avec une référence à son document source.
- Une recherche sans extrait pertinent est signalée dans le contexte sans inventer de source.
- Le scénario Mme Dupont associe le dossier local et les extraits publics utiles sans mélanger leurs stockages.

## Matteo — T1, EV1, EV2
