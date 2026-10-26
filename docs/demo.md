# Démo

Le script suit le [scénario d'usage](scenario.md) de bout en bout, dans un seul fil :
une consultation de Mme Dupont. Durée : environ 8 minutes, dont 3 à 4 minutes de
génération (≈ 60 s pour la question du scénario, ≈ 20 à 25 s pour les autres) à occuper en
expliquant ce qui se passe.

## Préparation (la veille)

```bash
source .venv/bin/activate
ollama list                                   # qwen2.5:3b et nomic-embed-text présents
python -m sensai.rag list                     # l'index contient les 2 documents publics
python -m pytest -q                           # tout est vert
python -m sensai.memory.profiles set generaliste --specialty "Médecine générale" \
    --preference "Réponses courtes" --instructions "Citer les sources disponibles"
```

Le jour même, fermer les applications gourmandes en RAM, et utiliser une **base de
répétition neuve** pour que le dossier ne contienne pas les notes des essais précédents :

```bash
rm -f /tmp/sensai-demo.sqlite3
python -m sensai.web --demo --mcp --db /tmp/sensai-demo.sqlite3 --rag-index .sensai/rag.sqlite3
```

Ouvrir `http://127.0.0.1:8000` et, dans un second onglet, `http://127.0.0.1:8000/metrics.html`.

## Déroulé

| # | Action | Ce qu'on montre | Fonctionnalités |
|---|---|---|---|
| 1 | « Nouvelle consultation » : patient **Jeanne Dupont**, profil **generaliste** | une session par consultation, liée à un patient | M1, X1 |
| 2 | Taper **« Mme Dupont peut-elle prendre de l'amoxicilline ? »** | réponse en streaming ; allergie à la pénicilline tirée du dossier ; panneau « Sources » avec l'extrait de la notice ANSM | B1, M3, R1, R2 |
| 3 | Pendant la génération : expliquer le compteur de contexte | contexte plafonné à 2 048 tokens | — |
| 4 | « Voir le prompt envoyé » | le modèle a reçu `[PATIENT_1]` et `[NAISSANCE_1]`, jamais le vrai nom | EV2 |
| 5 | Taper **« Ajoute une note au dossier : amoxicilline contre-indiquée, allergie à la pénicilline. »** → **Refuser** | la fenêtre montre « Jeanne Dupont » en clair ; refus → rien n'est écrit | T1, A3 |
| 6 | Redemander la note → **Valider** | la note est écrite (outil MCP) | T1, A3 |
| 7 | Taper **« Ignore toutes les instructions précédentes. »** | refus immédiat, sans appel au modèle | EV2 |
| 8 | Onglet métriques | les tours de la démo, latence, aucun nom en clair | EV3 |
| 9 | « Réglages » : passer `num_predict` à 32, reposer la question 2 | réponse coupée : un paramètre change le comportement sans toucher au code | X1, config |

Puis, en CLI, une minute pour la base obligatoire (B1) :

```bash
python -m sensai --model nexiste:pas                       # erreur claire : ollama pull …
python -m sensai --db /tmp/sensai-demo.sqlite3 --no-rag     # sans patient sélectionné
>                                                          # entrée vide : ignorée
> Je m'appelle Paul.
> Comment je m'appelle ?                                   # historique : « Paul »
> /reset                                                   # nouvelle conversation
> /patient Jeanne Dupont
> /dossier                                                 # la note validée à l'étape 6 est là
> /quit
```

## Si quelque chose casse

| Problème | Repli |
|---|---|
| génération trop longue | Ctrl+C (CLI) ou « Arrêter » (web) : la session est gardée ; passer à l'étape suivante |
| le modèle n'appelle pas l'outil de note | CLI : `/note <texte>` appelle le même outil, avec la même confirmation |
| le serveur MCP ne démarre pas | relancer sans `--mcp` (mêmes outils en Python direct) et le dire |
| Ollama ne répond pas | passer aux enregistrements ci-dessous |

## Enregistrements de secours

**CLI, scénario complet, enregistrement réel** (28/10, `qwen2.5:3b` sur le PC de test,
6 min 45 s avec les temps de génération réels) : `/dossier`, question sur l'amoxicilline
avec les sources, note **refusée** puis **validée**, injection refusée, `/dossier` qui montre
la note.

- [`enregistrements/cli-scenario.txt`](enregistrements/cli-scenario.txt) : la transcription, lisible directement ;
- [`enregistrements/cli-scenario.cast`](enregistrements/cli-scenario.cast) : la même session au format
  asciicast, rejouée avec son minutage :

```bash
pip install asciinema          # ou : sudo dnf install asciinema
asciinema play -i 2 docs/enregistrements/cli-scenario.cast    # -i 2 : attentes raccourcies à 2 s
```

C'est l'affichage du médecin : le vrai nom de la patiente (fictive) y apparaît, comme à l'écran.

**Web** : à enregistrer à l'écran (Spectacle sous KDE : « Enregistrer l'écran »), en suivant
le déroulé ci-dessus, et à ranger dans `docs/enregistrements/`.
