# Mesures : avec ou sans contexte

Question : **le dossier (M3) et les documents publics (R1) améliorent-ils vraiment la
réponse, et à quel prix ?** On compare chaque fonctionnalité à une version sans elle, sur
les questions du scénario, avec le vrai modèle et le vrai chemin de l'appli.

## Protocole

| | |
|---|---|
| Commande | `python -m sensai.obs.compare --runs 2 --out docs/mesures/compare-2026-10-28.json` |
| Code | `sensai/obs/compare.py` (tests : `tests/obs/test_compare.py`) |
| Modèle | `qwen2.5:3b`, `temperature 0.2`, `num_ctx 2048`, `num_predict 128` (`config.toml`) |
| Machine | Intel Core 5 120U, sans GPU, 15 Go de RAM |
| Essais | 2 par question et par variante, chacun dans une **session neuve** (pas d'historique) |
| Isolation | base de démo jetable, aucune écriture d'outil validée, rien dans `logs/` |
| Résultats bruts | [`mesures/compare-2026-10-28.json`](mesures/compare-2026-10-28.json) : chaque réponse (pseudonymisée), latence, tokens |

**Variantes :**

| Variante | Dossier (M3) | Documents (R1) | Rôle |
|---|---|---|---|
| sans contexte | non | non | baseline : le modèle seul |
| dossier | oui | non | apport du dossier |
| dossier + RAG | oui | oui | apport des documents, par rapport à « dossier » |
| dossier, num_predict 32 | oui | non | effet d'un réglage, par rapport à « dossier » |

**Questions et critère de chacune** (expressions régulières dans `score()`) :

| Question | Critère « atteint » |
|---|---|
| scénario : « Mme Dupont peut-elle prendre de l'amoxicilline ? » | **risque nommé** : la réponse parle d'allergie ou de pénicilline (absentes de la question), ne commence pas par « Oui » et n'est pas un refus de répondre |
| notice : « Que dit la notice de l'amoxicilline en cas d'allergie à la pénicilline ? Cite la source. » | **extrait cité** : la réponse cite `[S1]`, l'ANSM, la HAS, la BDPM ou le titre de la notice (pas seulement le mot « notice », qui est dans la question) |

Colonnes en plus : **s'abstient** (« je ne peux pas », « je n'ai pas accès »…) et
**tronquée** (la réponse atteint `num_predict` tokens).

## Résultats du 28/10

| Variante | Question | Critère | Atteint | S'abstient | Tronquée | Latence médiane (s) | Tokens lus (médiane) |
|---|---|---|---|---|---|---|---|
| sans contexte | scénario | risque nommé | 0/2 | 2/2 | 0/2 | 40,7 | 784 |
| sans contexte | notice | extrait cité | 0/2 | 2/2 | 0/2 | 42,7 | 796 |
| dossier | scénario | risque nommé | **2/2** | 0/2 | 0/2 | 20,4 | 307 |
| dossier | notice | extrait cité | 0/2 | 2/2 | 0/2 | 22,5 | 319 |
| dossier + RAG | scénario | risque nommé | **2/2** | 0/2 | 0/2 | 59,2 | 1 040 |
| dossier + RAG | notice | extrait cité | **2/2** | 0/2 | 1/2 | 63,1 | 1 076 |

Aucune erreur technique sur les 16 tours. Sans patient sélectionné, les 7 schémas d'outils
sont proposés au modèle : c'est pourquoi la baseline lit plus de tokens que « dossier » ;
sa latence ne se compare donc pas directement.

### Ce que ça montre

**Le dossier (M3) fait passer le risque de 0/2 à 2/2.** Sans dossier, le modèle ne dit pas
« Oui » : il **s'abstient** (« Je ne peux pas répondre à cette question sans consulter le
dossier du patient »), comme le demande le prompt système. C'est prudent, mais inutile au
médecin. Avec le dossier, les deux essais répondent « Non, [PATIENT_1] ne peut pas prendre
d'amoxicilline en raison des allergies précédentes à la pénicilline… ».

**Les documents (R1) font passer la citation de la notice de 0/2 à 2/2.** Avec le dossier
seul, le modèle répond « Je n'ai pas accès aux notices officielles des médicaments dans ce
contexte » : il ne l'invente pas. Avec le RAG, il cite la notice AMOXICILLINE SANDOZ 500 mg
et `[S1]`.

**Prix du RAG : environ 39 s de plus par tour** (20,4 → 59,2 s sur la question du
scénario), pour environ 730 tokens de plus à lire. À la vitesse de lecture mesurée au bench
(≈ 40 tokens/s), la lecture explique à peu près 18 s ; le reste (encodage de la question par
`nomic-embed-text`, chargement des modèles) n'a pas été décomposé. C'est la raison du mode
`auto`, qui ne lance pas de recherche quand la question ne porte que sur le dossier.

### Erreurs relevées dans les réponses

Un critère atteint ne garantit pas une réponse exacte. En relisant les 16 réponses :

- **mélange des sources** : avec le RAG, le modèle attribue à la notice « urticaire et œdème
  de Quincke », qui viennent du dossier de la patiente ; dans un autre essai, il écrit que le
  dossier parle d'une « éruption cutanée ou un gonflement du visage », formulation de la notice ;
- **détail inventé** : « lors de précédentes utilisations » (le dossier ne dit rien d'une prise
  antérieure d'amoxicilline) ;
- **imprécision** : « ne peut pas prendre de pénicilline » au lieu « d'amoxicilline » ;
- **répétition** : « La notice de la notice de l'AMOXICILLINE SANDOZ ».

Ces erreurs sont reprises dans [Limites](limites.md#modele).

## Effet d'un réglage : `num_predict`

`num_predict` borne le nombre de tokens générés. Même variante « dossier », seul ce réglage
change (`Runtime.configure`, comme la fenêtre « Réglages » du web) :

| `num_predict` | Question | Tronquée | Latence médiane (s) | Exemple de fin de réponse |
|---|---|---|---|---|
| 128 (config) | scénario | 0/2 | 20,4 | « …urticaire et œdème de Quincke en 2019. » |
| 32 | scénario | **2/2** | 17,4 | « …en raison des allergies connues à la pénicilline qui ont » |
| 128 (config) | notice | 0/2 | 22,5 | réponse complète |
| 32 | notice | **2/2** | 18,0 | « …Pour obtenir cette » |

**Effet** : 3 à 4,5 s de gagnés, mais **toutes** les réponses sont coupées au milieu d'une
phrase. Le gain est faible parce que le temps d'un tour est surtout la lecture du prompt,
pas l'écriture de la réponse. **Décision** : garder 128.

**À surveiller** : avec le RAG, une réponse sur deux à la question notice atteint déjà
128 tokens (tableau précédent). Une valeur un peu plus haute éviterait ces coupures ;
elle n'a pas été mesurée.

## Relancer la mesure

```bash
python -m sensai.obs.compare --runs 2                                   # toutes les variantes, ≈ 15 min
python -m sensai.obs.compare --runs 3 --only "dossier" --only "dossier + RAG"
python -m sensai.obs.compare --out docs/mesures/compare-AAAA-MM-JJ.json # garder les réponses
```

Le tableau sort en Markdown ; `--out` garde chaque réponse pour relecture. Le choix du
modèle a sa propre mesure : [Choix du modèle](bench.md) (`bench_models.py`). Les latences
de l'usage réel sont dans les logs et le tableau de bord (`python -m sensai.obs`).

## Limites de cette mesure

- **2 essais** par cas : assez pour voir un écart net (0/2 contre 2/2), pas pour mesurer un
  taux fin. Chaque tour coûte 20 à 60 s, d'où ce choix.
- Les critères sont des **mots-clés**. Une première version comptait le mot « notice »
  même dans « je n'ai pas accès aux notices », et le mot « dossier » dans « sans consulter le
  dossier » : à la relecture des 16 réponses, ces faux positifs ont été retirés, et la mesure
  a été relancée avec le script corrigé. Les réponses brutes restent dans le fichier JSON
  pour qu'on puisse les relire.
- Un critère atteint ne veut pas dire une réponse exacte : voir les erreurs relevées plus haut.
