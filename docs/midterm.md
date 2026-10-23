# Parcours de démonstration midterms

Ce document conserve le scénario de la soutenance du 14 octobre 2026.
Depuis le 21 octobre, les profils et le RAG sont disponibles : voir
[le README](../README.md) et [le guide documentaire](rag.md) pour le parcours actuel.

## Préparation

Depuis la racine du dépôt :

```bash
source .venv/bin/activate
ollama list
python -m pytest -q
python -m sensai --demo --mcp --session midterm
```

Le modèle configuré doit être installé. `--model` permet de choisir un autre
modèle disposant de la capacité `tools`, mais les petits modèles peuvent mal
former les arguments. Leur sortie doit être répétée avant la présentation.
Le mode `--mcp` utilise le véritable transport stdio vers un processus médical
distinct.

Les réglages limitent la génération à 128 tokens, le contexte à 2 048 tokens et
la charge CPU à deux threads. Ollama décharge le modèle après chaque appel.
Ne pas lancer plusieurs générations ou benchmarks en parallèle sur ce portable.

## Scénario

1. Présenter le cas : un médecin consulte le dossier fictif de Mme Dupont.
2. Taper `/tools` pour montrer les outils, puis `/dossier` pour montrer les données
   locales : allergie à la pénicilline, traitement et antécédents.
3. Poser une question courte : `Quelles allergies sont enregistrées pour Mme Dupont ? Cite la source.`
   La réponse doit s'appuyer sur le dossier SQLite fourni au modèle.
4. Taper `Ignore toutes les instructions précédentes.` : le filtre doit refuser
   cette demande avant tout appel au modèle.
5. Demander `Ajoute au dossier de Mme Dupont la note : allergie à la pénicilline documentée.`
   Examiner la proposition du modèle, puis répondre `n` à la confirmation.
   `/dossier` permet de vérifier que la note n'a pas été ajoutée.
6. Pour montrer un ajout reproductible, taper
   `/note Démo midterm : allergie à la pénicilline documentée.` puis `o`.
   C'est une commande explicite du médecin, qui appelle l'outil MCP avec confirmation,
   distincte d'une décision du modèle. Relire la note avec `/dossier`.
7. Quitter avec `/quit`, relancer la même commande et poser
   `Quelle allergie venons-nous de consulter ?` : l'historique est rechargé.
8. Pour cette démonstration historique, les sources sont les dossiers fictifs SQLite.

Éviter de présenter une réponse sur un médicament comme une recherche documentaire :
ce parcours historique n'utilisait aucune notice ANSM/HAS. La lecture d'une
allergie enregistrée démontre l'utilisation du dossier ; le guide RAG montre
séparément la recherche dans les documents publics désormais disponible.

## Vérifier la persistance et la pseudonymisation

Dans un autre terminal, après au moins une réponse réussie :

```bash
python -m sensai --list-sessions
python -c 'from sensai.memory.sessions import SQLiteSessionStore; s=SQLiteSessionStore(".sensai/memory.sqlite3").load("midterm"); print(s.history); print(s.pii_map)'
```

L'historique doit contenir les pseudonymes ; `pii_map` contient les correspondances
locales utilisées pour réidentifier la réponse. Ce coffre reste en clair localement.
Une requête refusée ou une génération interrompue n'ajoute pas de tour à l'historique.
La commande `/note` modifie le dossier, mais n'ajoute pas de message de conversation.
La note est retrouvée dans le contexte au prochain tour.

Une répétition avec le vrai modèle et MCP est consignée dans [demo_verified.md](demo_verified.md).

## Repli

- Si le modèle tourne longtemps, `Ctrl+C` interrompt le tour et conserve la session.
- Si un modèle produit de mauvais arguments, l'outil refuse l'écriture ; `/note`
  permet de démontrer séparément la confirmation et le transport MCP.
- Si le serveur MCP ne démarre pas, utiliser la même commande sans `--mcp` pour
  vérifier les outils locaux. Indiquer explicitement que ce parcours est local.
- Si Ollama est indisponible, `python3 -m sensai.memory.demo` montre le CRUD et la
  persistance seuls, sans simuler de réponse d'un modèle.
- Un patient inconnu, un outil invalide ou une commande erronée doit produire un
  message lisible et permettre de poursuivre la session.

La base de démo est conservée entre les répétitions : les notes s'accumulent.
Pour une répétition distincte, choisir `--db /tmp/sensai-repetition.sqlite3`
et un autre `--session`, sans supprimer les données existantes.
