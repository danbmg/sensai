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
