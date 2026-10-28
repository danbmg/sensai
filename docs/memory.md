# Mémoire — M1 et M3 de Timothée

## État actuel

Disponible : API Python CRUD SQLite des patients, trois patients fictifs, stockage
persistant des sessions conforme à `SessionStore`, profils médecins persistants,
démo autonome et tests du stockage et de l'intégration CLI.

Les sessions, le profil sélectionné, le dossier patient et les documents publics
RAG sont branchés à la CLI via les interfaces existantes. La partie documentaire
R1 et R2 sont décrits dans [rag.md](rag.md).

## Démonstration

Depuis la racine du projet, sans Ollama et sans installation supplémentaire :

```bash
python3 -m sensai.memory.demo
```

La démo crée une base temporaire, charge les dossiers fictifs, retrouve Mme Dupont,
affiche son allergie et son traitement, ajoute une note et la relit avec une nouvelle
instance du stockage. Elle sauvegarde ensuite un historique pseudonymisé avec son
coffre PII et le recharge. Les réponses de conversation sont des données de test,
pas des réponses produites par un modèle. La base temporaire est supprimée à la fin.

Pour conserver la base et vérifier la persistance entre deux processus :

```bash
python3 -m sensai.memory.demo --db /tmp/sensai-demo.sqlite3
python3 -c 'from sensai.memory.patients import PatientStore; print(PatientStore("/tmp/sensai-demo.sqlite3").get_patient("demo-dupont"))'
python3 -c 'from sensai.memory.sessions import SQLiteSessionStore; print(SQLiteSessionStore("/tmp/sensai-demo.sqlite3").load("demo-session"))'
```

Relancer la démo sur la même base préserve les patients existants et ajoute une
nouvelle note de démonstration ; elle remplace la session réservée `demo-session`.
Utiliser un fichier dédié à la démo, hors du dépôt.

## API utilisée par les outils patients

```python
from sensai.memory.patients import PatientStore
from sensai.memory.fixtures import seed_demo_patients

patients = PatientStore("/tmp/sensai-demo.sqlite3")
seed_demo_patients(patients)  # uniquement pour la démo ; aucun écrasement
matches = patients.find_patients("Dupont")
patient = patients.resolve_patient("Jeanne Dupont")
updated = patients.add_patient_note(patient["patient_id"], "Note du médecin")
```

| Méthode | Contrat |
| --- | --- |
| `create_patient(name, birth_date="", *, allergies=None, treatments=None, medical_history=None, notes=None, patient_id=None)` | Crée et retourne le dossier ; identifiant généré si absent. |
| `get_patient(patient_id)` | Retourne le dossier par identifiant. |
| `list_patients()` | Retourne tous les dossiers, triés par nom puis identifiant. |
| `find_patients(name)` | Recherche partielle insensible à la casse ; retourne une liste. |
| `resolve_patient(reference)` | Résout un identifiant ou un nom complet exact. |
| `update_patient(patient_id, **fields)` | Remplace uniquement les champs fournis ; retourne le dossier. |
| `add_patient_note(reference, note)` | Ajoute une note sans remplacer les précédentes ; retourne le dossier. |
| `delete_patient(patient_id)` | Supprime le dossier identifié. |

Un dossier est un dictionnaire avec `patient_id`, `name`, `birth_date` et quatre
listes de textes : `allergies`, `treatments`, `medical_history`, `notes`.
Une liste vide signifie qu'aucun élément n'est enregistré, pas une absence médicale
certifiée. `birth_date` utilise conventionnellement `YYYY-MM-DD` ; sa validité
calendaire n'est pas contrôlée dans cette livraison.

Erreurs publiques : `PatientNotFoundError` si le patient est absent,
`AmbiguousPatientError` si un nom complet désigne plusieurs patients,
`ValueError` si un champ est invalide et `sqlite3.IntegrityError` si un identifiant
existe déjà. Une recherche partielle ne peut pas déclencher directement une écriture.
Avec plusieurs résultats, demander une précision puis utiliser `patient_id`.

`sensai/tools/patient_tools.py` adapte ces méthodes à `ToolRegistry`, fournit les
schémas, convertit résultats/erreurs en `ToolResult` et marque les écritures comme
dangereuses. Le serveur `sensai/tools/mcp_server.py` expose les outils via MCP.
Le pipeline reçoit et transmet les arguments des outils en clair après
réidentification. Aucun appel Ollama ou MCP n'est effectué par cette API.

## SessionStore utilisé par la CLI

```python
from sensai.memory.sessions import SQLiteSessionStore

sessions = SQLiteSessionStore("/tmp/sensai-demo.sqlite3")
# À la construction du Pipeline existant : sessions=sessions
# À chaque reprise : réutiliser le même session_id dans pipeline.run(...).
```

`load(session_id)` retourne `SessionState()` pour une session inconnue.
`save(session_id, state)` crée ou remplace atomiquement l'historique et `pii_map`.
`list_sessions()` retourne les identifiants triés. Les données rechargées sont
indépendantes : elles ne sont modifiées en base qu'après `save()`.

La CLI permet de sélectionner/reprendre un identifiant avec `--session` ou `/session`,
injecte ce stockage au pipeline et demande confirmation avant les écritures.
La table supplémentaire `session_context` conserve le patient, l'identifiant du
profil, les filtres documentaires et les derniers extraits utilisés, sans modifier
le contrat `SessionState`. `load_context()` et `save_context()` sont utilisés par
la CLI. La reprise recharge ces informations ; un patient supprimé produit une
erreur explicite. Les anciennes sessions sans métadonnées nécessitent un choix
explicite du patient. `/patient`, `/profile` et `/reset` ouvrent une nouvelle
conversation ; les sources de la précédente restent enregistrées avec elle.
Le vrai `PIIVault` est branché : le stockage sauvegarde le contrat reçu,
il ne pseudonymise pas les messages lui-même. SQLite contient le coffre PII local
en clair, conformément au contrat ; aucun chiffrement n'est implémenté.

## Profil médecin

`sensai/memory/profiles.py` fournit `DoctorProfile` et `DoctorProfileStore`.
La table `doctor_profiles`, dans la base mémoire, conserve l'identifiant, la
spécialité, une liste de préférences et les instructions personnalisées.
`save()` crée ou remplace un profil ; `load()` le retrouve ; `list_profiles()`
liste ses identifiants. Un identifiant inconnu lève `ProfileNotFoundError`.

```bash
python -m sensai.memory.profiles set generaliste --specialty "Médecine générale" --preference "Réponses courtes" --instructions "Citer les sources disponibles"
python -m sensai.memory.profiles show generaliste
python -m sensai.memory.profiles list
python -m sensai --profile generaliste
```

Ajouter `--db <chemin>` avant `set`, `show` ou `list` pour une autre base.
`set` remplace l'ensemble des champs : conserver explicitement ceux souhaités.
Le lancement habituel crée uniquement un profil `default` vide s'il est absent.
`PatientContext` prend une copie du profil à l'ouverture et le transmet au pipeline,
qui masque le contexte avant l'appel au modèle. Une nouvelle conversation recharge
le profil en base ; le dossier patient, lui, est relu à chaque tour.

SQLite convient ici parce que les profils, patients et sessions sont locaux et
ne nécessitent pas de serveur. Un fichier JSON serait simple pour un profil unique,
mais moins pratique pour gérer plusieurs profils et des écritures atomiques avec
les autres stockages. PostgreSQL apporterait un serveur à administrer sans besoin
actuel de nombreux utilisateurs simultanés.

## Choix et limites

SQLite vient de la bibliothèque standard Python et conserve les données sans
serveur. Les patients ont leurs propres colonnes ; les collections de textes et
les messages Ollama sont sérialisés en JSON. Chaque opération ferme sa connexion.
L'ajout d'une note prend un verrou avant lecture pour préserver les ajouts concurrents.
Les stockages patients, sessions et profils partagent un fichier, avec des tables
distinctes. L'index documentaire public utilise un autre fichier.

Cette version ne propose pas de migrations de schéma, de comptes médecins,
d'horodatage/auteur des notes ou d'audit des modifications. Les profils ne sont pas
des comptes authentifiés : ils configurent les réponses, sans gérer les accès.
`PatientContext` fournit profil, dossier et extraits via `ContextProvider`.

## Vérification

```bash
python3 -m unittest discover -s tests/memory -p 'test_*.py' -v
```

Les tests utilisent de vrais fichiers SQLite temporaires. Ils couvrent le CRUD,
la réouverture, les erreurs et homonymes, le jeu fictif non destructif, ainsi que
la sauvegarde/reprise des messages, appels d'outils et correspondances PII.
Ils sont également collectés par la suite pytest du projet lorsque pytest est installé.
