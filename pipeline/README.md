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
# 1. Résoudre puis vérifier la configuration AVANT toute collecte (réseau requis).
#    Un Q-id erroné ne lève aucune erreur : il renvoie zéro résultat.
#    C'est le bug le plus silencieux et le plus coûteux du pipeline.
python -m roam_pipeline suggest-qids   # propose des Q-ids pour les termes en attente
python -m roam_pipeline verify-qids    # affiche le libellé réel de chaque Q-id retenu

# 2. Collecter les candidats (long : ~15-30 min, WDQS est throttlé)
python -m roam_pipeline fetch

#    Un thème en échec se reprend seul, sans tout recollecter :
python -m roam_pipeline fetch --only chateaux abbayes

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

- `themes.yaml` — thèmes, classes Wikidata, rayon de validation, plafonds, seuils
- `labels.yaml` — labels officiels : bonus de score **et** collections dédiées
- `scoring.yaml` — poids, seuils de niveau, règles de taille des collections

Les labels sans propriété Wikidata fiable (`kind: manual`) se saisissent dans
`data/manual/<label>.csv`, colonnes `name,wikidata_id,note`.

### Deux planchers de notoriété, et pourquoi

`fetch_min_sitelinks` s'applique dans la requête Wikidata ; `min_sitelinks` à la
construction. La distinction n'est pas cosmétique : un seuil appliqué côté serveur ne se
règle qu'en relançant une demi-heure de collecte. En collectant large et en filtrant à la
construction, ajuster un thème coûte une seconde.

`build` affiche d'ailleurs, pour chaque thème, combien de lieux resteraient à chaque
plancher — de quoi régler sur des chiffres réels plutôt qu'à l'estime.

### Ne jamais écrire un Q-id de mémoire

C'est la leçon la plus chère du pipeline : un identifiant erroné ne provoque aucune
erreur, il renvoie zéro résultat et fait disparaître un thème entier en silence. Sur les
33 identifiants de la première version, 12 étaient faux — dont deux inversés entre
monuments classés et inscrits, ce qui aurait faussé tous les scores.

Le cycle est donc : `search` dans la configuration → `suggest-qids` propose des candidats
réels → on choisit → `verify-qids` confirme le libellé. Le choix entre deux entités
proches (« château » et « château fort ») reste une décision éditoriale.

## Tests

```bash
python -m unittest discover -s tests
```

Aucun accès réseau : les tests valident la logique métier (scoring, niveaux, règles de
collection, déduplication, génération SQL), pas Wikidata.
