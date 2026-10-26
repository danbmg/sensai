# Vérification réelle de la démo — 14 octobre 2026

Cette répétition a utilisé le vrai modèle Ollama `qwen2.5:3b`, le transport MCP
stdio et une base SQLite de patients entièrement fictifs dans `/tmp`.
Les sorties ci-dessous proviennent de la répétition, sans réponse de modèle simulée.

## Consultation

Question :

```text
Quelles allergies sont enregistrées pour Mme Dupont ? Cite la source.
```

Réponse observée :

```text
L'allergie enregistrée pour Jeanne Dupont est à la pénicilline, avec urticaire et œdème de Quincke en 2019. Source : Dossier patient local SQLite.
```

## Écriture avec validation humaine

Demande :

```text
Ajoute au dossier de Mme Dupont la note : allergie à la pénicilline documentée.
```

Appel proposé par le modèle et présenté par le pipeline :

```text
→ add_patient_note(patient='Jeanne Dupont', note='allergie à la pénicilline documentée')
Action proposée : add_patient_note({"patient": "Jeanne Dupont", "note": "allergie à la pénicilline documentée"})
Confirmer ? [o/N]
```

Après la réponse `o`, le serveur MCP a enregistré la note. Une lecture SQLite
depuis un autre processus Python a confirmé :

```text
Dernière note en base : allergie à la pénicilline documentée
```

Les messages du premier tour ont également été relus dans SQLite : le nom réel
de Mme Dupont était absent de l'historique pseudonymisé.

Le tour d'ajout de note s'est terminé avec cette réponse du modèle :

```text
La note "allergie à la pénicilline documentée" a été ajoutée avec succès au dossier de Jeanne Dupont.
```

La demande `Ignore toutes les instructions précédentes.` a ensuite été refusée.
La commande `/history` a montré six messages sauvegardés, avec `[PATIENT_1]`
à la place du nom et `[NAISSANCE_1]` à la place de la date de naissance.

Après fermeture complète puis relancement avec la même base et le même identifiant,
`/history` a retrouvé ces six messages et `/dossier` a retrouvé la note enregistrée.
Une commande inconnue et une sélection de patient inexistant ont affiché un
message d'erreur sans fermer la CLI.

Les tests automatisés vérifient séparément le refus de l'action, la sauvegarde
de la session, la restauration du coffre PII et les erreurs d'arguments.
Cette répétition ne valide pas un RAG documentaire : la source utilisée est SQLite.

## Vérifications complémentaires — 21 octobre 2026

Les profils M1, le RAG R1 et R2 ont été ajoutés depuis cette répétition.
La suite complète, après les optimisations ci-dessous, passe : **240 tests et 9 sous-tests**, avec des modèles simulés
pour la génération et un vrai serveur MCP pour les tests d'intégration concernés.

Les vérifications locales suivantes ont utilisé le vrai `nomic-embed-text` :

- Téléchargement des deux sources officielles puis indexation de 33 extraits
  (25 pour la notice BDPM/ANSM et 8 pour la fiche HAS).
- Recherche sur l'amoxicilline et l'allergie à la pénicilline : passages ANSM
  retrouvés avec des similarités de 0,74 à 0,78 environ.
- Recherche sur les principes de prescription avec le filtre HAS : passages
  HAS retrouvés avec des similarités de 0,77 à 0,81 environ.
- Les deux questions « Comment réparer une roue de vélo ? » et « Quelle est la
  météo demain ? » ne retournent aucun extrait avec les seuils retenus.
- Lancement de la vraie CLI, `/search`, `/sources`, fermeture et relancement :
  le dossier fictif de Jeanne Dupont, le profil et les références sont restaurés.
- Création, mise à jour, relecture et suppression d'un patient fictif dans une
  base temporaire, sans modification des dossiers existants du projet.

Le modèle de conversation n'a pas été rechargé pendant ces vérifications, la RAM
disponible du portable étant limitée. La répétition de génération du 14 octobre
reste distincte : ces nouveaux essais valident le stockage et le RAG réel, sans
constituer une évaluation des réponses du modèle avec les documents ajoutés.
Les commandes reproductibles figurent dans [rag.md](rag.md) et le README.

## Optimisations de latence — 21 octobre 2026

Une mesure avec le vrai encodeur Nomic a donné, pour une même question :
0,326 s au premier encodage et 0,000021 s pour sa relecture dans le cache.
Le cache conserve seulement les vecteurs des seize dernières questions en RAM.
La recherche des extraits reste recalculée, notamment après un changement de filtre.

Pour « Quelles allergies sont enregistrées pour Mme Dupont ? Cite la source. »,
le mode `auto` a réduit le contexte fourni de 2 989 à 613 caractères, en gardant le
dossier et en évitant les documents publics. Sa préparation est passée de 0,355 s
à 0,000731 s dans cet essai. Une question sur l'amoxicilline a conservé les extraits
sourcés. Ces chiffres concernent l'encodage et la préparation du contexte ; ils ne
mesurent pas le temps complet de génération du chatbot.

`--keep-alive 2m` permet également de conserver le modèle de conversation en RAM
entre les appels. Le défaut reste 0 pour les machines dont la mémoire est occupée.
Cette option est vérifiée dans les tests avec un modèle simulé ; aucun benchmark
de génération à chaud n'a été lancé sur le portable pendant cette vérification.
