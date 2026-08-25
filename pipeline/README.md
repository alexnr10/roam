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

# une fois pour toutes : les contours de la carte de conquête
python -m roam_pipeline export-outlines
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

### Les contours de la carte de conquête

`export-outlines` écrit `mobile/src/data/outlines.json` : les tracés des régions et des
départements, DROM compris, qui permettent à la carte de **colorier** un territoire
conquis. Il ne dépend pas du catalogue et **n'a pas à être relancé après un `build`** —
les frontières administratives ne bougent qu'à la faveur d'une loi. Le fichier est
versionné : l'application n'a rien à télécharger.

Deux exigences le gouvernent, et la seconde n'est pas évidente :

- **la légèreté** — les tracés de l'IGN pèsent 3,6 Mo pour les seuls départements,
  contre 460 Ko une fois simplifiés, pour un détail invisible à l'échelle où on les
  regarde ;
- **la jointivité** — deux départements limitrophes doivent garder *exactement* le même
  tracé de frontière commune. Simplifier chaque polygone dans son coin fait diverger les
  deux versions de quelques mètres, et la carte se fend d'un liseré de fond entre chaque
  aplat de couleur. Invisible sur un fond blanc, criant dès que c'est colorié.

D'où la méthode, empruntée à TopoJSON : reconstruire la topologie (le découpage des
contours en **arcs** partagés), simplifier chaque arc **une seule fois**, puis recoudre
les polygones. Un test vérifie qu'une frontière partagée reste identique des deux côtés.

Source : IGN Admin Express, sous [Licence ouverte](https://www.etalab.gouv.fr/licence-ouverte-open-licence/) — la
mention de source voyage avec les données et s'affiche sur la carte.

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

### Nature et culture : un équilibre à surveiller

Roam promet des **paysages** autant que du patrimoine. Or rien dans les sources ne
défend cet équilibre, et trois mécanismes penchent tous du même côté :

- **Wikidata documente le bâti bien mieux que le naturel.** Un château a un article en
  dix langues, une cascade en a un — en français. Le plancher de notoriété, qui compte
  les langues, écarte donc les paysages plus vite.
- **Le repêchage exige des horaires d'ouverture.** Un musée en a, une cascade jamais.
  Sur les 512 lieux repêchés du premier vrai passage, **onze** étaient naturels.
- **L'offre elle-même est courte** sur certains thèmes : Wikidata ne connaît que 86
  cascades et 34 gorges en France dans les classes interrogées. Ces thèmes sont déjà
  pris presque en entier — ils ne grandiront pas depuis cette source.

Chaque thème porte donc un `kind` (`nature` ou `culture`), et `build` affiche la
répartition. Un décompte visible à chaque construction est le seul moyen qu'une dérive
vers le bâti ne s'installe pas sans qu'on la voie.

### Le repêchage : sortir du plancher, mais pas avec plus de documentation

Le plancher de notoriété ne regarde **qu'un** signal : le nombre de versions
linguistiques. Le musée des impressionnismes de Giverny n'en a que cinq — on y vient du
monde entier sans écrire dessus dans sa langue — et se faisait donc écarter, malgré un
long article français, une photo et des horaires affichés.

Un lieu sous son plancher est donc repêché. À **deux** conditions, et la première n'est
pas négociable :

1. son **accueil du public est attesté** par OpenStreetMap ;
2. son score atteint `rescue_score`.

La première condition est la leçon d'une erreur : une version antérieure repêchait sur le
score seul, et a fait entrer **2 757 lieux d'un coup**. Photo et article francophone valent
treize points d'office, et presque tout monument français en a — dans le bas du classement
le score est presque constant, il ne discrimine rien. Un plancher qui mesure la
documentation ne peut pas être franchi par plus de documentation. Les horaires, eux, sont
une preuve d'une autre nature : un fait de terrain. Le score ne sert que de second filtre,
pour ne pas repêcher tout ce qui ouvre une billetterie.

Le seuil se choisit sur la table que `build` imprime — combien de lieux seraient repêchés,
par thème, à 70, 80, 85, 90, 100, 120 — et non sur un exemple. C'est cette table qui
manquait la première fois.

### Un lieu où l'on ne peut pas entrer n'est pas collectionnable

L'application se joue sur place : on valide en s'y rendant. Les lieux dont OpenStreetMap
dit l'accès explicitement refusé (`access=private|no`) sont donc écartés, et non plus
seulement pénalisés — un malus de 20 points ne suffisait pas à sortir le château
d'Hérouville, qui restait au niveau 2 des châteaux d'Île-de-France.

Le signal est délibéré : `access=private|no` est posé à la main par un contributeur. Mais
il ne veut pas toujours dire ce qu'il semble dire — sur une grotte aménagée, il signifie
qu'on n'y entre pas **seul**, et la visite guidée existe bel et bien. Un lieu qui affiche
par ailleurs des **horaires** est donc considéré comme ouvert : sans cette nuance, la
grotte des Planches et celle de Marsoulas disparaissaient, avec cent six autres.

Un simple **site web** ne suffit en revanche pas à faire l'exception — et c'est un
correctif après coup. Le château d'Hérouville en a un, descriptif et patrimonial, sans
être ouvert au public ; le laisser rouvrir l'accès sur cette seule base l'a fait
réapparaître dans le catalogue, alors qu'il est l'exemple même qui a motivé ce filtre. Un
site web prouve qu'un lieu existe et qu'on en parle ; seuls des horaires prouvent qu'on
peut s'y rendre à une heure donnée.

Deux échappatoires, donc : des horaires, et l'épinglage par le curateur — ce qui se voit
très bien depuis la route reste son choix.

### Un sommet sans preuve d'accès est écarté

Le château d'Hérouville avait un signal explicite pour l'exclure : `access=private`. Un
sommet à 3 000 m n'en a aucun — les sommets ne sont collectés que sur Wikidata, qui ne dit
rien d'un chemin de randonnée ou d'un accès équipé. Il n'y a donc ni preuve qu'on s'y rend
à pied, ni preuve du contraire.

Faute de ce signal positif, l'ambiguïté se résout par un principe assumé : **au moindre
doute, on écarte**. Un sommet du thème « sommets » au-dessus de `alerts.alpine_elevation_m`
(2 500 m) est retiré du catalogue, sauf s'il est épinglé à la main — le cas des sommets
réellement accessibles malgré leur altitude, comme l'Aiguille du Midi et son téléphérique.
Ce que le pipeline ne peut pas prouver, il ne le devine pas : ces lieux reviendront par un
épinglage manuel ou une proposition de la communauté, pas par une supposition.

### Pourquoi ce lieu est-il là, ou pourquoi n'y est-il pas ?

La question revient à chaque revue. Chaque étape du pipeline étant un filtre nommé, il
suffit de suivre un lieu à travers elles :

```bash
python -m roam_pipeline explain giverny
python -m roam_pipeline explain "château d'hérouville"
```

La commande dit le thème, le nombre de langues, le score, l'ouverture au public, le
plancher applicable et la décision enregistrée — puis **l'étape exacte** qui l'a écarté,
ou les collections dans lesquelles il est entré. Un nom introuvable est une réponse aussi :
ni Wikidata ni OpenStreetMap ne l'ont signalé.

### Et pourquoi ce lieu n'est-il NULLE PART ?

`explain` ne connaît que ce qui a été collecté. Il est donc muet sur le défaut
le plus grave possible : un lieu emblématique qui n'est jamais entré. La
Fondation Claude Monet à Giverny en est l'exemple — `explain monet` renvoyait
le musée Marmottan, le musée des impressionnismes voisin et deux homonymes,
mais pas la maison de Monet.

Rien ne signale une telle absence. Chaque clause de `theme_query` — pays,
coordonnées, classe, notoriété — ne lève aucune erreur quand elle n'est pas
remplie : elle retire simplement l'entité du résultat, sans laisser de trace.

```bash
python -m roam_pipeline probe "maison de Claude Monet" "jardins de Giverny"
python -m roam_pipeline probe Q1244161
```

La requête est l'inverse exact de `theme_query` : elle n'exige **rien**, et
rapporte justement ce qui manque.

```
Fondation Claude Monet  (Q1244161)
  pays : France · commune : Giverny
  coordonnées : Point(1.53 49.07)
  langues : 12 · article francophone : oui
  classes déclarées : maison-musée (Q2087181), jardin (Q1107656)
  thème(s) qui la reconnaissent : maisons, jardins
  déjà collectée : NON · proposée par OpenStreetMap : oui
  Rien ne s'y oppose côté Wikidata : relance `fetch --only maisons,jardins`.
```

Quatre verdicts possibles, et ils n'appellent pas le même remède :

| Verdict | Ce qui s'est passé | Remède |
|---|---|---|
| pas de `pays = France` | invisible à **toutes** les requêtes de thème | `data/manual/places.csv` |
| pas de coordonnées | ni carte ni validation GPS possibles | `data/manual/places.csv` |
| aucune classe reconnue | aucun thème ne la collecte | ajouter la classe à un thème — en vérifiant ce qu'elle ramène d'autre |
| sous le plancher de collecte | écartée par la requête SPARQL elle-même | baisser `fetch_min_sitelinks`, ou liste manuelle |

### Quand la classe ne dit rien : les classes génériques

`probe` a rendu son verdict sur la fondation Claude-Monet : chez Wikidata,
elle n'est qu'une **maison** (Q3947). Pas une maison-musée, pas un jardin. Onze
langues, un article francophone, des coordonnées, en France — et pourtant
invisible, parce qu'aucun thème ne collecte une classe aussi large.

Les deux issues évidentes sont mauvaises. Ne rien faire laisse dehors la maison
de Monet. Ajouter `maison` aux classes du thème ramène toutes les maisons de
France.

**Le plancher est la sortie.** Une classe générique se déclare avec un plancher
de collecte qui lui est propre, plus haut que celui du thème :

```yaml
  - id: maisons
    fetch_min_sitelinks: 2
    wikidata_classes: [Q2087181, ...]     # maison-musée, atelier, …
    broad_classes:
      - qid: Q3947                        # maison
        fetch_min_sitelinks: 8
```

À onze langues, on ne parle plus d'un pavillon : la notoriété fait à elle seule
le tri que la classe ne fait pas. C'est le seul filtre disponible quand la
classe ne dit rien.

Le chargement refuse un plancher générique qui ne serait pas **strictement plus
haut** que celui du thème — sans écart, le garde-fou serait décoratif et le
thème se noierait. Ces classes passent par `verify-qids` comme les autres.

> Le bon plancher se calibre sur le volume réel : `fetch --only maisons`
> journalise le nombre de candidats. Trop haut, on rate des lieux ; trop bas,
> la revue devient impraticable.

### Un Q-id listé qui ne rend rien : trois causes, trois gestes

Les listes tenues à la main — ajouts du curateur, candidats adoptés depuis
OpenStreetMap — sont récupérées par `items_query`, qui **exige des
coordonnées**. Une entité qui n'en a pas n'y produit aucune ligne : exactement
comme une entité supprimée.

Les deux tombaient sous le même message, « introuvable sur Wikidata ». Or ils
n'appellent pas du tout le même geste :

| Cause | Ce que c'est | Geste |
|---|---|---|
| **absent** | identifiant supprimé ou redirigé | retirer la ligne de la liste |
| **sans coordonnées** | un lieu bien réel, que Wikidata ne situe pas | l'inscrire dans `data/manual/places.csv` avec ses coordonnées |
| **sans libellé** | entité sans nom exploitable | rien à en tirer |
| **inexpliqué** | tout est là et rien n'est rendu | à signaler, c'est un défaut du pipeline |

Le diagnostic passe par `probe_query`, qui n'exige rien, et le nom du lieu
accompagne chaque ligne : un Q-id nu n'aide personne à décider.

### Wikidata donne un libellé, pas un titre

Les libellés français de Wikidata ne sont pas capitalisés de façon fiable :
« Dune du Pilat » y côtoie « château d'Hérouville » et « musée des
impressionnismes Giverny ». C'est cohérent de leur point de vue — un libellé y
est un syntagme, pas un titre — mais dans une liste de lieux, une minuscule
initiale se lit comme une faute.

Le pipeline capitalise donc **la première lettre, et rien d'autre**, à la
construction de chaque lieu, d'où qu'il vienne. Aller plus loin détruirait les
noms propres internes (« Saint-Cirq-Lapopie ») : il n'existe aucune règle
mécanique pour distinguer « Pont du Gard » de « pont de Normandie ».

Reste le cas où le libellé est exact mais mauvais comme titre. Il se règle à la
main, durablement :

```bash
python -m roam_pipeline rename Q3330248 "Musée des impressionnismes"
python -m roam_pipeline rename                    # liste les renommages
python -m roam_pipeline rename Q3330248 --clear   # revenir au libellé Wikidata
```

Le nom choisi vit dans `data/manual/names.csv` et s'applique à **chaque**
construction — y compris dans la feuille de revue, faute de quoi on relirait un
nom qu'on ne reconnaît plus.

### Un parc d'attractions n'est pas un musée

Marineland est entré au catalogue par le thème « musées », parce qu'un de ses
équipements est classé comme aquarium public et qu'un aquarium public est,
dans la hiérarchie de Wikidata, une sorte de musée. Le rattachement n'est pas
faux ; c'est le lieu qui n'a pas sa place ici.

Le bloc `exclude_classes` de `themes.yaml` liste les classes qui
**disqualifient** un lieu quel que soit le thème par lequel il est entré. La
liste est globale et non par thème : le problème n'est pas qu'un delphinarium
soit mal rangé, c'est qu'il ne doit exister nulle part.

Le marquage se fait à `enrich`, par une requête **bornée** sur les seuls lieux
déjà collectés — comme la remontée administrative, et pour la même raison :
poser ce filtre dans `theme_query` ajouterait un chemin transitif de plus aux
classes les plus volumineuses, ce qui faisait déjà dépasser le délai. Bénéfice
supplémentaire : ajouter une classe à la liste ne demande pas de recollecter,
seulement de rejouer `enrich` puis `build`.

> ⚠️ **Une exclusion par classe est un instrument brut.** Le Jardin des plantes
> abrite une ménagerie ; s'il porte lui-même la classe « parc zoologique », il
> tombe avec elle. `build` nomme donc les lieux qu'il écarte à ce titre, classe
> par classe, et `explain` le dit lieu par lieu. C'est la seule protection
> contre une exclusion trop large — et elle suppose de lire le journal une fois.
> Un lieu épinglé (`keep`) y échappe.

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
