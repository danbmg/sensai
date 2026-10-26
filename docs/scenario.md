# Scénario d'usage

## L'utilisateur

**Le Dr Martin, médecin généraliste en cabinet libéral.** Une vingtaine de consultations
par jour, sur le PC du cabinet : un portable de bureau, **sans carte graphique**.
Le Dr Martin n'est pas informaticien : l'assistant se lance comme un logiciel du cabinet.

## Le contexte

- **Les données de santé ne doivent pas sortir du cabinet.** Le secret médical et le RGPD
  interdisent d'envoyer un dossier à une API d'IA en ligne sans hébergement certifié.
  D'où le choix d'un modèle **local** (Ollama) et, en plus, la **pseudonymisation** de tout
  ce qui part vers le modèle : si un jour le modèle tourne ailleurs, aucun nom ne part avec.
- **Le dossier patient existe déjà** (antécédents, allergies, traitements) dans une base
  locale. La notice du médicament est publique (base ANSM).
- **Le médecin reste responsable.** L'assistant aide à vérifier, il ne prescrit pas et ne
  modifie rien sans accord.

## Le besoin

> Avant de prescrire, vérifier en une question qu'un médicament ne pose pas de problème
> **pour ce patient-là**, avec la source, et garder une trace dans le dossier.

## Le scénario (fil rouge de la démo)

Le Dr Martin reçoit Mme Dupont et envisage de lui prescrire de l'amoxicilline.

| Étape | Ce qui se passe | Fonctionnalités |
|---|---|---|
| S0 | Le médecin ouvre la consultation de Mme Dupont (CLI ou web) et tape sa question. La réponse s'affiche au fil de l'eau. | B1, X1, M1 |
| S1 | « Mme Dupont » devient `[PATIENT_1]` avant l'envoi au modèle. À l'écran, le médecin lit le vrai nom. | EV2 |
| S2 | L'assistant retrouve dans le dossier SQLite l'**allergie à la pénicilline** (urticaire et œdème de Quincke en 2019). | M3 |
| S3 | Il cite l'extrait de la **notice ANSM** de l'amoxicilline, qui est une pénicilline. | R1, R2 |
| S4 | Il propose d'ajouter une note au dossier. Une fenêtre montre l'outil et ses arguments **en clair**. Le médecin valide ou refuse. | T1, A3 |
| S5 | Chaque tour est journalisé (pseudonymisé) ; le tableau de bord montre la latence. | EV3 |

## Le scénario est-il réaliste avec un modèle local ?

C'est la vraie contrainte du projet, mesurée sur le PC de Dan (Intel Core 5 120U, sans GPU,
15 Go de RAM) avec `qwen2.5:3b` :

| Mesure | Valeur | Source |
|---|---|---|
| Question du scénario, dossier + 3 extraits (≈ 1 040 tokens lus) | **≈ 59 s** | [Mesures](mesures.md), 28/10 |
| Même question, dossier seul (≈ 310 tokens lus) | ≈ 20 s | [Mesures](mesures.md), 28/10 |
| Questions sur le dossier en consultation (≈ 800 tokens lus) | 42 à 47 s | logs du 23/10 (6 tours) |
| Premier fragment affiché (≈ 770 tokens lus) | ≈ 37 s après la question | essai CLI du 28/10 |
| Tour du bench initial (2 appels, contexte 4 096) | 69 s | [Choix du modèle](bench.md) |

**Ce qu'on en conclut :**

- L'assistant n'est **pas fait pour une conversation rapide**. Il sert à **une à trois
  vérifications ponctuelles par consultation**, que le médecin lance pendant qu'il fait autre
  chose (examen, rédaction). C'est cet usage que le scénario montre.
- La quasi-totalité du temps est la **lecture du contexte** (le dossier et les extraits) par
  le modèle : la latence suit le nombre de tokens lus (≈ 20 s pour 310, ≈ 59 s pour 1 040).
  D'où les réglages qui réduisent le contexte (`num_ctx = 2048`, extraits plafonnés à 2 600 caractères, mode RAG `auto` qui
  n'ajoute pas de notice quand la question ne porte que sur le dossier). Voir
  [Choix et alternatives](choix.md#budget-de-contexte).
- Le budget de départ (un tour en 30 s) **n'est pas tenu** sur ce PC. Nous l'assumons et le
  disons ([Limites](limites.md)) ; sur un PC avec GPU, l'écart serait différent, mais nous ne
  l'avons pas mesuré.

## Le projet colle-t-il au profil ?

Chaque fonctionnalité répond à une contrainte du Dr Martin ; aucune n'a été ajoutée pour
elle-même.

| Contrainte du cabinet | Réponse dans Sensai |
|---|---|
| Pas de fuite de données de santé | modèle local + pseudonymisation (EV2), logs pseudonymisés (EV3) |
| L'information est dans le dossier, pas dans le modèle | dossiers SQLite (M3) injectés dans le contexte |
| Une réponse médicale doit être sourcée | notices publiques citées [S1], [S2] (R1, R2) |
| Le médecin garde la main sur le dossier | toute écriture attend sa validation (A3) |
| Plusieurs patients par jour, sans mélanger | une session par consultation, liée à un patient (M1) |
| Pas informaticien | interface web (X1), messages d'erreur sans trace technique (B1) |
| Un PC lent | réglages de contexte, tableau de latence (EV3) |

## Un scénario fixé dès le départ

Ce scénario n'a pas changé depuis le début du projet :

- **5 octobre (bootstrap)** : il sert déjà de cas de mesure pour choisir le modèle — dossier
  de `[PATIENT_1]` allergique aux pénicillines, question sur l'amoxicilline, outil
  `add_patient_note` ([Choix du modèle](bench.md), commit `b35d135`).
- **14 octobre** : démo du même cas, rejouée avec le vrai modèle ([Vérification de la démo](demo_verified.md)).
- **28 octobre** : mesure avec / sans contexte, toujours sur la même question
  ([Mesures](mesures.md)).
