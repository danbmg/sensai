# Documents publics — R1 et bonus R2

## Préparation et utilisation

Depuis la racine du projet, avec les dépendances de `requirements.txt` installées
et Ollama lancé :

```bash
ollama pull nomic-embed-text
python -m sensai.rag fetch
python -m sensai.rag index
python -m sensai.rag list
python -m sensai.rag search "Allergie à la pénicilline et amoxicilline"
python -m sensai.rag search "Principes de prescription des antibiotiques" --publisher HAS
python -m sensai --demo --mcp --session consultation
```

Dans Sensai :

```text
/rag
/search Précautions avec l’amoxicilline en cas d’allergie à la pénicilline ?
/sources
/rag-filter {"publisher":"HAS","tags":["antibiotiques"]}
/search Principes de prescription des antibiotiques
/rag-filter all
```

En mode `auto`, les questions documentaires ou ambiguës passent par la recherche,
puis les extraits sont ajoutés au contexte du modèle. Les lectures explicites du
dossier seul, avec un patient sélectionné, évitent cette recherche. Par exemple,
« Quelles allergies sont enregistrées ? » utilise seulement le dossier ; une
question sur l'amoxicilline conserve le RAG. Cette détection est volontairement
étroite : les formulations non reconnues conservent la recherche.
`search_mode = "always"` dans `[rag]` permet de chercher à chaque question.
`/search` force toujours une recherche et permet de vérifier la
recherche seule, sans charger le modèle de conversation. `/sources` présente les
derniers extraits effectivement retenus, leurs scores et les références `[S1]`,
`[S2]` utilisables par le modèle. Leurs métadonnées sont restaurées avec la session.
La génération d'une citation correcte reste un comportement à vérifier du modèle.

La notice du corpus est une [notice BDPM/ANSM d'amoxicilline Sandoz](https://base-donnees-publique.medicaments.gouv.fr/medicament/67410088/extrait).
La deuxième source est une [fiche HAS de février 2014](https://www.has-sante.fr/upload/docs/application/pdf/2014-02/fiche_memo_conseils_prescription_antibiotiques.pdf).
La date complète de cette fiche n'étant pas connue, le champ date reste vide et
le mois figure dans son titre. Elle sert à démontrer le fonctionnement documentaire,
sans présenter ce petit corpus comme une base de recommandations actuelles exhaustive.

Le manifeste `corpus/sources.json` décrit uniquement des sources publiques.
`fetch` télécharge explicitement dans `.sensai/corpus` ; les fichiers déjà présents
sont conservés, sauf avec `--overwrite`. Les redirections sont contrôlées et TLS
reste vérifié. Un intermédiaire public supplémentaire est fourni pour le serveur
HAS : voir [sa provenance](../corpus/tls/README.md).
La conversation ne télécharge rien sur Internet.

## Ajouter un document

Ajouter une entrée au manifeste puis relancer `fetch` et `index`, ou fournir un
fichier public déjà téléchargé :

```bash
python -m sensai.rag ingest /chemin/recommandation.pdf --title "Titre de la recommandation" --source "https://www.has-sante.fr/chemin/officiel.pdf" --publisher HAS --date 2025-01-15 --tag antibiotiques --public
```

Remplacer le chemin, le titre, l'URL et la date par ceux du document réel.
`--public` est une attestation de l'opérateur ; il ne remplace pas une vérification
de son contenu. Les URL acceptées sont les domaines officiels ANSM, HAS et BDPM.
Les fichiers SQLite et les documents non déclarés publics sont refusés.
Formats : PDF contenant du texte, HTML, texte UTF-8 et Markdown. Les scans
nécessitent un OCR externe ; les PDF chiffrés et les fichiers de plus de 25 Mo
sont refusés. `--section-id` isole une section HTML, comme la notice dans la page BDPM.

`index` ignore les documents inchangés. Une réindexation prépare les nouveaux
vecteurs avant de remplacer atomiquement l'ancien document : une panne d'Ollama
préserve sa version précédente. `--force` impose le recalcul.
`python -m sensai.rag remove <document_id>` retire un document et ses extraits.

## Fonctionnement et choix

1. `documents.py` extrait le texte en conservant les pages, puis le découpe en
   morceaux de 900 caractères avec un chevauchement de 120 caractères.
2. `embeddings.py` appelle directement l'API Ollama `/api/embed`, avec
   `nomic-embed-text` et ses préfixes `search_document:` / `search_query:`.
   Les lots contiennent quatre textes. Les limites de tokens de l'encodeur sont
   cohérentes (`num_ctx = num_batch = 2048`), les threads limités à deux et le
   modèle déchargé après chaque lot.
   Un cache en RAM, limité aux seize dernières questions, évite les encodages
   répétés dans la même exécution. Il conserve les vecteurs et l'empreinte de la
   question, sans texte de question sur disque ; les erreurs ne sont pas cachées.
3. `store.py` conserve documents, métadonnées, texte et vecteurs float32
   normalisés dans `.sensai/rag.sqlite3`, séparé de `.sensai/memory.sqlite3`.
4. `retrieval.py` applique les filtres, encode la question pseudonymisée, calcule
   la similarité cosinus et retient jusqu'à vingt candidats. Le bonus R2 combine
   70 % de similarité et 30 % de BM25 normalisé (`bm25 / (bm25 + 2)`).
5. Les seuils par défaut sont 0,70 pour le cosinus et 0,50 pour le score final.
   Les copies identiques sont retirées. Au maximum trois extraits sont retenus,
   avec un budget de contexte documentaire de 2 600 caractères, sources comprises.
6. `PatientContext`, dans `memory/context.py`, assemble profil, dossier SQLite et
   documents publics via `ContextProvider`. Le pipeline masque ce contexte avant
   le modèle. Le dossier et le profil ne sont jamais envoyés à l'encodeur ni indexés.

Nomic respecte le modèle prévu par le sujet et fonctionne en local. L'API directe
évite d'ajouter un framework RAG. SQLite avec NumPy suffit à ce petit corpus et ne
nécessite pas un service Chroma ou Qdrant ; le calcul parcourt cependant les vecteurs
en mémoire, ce qui demanderait une autre solution pour un gros corpus.
BM25 reclasse rapidement les résultats en tenant compte des mots exacts, sans
charger un second modèle. Il est moins expressif qu'un reranker neuronal.

## Réglages, erreurs et limites

La table `[rag]` de `config.toml` expose modèle, taille des morceaux, chevauchement,
seuils, nombres de résultats, reclassement, mode `auto`/`always` et budget. Pour isoler un autre index,
ajouter `--index <chemin>` avant la sous-commande RAG et utiliser `--rag-index`
au lancement de Sensai. Par défaut, l'index suit le dossier de `--db`/`--memory-db`.
Un index ne peut pas être le même fichier que la base mémoire.

Les filtres acceptent `publisher` (ANSM/HAS), `tags` (liste), `since` et `until`
(dates ISO complètes). Toutes les étiquettes demandées doivent être présentes.
Un document sans date complète est exclu d'un filtre par période.
`search --no-rerank` conserve le classement cosinus, avec les seuils configurés.

Un modèle absent donne la commande de téléchargement ; un index incompatible
demande une réindexation. Pour changer de modèle, créer de préférence un nouvel
index complet. Une panne d'embeddings pendant une conversation signale la recherche
indisponible et conserve le contexte patient, sans inventer de source.
Une recherche vide le précise explicitement.

Les seuils ont été vérifiés sur quelques recherches françaises de démonstration,
dont deux questions hors sujet ; ce n'est pas une évaluation clinique ni une
garantie de pertinence pour toute question. La détection PII conserve ses limites
documentées dans le README. L'évaluation globale du modèle relève de la partie
prévue pour les autres membres du groupe.

## Fichiers et vérification

`indexing.py` orchestre l'ingestion ; `corpus.py` gère le manifeste et le téléchargement ;
`settings.py` valide la configuration ; `__main__.py` expose les commandes.
Les tests dans `tests/rag/` couvrent extraction PDF/HTML, découpage, filtres,
embeddings, réindexation, classement, budget, sources et séparation des données.
`tests/core/test_cli.py` vérifie également la reprise du patient, du profil et des
sources, avec des modèles simulés.

```bash
python -m pytest -q
```
