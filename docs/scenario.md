# Scénario d'usage

Pourquoi un médecin a besoin de Sensai, dans quelle situation, et comment le projet y répond.
Les user stories qui en découlent sont dans [user_stories.md](user_stories.md#1-user-stories), la démo qui rejoue
ce scénario dans [demo.md](demo.md).

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

## Pourquoi le Dr Martin a besoin de Sensai

### Une consultation, sans assistant

Mardi, 10 h 40. Le Dr Martin reçoit Mme Dupont, 68 ans, qu'il suit pour une hypertension.
Elle a mal à la gorge depuis trois jours ; il pense à une angine, et à l'amoxicilline.

Avant de rédiger l'ordonnance, il doit vérifier deux choses :

1. **Le dossier de la patiente** : ses allergies et ses traitements en cours. L'allergie à la
   pénicilline a été notée en 2019, après un œdème de Quincke, parmi d'autres antécédents. Il
   faut la retrouver, et ne pas conclure trop vite : « aucune allergie enregistrée » ne
   voudrait pas dire « pas d'allergie ».
2. **Le médicament** : savoir que l'amoxicilline est une pénicilline, et ce que dit sa notice
   en cas d'allergie. Il faut ouvrir la base publique des médicaments (BDPM) et chercher le
   bon paragraphe.

Il veut ensuite **garder une trace** : une note au dossier, « amoxicilline contre-indiquée »,
pour lui et pour le confrère qui verra la patiente la prochaine fois.

Tout cela se fait pendant la consultation, avec une vingtaine de patients dans la journée.
C'est dans ces conditions qu'une allergie ancienne peut passer inaperçue.

### Pourquoi pas un assistant en ligne

Coller le dossier de Mme Dupont dans un chatbot en ligne, c'est faire sortir des données de
santé du cabinet. Le secret médical et le RGPD l'interdisent, sauf chez un hébergeur certifié
de données de santé (HDS) et avec un contrat adapté. Le cabinet n'en a pas, et un assistant en
ligne n'aurait de toute façon pas accès au dossier local.

### La même consultation, avec Sensai

Le PC du cabinet fait tourner Sensai en local. Le Dr Martin ouvre la consultation de
Mme Dupont et tape une seule question : « Mme Dupont peut-elle prendre de l'amoxicilline ? ».
Il examine la patiente pendant que l'assistant travaille, environ une minute.

- Avant l'envoi au modèle, « Mme Dupont » devient `[PATIENT_1]` : même en local, le modèle ne
  reçoit jamais son identité.
- L'assistant lit son dossier : allergie à la pénicilline, urticaire et œdème de Quincke en 2019.
- Il cite l'extrait de la notice ANSM de l'amoxicilline, avec sa source.
- Il répond « Non », et explique pourquoi.
- Le Dr Martin demande d'ajouter la note au dossier. Une fenêtre lui montre exactement ce qui va
  être écrit, avec le vrai nom de la patiente. Il valide ; sans sa validation, rien n'est écrit.

Il choisit un autre traitement : c'est sa décision, pas celle de l'assistant.

### Ce que Sensai ne fait pas

- Il ne prescrit pas et ne pose pas de diagnostic : il aide à vérifier, le médecin décide.
- Ce n'est pas un dispositif médical : il n'a aucune validation clinique.
- Il peut se tromper. C'est pour cela qu'il cite ses sources et que toute écriture passe par le
  médecin ([limites](mesures.md#4-limites-du-système)).

### Autour de la consultation

- **Un nouveau patient** : avant sa première consultation, le Dr Martin crée son dossier par
  une commande, sans passer par l'assistant. Son nom est ainsi pseudonymisé dès la première
  question (étape P).
- **Un patient demande l'effacement de ses données** : le Dr Martin, titulaire du cabinet,
  supprime son dossier et ses conversations (étape P).
- **Le prestataire informatique** installe Sensai et règle `config.toml` : le modèle adapté au
  PC, les outils, les règles de filtrage, sans modifier le code (étape P).
- **En fin de journée**, le Dr Martin peut relire le journal des échanges, sans aucun nom en
  clair, et la latence de l'assistant (étape S5).

## Les rôles autour du médecin

Pendant la consultation, le Dr Martin est le seul utilisateur. Les user stories nomment
aussi deux rôles qui interviennent avant ou après :

| Rôle dans les user stories | Qui, au cabinet | Ce qu'il fait avec Sensai | Étape |
|---|---|---|---|
| « médecin » | le Dr Martin | crée le dossier d'un nouveau patient avant sa première consultation ; pose ses questions, valide ou refuse les écritures | P, S0 à S4 |
| « responsable du cabinet » | le Dr Martin lui-même : en libéral, il est titulaire de son cabinet | relit le journal et la latence, après les consultations ; supprime un dossier quand un patient demande l'effacement de ses données | P, S5 |
| « responsable informatique du cabinet » | le prestataire informatique qui installe et entretient le PC du cabinet | installe Sensai, choisit le modèle adapté au PC, déclare les outils et les règles de filtrage dans `config.toml` | P |

## Le scénario (fil rouge de la démo)

Le Dr Martin reçoit Mme Dupont et envisage de lui prescrire de l'amoxicilline. Le poste a
été préparé une fois, en amont (P).

| Étape | Ce qui se passe | Fonctionnalités |
|---|---|---|
| P | Avant la première consultation, le prestataire installe Sensai sur le PC du cabinet et règle `config.toml` : modèle adapté à la machine, serveurs MCP, règles de filtrage. Aucun code n'est modifié. Le Dr Martin crée le dossier d'un nouveau patient, ou supprime celui d'un patient qui le demande, par une commande qui n'appelle pas le modèle. | B1, T1, EV2, M3 |
| S0 | Le médecin ouvre la consultation de Mme Dupont (CLI ou web) et tape sa question. La réponse s'affiche au fil de l'eau. | B1, X1, M1 |
| S1 | La question passe les filtres d'entrée (une tentative de détournement serait refusée ici), puis « Mme Dupont » devient `[PATIENT_1]` avant l'envoi au modèle. À l'écran, le médecin lit le vrai nom. | EV2, X1 |
| S2 | L'assistant retrouve dans le dossier SQLite l'**allergie à la pénicilline** (urticaire et œdème de Quincke en 2019). | M3 |
| S3 | Il cite l'extrait de la **notice ANSM** de l'amoxicilline, qui est une pénicilline. | R1, R2 |
| S4 | Il propose d'ajouter une note au dossier. Une fenêtre montre l'outil et ses arguments **en clair**. Le médecin valide ou refuse. | T1, A3, M3 |
| S5 | Chaque tour est journalisé (pseudonymisé) ; le tableau de bord montre la latence. | EV3 |

## Le scénario est-il réaliste avec un modèle local ?

C'est la vraie contrainte du projet, mesurée sur le PC de Dan (Intel Core 5 120U, sans GPU,
15 Go de RAM) avec `qwen2.5:3b` :

| Mesure | Valeur | Source |
|---|---|---|
| Question du scénario, dossier + 3 extraits (≈ 1 040 tokens lus) | **≈ 59 s** | [Mesures](mesures.md#2-avec-ou-sans-contexte), 28/10 |
| Même question, dossier seul (≈ 310 tokens lus) | ≈ 20 s | [Mesures](mesures.md#2-avec-ou-sans-contexte), 28/10 |
| Questions sur le dossier en consultation (≈ 800 tokens lus) | 42 à 47 s | logs du 23/10 (6 tours) |
| Premier fragment affiché (≈ 770 tokens lus) | ≈ 37 s après la question | essai CLI du 28/10 |
| Tour du bench initial (2 appels, contexte 4 096) | 69 s | [Choix du modèle](mesures.md#1-choix-du-modèle--le-bench) |

**Ce qu'on en conclut :**

- L'assistant n'est **pas fait pour une conversation rapide**. Il sert à **une à trois
  vérifications ponctuelles par consultation**, que le médecin lance pendant qu'il fait autre
  chose (examen, rédaction). C'est cet usage que le scénario montre.
- La quasi-totalité du temps est la **lecture du contexte** (le dossier et les extraits) par
  le modèle : la latence suit le nombre de tokens lus (≈ 20 s pour 310, ≈ 59 s pour 1 040).
  D'où les réglages qui réduisent le contexte (`num_ctx = 2048`, extraits plafonnés à 2 600 caractères, mode RAG `auto` qui
  n'ajoute pas de notice quand la question ne porte que sur le dossier). Voir
  [Choix et alternatives](decisions.md#budget-de-contexte).
- Le budget de départ (un tour en 30 s) **n'est pas tenu** sur ce PC. Nous l'assumons et le
  disons ([Limites](mesures.md#4-limites-du-système)) ; sur un PC avec GPU, l'écart serait différent, mais nous ne
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
| Un prestataire informatique, pas un développeur | modèle, serveurs MCP et règles de filtrage réglables dans `config.toml` (B1, T1, EV2) |

## Un scénario fixé dès le départ

Ce scénario n'a pas changé depuis le début du projet :

- **5 octobre (bootstrap)** : il sert déjà de cas de mesure pour choisir le modèle — dossier
  de `[PATIENT_1]` allergique aux pénicillines, question sur l'amoxicilline, outil
  `add_patient_note` ([Choix du modèle](mesures.md#1-choix-du-modèle--le-bench), commit `b35d135`).
- **14 octobre** : démo du même cas, rejouée avec le vrai modèle ([Vérification de la démo](mesures.md#3-vérifications-avec-le-vrai-modèle)).
- **28 octobre** : mesure avec / sans contexte, toujours sur la même question
  ([Mesures](mesures.md#2-avec-ou-sans-contexte)).
- **3 novembre** : la préparation du poste (P) et les rôles autour du médecin sont écrits
  explicitement, pour rattacher chaque user story à une étape ; la création et la suppression d'un
  dossier y sont rattachées. Le fil rouge S0 à S5 ne change pas.
  Le récit « Pourquoi le Dr Martin a besoin de Sensai » détaille ce même cas, sans le changer.
