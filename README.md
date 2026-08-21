# Roam

> Collectionner le monde — en commençant par la France.

Roam transforme la découverte de lieux en collection. L'utilisateur visite des châteaux,
des cascades, des villages ; chaque lieu compte dans **plusieurs collections** à la fois —
thématiques, géographiques, labellisées — et fait monter des pourcentages, débloquer des
badges, franchir des niveaux.

Le pari du produit n'est pas la couverture, c'est **la curation** : peu de lieux, mais qui
valent le déplacement. Une collection doit rester finissable, sinon il n'y a plus de jeu.

## État du projet

| Étape | État |
|---|---|
| Concept et charte de curation | ✅ |
| Schéma de base (Postgres + PostGIS) | ✅ validé en local |
| Pipeline de curation (Wikidata + labels) | ✅ écrit, **collecte réelle à lancer** |
| Revue éditoriale du catalogue | ⏳ à faire |
| Application Expo (carte, check-in) | ⏳ à venir |
| Badges et progression | ⏳ à venir |
| Contribution communautaire | ⏳ à venir |
| Social | ⏳ v2 |

## Organisation du dépôt

```
docs/       concept.md, curation-charter.md — lire en premier
db/         schema.sql, bouchons Supabase et script de validation locale
pipeline/   collecte Wikidata, scoring, construction des collections
```

## Démarrage

```bash
# 1. Catalogue : vérifier la config, collecter, construire
cd pipeline
pip install -r requirements.txt
python -m roam_pipeline verify-qids     # ⚠️ à faire en premier
python -m roam_pipeline fetch
python -m roam_pipeline build

# 2. Relire data/out/review.csv à la main, puis
python -m roam_pipeline apply-review --strict

# 3. Charger dans une base locale (Postgres + PostGIS requis)
cd .. && ./db/local/validate.sh
```

## Les trois idées qui structurent le projet

**Les niveaux sont le mécanisme de curation.** Plutôt que de trancher « ce lieu mérite
d'être dans l'app ou non », chaque collection se découpe en trois paliers : ~10
incontournables, ~25 en deuxième ligne, puis les pépites locales. Cela règle d'un coup la
sévérité de la sélection, la densité en zone creuse, et la progression.

**Les labels existants sont la meilleure amorce gratuite.** UNESCO, Plus Beaux Villages,
Grands Sites, Jardins Remarquables : c'est de la curation humaine, officielle et *finie*.
Ils servent à la fois de signal de score et de collection dédiée.

**Le nombre de versions linguistiques de l'article Wikipédia est le meilleur signal de
notoriété gratuit.** Il sépare remarquablement bien le lieu d'intérêt réel du clocher de
village, et il n'est pas manipulable comme un avis Google — lequel ne sert jamais à
sélectionner, au mieux à repérer une anomalie.

## Ce que le pipeline ne fait pas

Il ne publie rien. Il trie, score, et produit une feuille de revue que quelqu'un doit
relire. C'est le coût réel du projet, et c'est aussi sa barrière à l'entrée.
