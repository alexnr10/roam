# Pipeline de curation

Génère le catalogue de lieux et de collections à partir de Wikidata et des labels
officiels. **Le pipeline propose et classe — il ne publie pas.** Tout ce qu'il sort part
en statut `draft` et attend une relecture humaine (cf. `../docs/curation-charter.md`).

## Installation

```bash
cd pipeline
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Utilisation

```bash
# 1. Vérifier la configuration AVANT toute collecte (réseau requis).
#    Un Q-id erroné ne lève aucune erreur : il renvoie zéro résultat.
#    C'est le bug le plus silencieux et le plus coûteux du pipeline.
python -m roam_pipeline verify-qids

# 2. Collecter les candidats (long : ~15-30 min, WDQS est throttlé)
python -m roam_pipeline fetch

# 3. Scorer, construire les collections, exporter
python -m roam_pipeline build

# 4. Relire data/out/review.csv à la main, remplir la colonne `decision`,
#    puis réinjecter les décisions
python -m roam_pipeline apply-review

# statistiques du catalogue courant
python -m roam_pipeline stats
```

## Sorties (`data/out/`)

| Fichier | Rôle |
|---|---|
| `places_raw.json` | candidats bruts issus de Wikidata, avant scoring |
| `places.json` | lieux retenus, scorés |
| `collections.json` | collections construites, avec niveaux et rangs |
| `review.csv` | **la feuille de revue éditoriale** — le vrai livrable |
| `seed.sql` | seed idempotent pour la base |

## La feuille de revue

C'est le cœur du travail. Le pipeline trie et propose ; quelqu'un relit ligne à ligne et
remplit la colonne `decision` :

| Valeur | Effet |
|---|---|
| *(vide)* | en attente — conservé, sauf en `--strict` |
| `keep` | validé tel quel |
| `drop` | écarté du catalogue |
| `promote` | score relevé (`--adjust`, 15 par défaut) |
| `demote` | score abaissé |

`--strict` ne conserve que les lieux explicitement relus. C'est le mode à utiliser pour
constituer le premier catalogue publiable.

## Configuration (`config/`)

- `themes.yaml` — thèmes, classes Wikidata, rayon de validation, plafonds
- `labels.yaml` — labels officiels : bonus de score **et** collections dédiées
- `scoring.yaml` — poids, seuils de niveau, règles de taille des collections

Les labels sans propriété Wikidata fiable (`kind: manual`) se saisissent dans
`data/manual/<label>.csv`, colonnes `name,wikidata_id,note`.

## Tests

```bash
python -m unittest discover -s tests
```

Aucun accès réseau : les tests valident la logique métier (scoring, niveaux, règles de
collection, déduplication, génération SQL), pas Wikidata.
