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

# 3. Compléter : taille des articles, signaux d'alerte, rattachement
#    administratif par coordonnées (~2 min)
python -m roam_pipeline enrich

python -m roam_pipeline build

# 4. Relire le catalogue

# 4. Relire le catalogue dans le navigateur, avec les photos
python -m roam_pipeline review

#    puis réinjecter le fichier de décisions téléchargé
python -m roam_pipeline apply-review --review ~/Downloads/review-decisions.csv

# 5. Brancher le catalogue dans l'application
python -m roam_pipeline export-app

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

`export-app` écrit en plus `mobile/src/data/catalog.json`, le fichier que lit
l'application. Il ne contient que les lieux effectivement rattachés à une collection : un
lieu que l'application ne pourrait afficher nulle part n'a rien à y faire.

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

### Le rattachement administratif ne vient pas de Wikidata

Wikidata omet souvent `P131` sur les sites naturels : une cascade n'a que ses
coordonnées. S'appuyer dessus laissait huit cent vingt lieux de métropole sans
département, donc hors de toute collection géographique — et le filtre de périmètre les
écartait comme s'ils étaient à l'étranger.

`enrich` part donc des coordonnées, qui elles sont toujours là, en deux passes :

1. **API Adresse**, par lots de cinq cents. Rapide, mais elle cherche l'*adresse* la plus
   proche — et une cascade au fond d'une forêt vosgienne n'en a aucune à portée. Elle
   revient vide sur exactement les lieux qui posaient problème.
2. **API Géo**, point par point, pour le reste. Elle répond par appartenance au polygone
   communal : c'est la bonne question pour un lieu qui n'est pas une adresse. Plus lente,
   mais elle ne traite que les cas restants.

Le code INSEE de commune donne le département, à condition de connaître ses trois formes :
deux chiffres en métropole, une lettre en Corse (`2A004`), trois chiffres outre-mer
(`97411`). Le code de région, lui, est déduit du référentiel local plutôt que repris de la
réponse — il rate les communes mal rattachées.

Ce qui reste sans commune après les deux passes est hors de France ou en mer : un îlot, un
phare isolé. Le filtre de périmètre redevient alors une frontière, et non un symptôme de
données manquantes.

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

### Ce que Wikidata ne sait pas : l'ouverture au public

Wikidata dit si un lieu est **documenté**. Il ne dit pas s'il se **visite**. Cette
confusion produit deux erreurs symétriques : le château d'Hérouville est au catalogue alors
qu'il est fermé, les jardins de Giverny en sont absents alors qu'on y vient du monde
entier.

OpenStreetMap répond à l'autre question. Un lieu qui porte des `opening_hours`, un
`website` ou un `fee` accueille du public — c'est un fait de terrain, posé par des gens qui
sont passés devant, sans rapport avec la notoriété encyclopédique.

`discover` interroge donc OpenStreetMap sur toute la France et en tire deux choses :

- **l'ouverture au public** des lieux déjà au catalogue, en trois états et non deux.
  Confirmé ouvert quand des horaires, un tarif ou un site web l'attestent ; fermé quand
  l'accès est explicitement refusé (`access=private`) ; non renseigné pour tout le reste.

  Cette troisième valeur n'est pas un détail. Sur le premier passage, 62 % des lieux
  rapprochés ne portaient aucun horaire — non parce qu'ils sont fermés, mais parce que
  peu de contributeurs renseignent ce champ. En faire un signal de fermeture aurait signalé
  la moitié du catalogue sans rien apprendre à personne. Seule l'interdiction explicite
  est donc remontée en alerte ; l'ouverture confirmée, elle, s'affiche en positif avec
  ses horaires.
- **`data/out/candidates.csv`** : les sites de visite qu'OpenStreetMap connaît et que le
  catalogue ignore. Par défaut, seuls les candidats sûrs — un signe d'accueil du public
  (horaires ou tarif) **et** un lien encyclopédique. `--all` donne les autres.

### Adopter les candidats

Neuf cents lignes de tableur ne se jugent pas. Il y manque la photo, le score, le nombre
de langues, et surtout les voisins du même thème — on ne décide pas d'un château sans
voir les vingt autres châteaux devant lesquels il passerait.

`adopt` fait donc entrer ces candidats dans le catalogue, pour qu'ils soient jugés là où
tout le reste l'est déjà : dans la page de revue, avec vignette et score.

```bash
python -m roam_pipeline adopt   # puis build, puis review
```

Les faire entrer n'est pas les accepter. À la différence des ajouts de `places.csv`, ils
ne sont **pas épinglés** : le plancher de notoriété leur est appliqué et en écarte une
bonne part sans qu'on ait à les lire. Ceux qui restent portent la mention « Trouvé sur
OpenStreetMap » dans la page de revue, où un filtre dédié permet de ne relire qu'eux.

La commande n'exige pas de recollecter : elle ne va chercher sur Wikidata que les Q-ids
absents du catalogue, les enrichit comme les autres (département, photo, description,
signaux d'alerte) et les ajoute à `places_raw.json`. La liste adoptée est conservée dans
`data/manual/candidates.csv` pour qu'un `fetch` complet la retrouve — et pour qu'une
ligne supprimée à la main le reste.

Le rapprochement se fait par identifiant Wikidata, puis par proximité **conditionnée au
nom**. Sans ce contrôle, la densité fait tout apparier : « château de la Roche » et
« moulin de la Roche » sont à deux cents mètres l'un de l'autre et ne sont pas le même
bâtiment. Le mot qui dit la nature du lieu tranche ; en deçà de quatre-vingts mètres, on
considère qu'il s'agit du même site quoi qu'en disent les noms.

La collecte se découpe en cellules rectangulaires pour tenir dans le temps imparti par
Overpass — et un rectangle autour de la France couvre l'Allemagne rhénane, la Suisse, le
nord de l'Italie, la Catalogne, la Belgique et le sud de l'Angleterre. Le premier jet de
candidats en était plein : Zoo Basel, Pinacoteca di Brera, Museu Picasso. Les lieux du
catalogue, eux, viennent de Wikidata où la nationalité est filtrée à la source, si bien
que le contrôle de périmètre ne s'appliquait qu'à eux.

Le périmètre est donc tenu deux fois, et à deux endroits indépendants : la requête
Overpass est bornée par la frontière française telle qu'OpenStreetMap la trace
(`area["ISO3166-1"="FR"]`), et chaque candidat est ensuite situé par ses coordonnées via
l'API Adresse puis l'API Géo. Sans commune française, il est écarté ; avec, son
département alimente la colonne correspondante de la feuille. Une zone qui ne se résout
pas ne lève aucune erreur chez Overpass — elle renvoie zéro objet, partout — donc une
requête de contrôle sur le centre de Paris précède la collecte et l'interrompt aussitôt
si elle revient vide.

### L'ouverture au public compte dans le score

Le score mesurait jusqu'ici la **documentation** d'un lieu : langues de l'article, taille
du texte, photo, labels. Tous ces signaux disent la même chose sous quatre angles — ce
lieu est-il écrit quelque part. Aucun ne dit s'il se visite.

Le constat de terrain d'OpenStreetMap est donc un poste de score à part entière :

| État | Effet | Pourquoi |
| --- | --- | --- |
| ouvert (`opening_hours`, `fee`, `website`) | `+visitable_bonus` | des gens y accueillent du public |
| refusé (`access=private\|no`) | `−not_visitable_malus` | on ne peut pas y entrer |
| non renseigné | **rien** | l'absence de balise ne prouve rien |

Le troisième cas est le plus important. Les deux tiers des lieux rapprochés n'ont aucun
horaire dans OpenStreetMap ; les pénaliser reviendrait à noter le zèle des contributeurs
plutôt que l'intérêt des lieux.

Le malus fait reculer, il n'exclut pas : un château qu'on ne visite pas peut se
photographier depuis la route, et une alerte prévient déjà le relecteur.

Enfin, l'accueil du public attesté **et** un article francophone donnent droit à une
remise sur le plancher de notoriété (`visitable_floor_ratio`). Le plancher mesure la
documentation ; ces deux signaux réunis disent qu'on y va vraiment. C'est le réglage à
bouger si les découvertes OpenStreetMap meurent toutes au plancher — ou l'inondent.

C'est une **proportion** du plancher du thème, et non un nombre de langues. Un rabais
fixe de trois est modeste sur les musées (12 → 9) et dévastateur sur les mégalithes
(6 → 3) : les thèmes les moins exigeants se retrouvent sans plancher du tout, et c'est
justement là que la remise sert le plus. Sur le premier passage, elle repêchait d'un coup
82 mégalithes et 73 jardins — une amnistie, pas une remise.

Une remise est un pari : un signal de terrain contre un signal encyclopédique. Elle doit
donc rester relisible. Le nombre de lieux qu'elle sauve est journalisé par thème à chaque
`build`, la feuille de revue porte une colonne `entre_par_remise`, et la page de revue un
filtre dédié — de quoi juger ces lieux comme un lot, et remonter le seuil s'ils ne
tiennent pas.

### Les décisions du curateur sont conservées

Elles vivent dans **`data/manual/decisions.csv`**, cumulées d'une revue à l'autre, et
sont réappliquées à **chaque** `build` — pas seulement par `apply-review`. Un lieu écarté
reste écarté, un lieu validé est épinglé et ne peut plus tomber sous un plancher qui
monterait.

```bash
python -m roam_pipeline apply-review --review ~/Downloads/review-decisions.csv
python -m roam_pipeline build          # les décisions sont reprises telles quelles
```

Le fichier est éditable à la main : corriger une ligne suffit à revenir sur un verdict.

### Ajouter un lieu à la main

Le pipeline ratera toujours des lieux : ceux que Wikidata classe mal, et ceux qu'il
documente peu alors qu'on vient de loin les visiter. Le château d'Auvers-sur-Oise et les
jardins de Giverny reçoivent des visiteurs du monde entier sans être documentés en dix
langues — le plancher de notoriété les écarte, et il a tort.

`data/manual/places.csv` est l'échappatoire du curateur. Ces lieux passent outre le
plancher et imposent le thème indiqué :

```csv
wikidata_id,theme_id,note
Q151952,jardins,jardins de Claude Monet à Giverny
```

Pour trouver un identifiant sans l'inventer :

```bash
python -m roam_pipeline suggest-qids "jardins de Giverny"
```

Ces lieux sont recollectés à chaque `fetch`, y compris en reprise partielle : ils ne
dépendent d'aucun thème.

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
