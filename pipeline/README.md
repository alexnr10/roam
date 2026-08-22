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

# 3. Compléter : taille des articles francophones et signaux d'alerte (~1 min)
python -m roam_pipeline enrich

python -m roam_pipeline build

# 4. Relire le catalogue

# 4. Relire le catalogue dans le navigateur, avec les photos
python -m roam_pipeline review

#    puis réinjecter le fichier de décisions téléchargé
python -m roam_pipeline apply-review --review ~/Downloads/review-decisions.csv

# statistiques du catalogue courant
python -m roam_pipeline stats
```

## Sorties (`data/out/`)

| Fichier | Rôle |
|---|---|
| `places_raw.json` | candidats bruts, avant scoring — c'est aussi ce que `enrich` complète |
| `places.json` | lieux retenus, scorés |
| `collections.json` | collections construites, avec niveaux et rangs |
| `review.html` | **la page de revue** — avec vignettes, c'est par là qu'on relit |
| `review.csv` | la même chose en tableur, pour qui préfère |
| `seed.sql` | seed idempotent pour la base |

## La revue

C'est le cœur du travail, et il se fait dans le navigateur : `python -m roam_pipeline
review` ouvre une page avec **une vignette par lieu**. Un nom seul ne permet pas de juger
deux cents abbayes qu'on ne connaît pas ; une photo, si.

La page se sert en local plutôt que par un double-clic, et ce n'est pas un détail :
ouverte en `file://`, elle ne peut pas mémoriser les décisions, et un travail de plusieurs
soirées se perdrait à la fermeture de l'onglet.

Le filtre **« à vérifier »** regroupe les lieux portant un signal : date de démolition,
altitude qui suggère un accès alpin, absence de photo. Aucun n'est concluant à lui seul —
une ruine se visite, un sommet de 3 800 m peut avoir un téléphérique — mais ils font
remonter en quelques clics des cas qui se noieraient autrement.

Les lieux sont classés par **priorité de revue**, c'est-à-dire leur niveau dans la
collection nationale de leur thème. Relire les 160 premiers — dix par thème — suffit à
obtenir un catalogue jouable.

Chaque carte affiche le détail du score : `151 pts = 94 notoriété (70 langues) + 44
labels + 8 image + 5 fr`. Un classement qu'on ne peut pas auditer ne peut pas être
corrigé.

Le bouton « Télécharger les décisions » produit un CSV que `apply-review` relit. Les
mêmes décisions peuvent aussi être saisies directement dans `review.csv` :

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

- `themes.yaml` — thèmes, classes Wikidata, rayon de validation, plafonds, seuils.
  **L'ordre de déclaration est signifiant** : un lieu qui relève de plusieurs thèmes
  n'entre au catalogue que sous le premier. Les thèmes vont du plus spécifique au plus
  générique — le château de Versailles est aussi un palais, mais c'est d'abord un
  château ; le Louvre est un palais, mais c'est d'abord un musée.
- `labels.yaml` — labels officiels : bonus de score **et** collections dédiées
- `scoring.yaml` — poids, seuils de niveau, règles de taille des collections

Les labels sans propriété Wikidata fiable (`kind: manual`) se saisissent dans
`data/manual/<label>.csv`, colonnes `name,wikidata_id,note`.

### Deux signaux de notoriété, et pourquoi

Le **nombre de versions linguistiques** classe bien le patrimoine bâti : un château de la
Loire est documenté en dix langues, une gentilhommière en une. Il ne classe rien du tout
pour les sites naturels — 79 cascades françaises passent le seuil de deux langues, 12
seulement celui de quatre. À l'intérieur du thème, tout le monde est à égalité.

La **taille de l'article francophone** rattrape exactement ce cas : une cascade documentée
sur vingt mille caractères n'est pas une ébauche de trois lignes. Elle se récupère par
`enrich`, qui travaille sur le fichier déjà collecté — ajouter ce signal ne coûte pas une
nouvelle collecte.

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
