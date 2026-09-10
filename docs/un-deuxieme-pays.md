# Ce que coûterait un deuxième pays

Évaluation mesurée sur le catalogue réel, pas estimée. Elle sert à décider,
et à ne pas redécouvrir dans six mois ce qui a déjà été compté.

## Le principe retenu

**Un catalogue parle d'UN pays.** Une étoile dit un rang dans une collection
nationale : savoir que les plages sont plus belles dans le pays d'à côté
n'intéresse personne qui visite celui-ci. Le pays est donc la partition, pas
une colonne de plus.

**Les labels internationaux d'abord.** Pas de Monuments historiques ni de
Grands Sites pour un pays neuf : on se contente de l'UNESCO, quitte à ajouter
une liste nationale là où elle change tout.

## La revue n'est pas le blocage

Le catalogue a été construit deux fois, avec et sans le moindre verdict :

    sans aucune décision   2 383 lieux
    avec les 3 188         2 079 lieux
    en commun              1 895   (91 % du catalogue final)

    la revue AJOUTE   184 lieux que les filtres écartaient
    la revue RETIRE   488 lieux que les filtres gardaient
    la revue DÉPLACE  204 lieux d'un niveau

Un pays neuf sort donc utilisable au premier build. La revue est du
polissage — du vrai, elle retire un lieu sur cinq — mais elle se fait après,
et pays par pays.

## Ce que coûtent les labels internationaux seulement

    2 079 lieux au catalogue
      1 261 portent au moins un label            (61 %)
        470 sont SOUS le plancher de leur thème — ils n'y sont que par un
            repêchage, dont 326 par un label
          2 seulement tiennent par l'UNESCO

Et surtout : **le thème « villages de caractère » a 290 lieux et ZÉRO classe
Wikidata.** C'est le plus gros thème du catalogue, 14 % du total, alimenté à
100 % par les Plus Beaux Villages et les Plus Beaux Détours. Sans liste
nationale, un pays neuf n'a pas de villages du tout.

D'où l'exception à faire dès le premier pays : la liste équivalente, quand
elle existe sous le même modèle associatif — *I Borghi più belli d'Italia*
pour l'Italie. Coût : une entrée dans `labels.yaml`.

## Ce qui est déjà générique

- `areas` dans le catalogue exporté est **déjà** une hiérarchie pays → région
  → département → commune, en données. L'app ne connaît la France que dans ses
  commentaires : 19 littéraux `'region'` / `'departement'` en tout.
- `outlines.py` (447 lignes de simplification topologique) est générique ;
  seule l'URL source est française.
- Les thèmes sont universels par construction — châteaux, cathédrales, phares,
  cascades ne sont pas français.
- **Le pays des requêtes est une donnée** depuis `geo.country` dans
  `scoring.yaml`. Les six requêtes SPARQL filtrées par pays le reçoivent en
  paramètre OBLIGATOIRE — pas de valeur par défaut, pour qu'aucune ne puisse
  collecter la France en croyant collecter l'Italie.

Et l'Italie tombe bien : *regione* / *provincia*, deux niveaux, 20 et 107 —
la France en a 18 et 101. Le référentiel de `data/reference` fait 121 lignes.

## Ce qui reste à écrire

**Le rattachement administratif — FAIT pour le département.**
`geocode.py` reposait sur `api-adresse.data.gouv.fr` et `geo.api.gouv.fr` :
gratuits, sans clé, et strictement français.

`localisation.py` répond désormais à la question localement, par
point-dans-polygone sur les contours que `geo-layers` télécharge. Mesuré sur
la collecte entière, en effaçant TOUS les départements pour voir ce que le
calcul local retrouve seul :

    10 422 / 10 955 lieux situés, en 3,8 secondes, sans réseau
    99,35 % d'accord avec le verdict des API sur les 10 446 qu'elles situaient
        39 désaccords · 29 non situés

Et les 39 désaccords ne sont pas des erreurs : **trente d'entre eux sont des
objets QUI SONT une frontière** — seize sommets (le Hohneck, le mont Granier,
la cime de la Bonette), douze ponts et viaducs (un pont franchit une rivière,
et une rivière sépare deux départements), deux gorges. Aucune des deux
réponses n'y est plus vraie que l'autre. Deux autres cas — le jardin
d'agronomie tropicale et le lac de Saint-Mandé, dans le bois de Vincennes —
sont ceux où le contour a RAISON contre l'API : le bois appartient à Paris.

Reste la COMMUNE, qui demanderait les trente-cinq mille contours communaux
(46 Mo). Elle vient toujours de Wikidata et, pour la France, des API. Ce n'est
pas bloquant pour un deuxième pays : les sondages italiens montrent que
Wikidata renseigne la commune de tous les lieux testés — Turin, Rome,
Florence, Velletri, Cesena.

Le reste est mécanique : source des contours, référentiel des provinces,
`de_form` en français pour des noms étrangers (« de Toscane », « des
Pouilles »), et recalibration des planchers — `gaps --class` et `weigh`
existent déjà pour ça.

## L'avertissement États-Unis

    contours France     101 départements   724 Ko   ≈ 7,2 Ko par forme
    contours Italie     107 provinces      ~800 Ko  même ordre
    contours USA      3 143 comtés         ~22 Mo   ingérable

`catalog.json` pèse 2,4 Mo pour 2 079 lieux, **embarqué dans le bundle**.

L'architecture « tout embarqué » tient pour l'Italie et **casse pour les
États-Unis** : là-bas il faudra s'arrêter à l'État (50 zones au lieu de 3 143),
ou charger catalogue et contours à la demande. À décider avant d'écrire le
code du deuxième pays, pas après.

## L'estimation

    paramétrage du pays (requête, config, référentiel)      ~1 j   ← FAIT
    rattachement par point-dans-polygone                   2–3 j   ← FAIT
        (département et région ; la commune reste à Wikidata)
    contours étrangers (source + machinerie existante)       ~1 j
    collections partitionnées par pays                     2–3 j   ← FAIT
    app : bascule à la carte, chargement, contours          ~2 j   ← FAIT
    calibration des planchers sur données étrangères       1–2 j
                                                          ─────
                                                           9–12 j

Dont environ six jours payés une seule fois ; le troisième pays coûterait deux
à trois jours plus la calibration.

## Une réserve levée par le curateur

J'avais écrit ici que la curation vaut ce que vaut la connaissance du pays, et
que les jugements portés sur la Cité radieuse ou le Familistère n'existeraient
pas pour l'Italie. **C'est faux, et le curateur l'a corrigé** : la revue se
fait sur les avis Google et les photos, pas sur une connaissance personnelle
du terrain. C'était déjà le cas pour la France. La méthode se transporte donc
telle quelle, et le catalogue italien sera relu aussi bien que le français.

Ce qui reste vrai, en revanche, et sans rapport avec le curateur : sans les
labels nationaux, la COLLECTE italienne repose entièrement sur la
documentation Wikipédia — c'est le mode de défaillance corrigé sur les forêts,
où « forêt domaniale » ne voyait même pas Fontainebleau. Les planchers d'un
pays neuf méritent donc plus d'attention que les français n'en ont reçu au
départ. C'est le travail de `gaps`, pas celui de la revue.

## Ce que l'Italie a répondu, mesuré

`gaps --pays Q38`, plancher 12 langues : **11 914 lieux notoires non
collectés**. Le chiffre est trompeur, et c'est la première leçon.

    communes, frazioni, anciennes communes, provinces,
    municipi, villes, communes éparses                    8 750
    batailles, fleuves, Grands Prix, éditions sportives,
    stades, stations de métro, gares                        589
                                                         ──────
                                                          9 339   (78 %)

Wikidata documente chaque *comune* italien en douze langues et plus : ce sont
des articles produits en série, pas des lieux de visite. Le vivier réel est
d'environ **2 575 lieux**, à un plancher déjà très haut.

### Un « ✗ » de `gaps` ne veut pas dire « invisible »

`census()` marque `✗` une classe qui n'est pas ÉCRITE dans `themes.yaml`. Or
`theme_query` remonte les sous-classes (`P31/P279*`) : une classe italienne
rangée sous une classe déclarée est collectée quand même. Six lignes du
recensement paraissaient être des angles morts ; `probe` les a démenties.

    palais Carignan (Q19829) — palais muséal, palais urbain, palazzo,
                               musée national italien
        ✓ monuments via « palais »   ✓ musees via « musée »
        ✓ maisons   via « maison »

    basilique Santa Maria Novella (Q51175) — basilique mineure, musée d'un
                               organisme public, musée, musée religieux
        ✓ cathedrales via « basilique mineure »   ✓ musees via « musée »

Les quatre classes « musée » propres à l'Italie et `palazzo` sont donc déjà
couvertes. Et le dédoublonnage tranche bien : le palais Carignan entre par
`maisons` via une classe GÉNÉRIQUE, qui perd contre une classe précise ; il
part en `musees`, déclaré avant `monuments`. Santa Maria Novella part en
`cathedrales`, déclaré avant `musees`. Deux bons classements sans rien
toucher.

Leçon d'outil : lire `gaps` comme une liste de SUSPECTS, et confirmer chacun
par `probe` avant de déclarer une classe.

### Le seul vrai angle mort : les églises

    église (Q16970) — lieux situés en Italie, par plancher

      ≥0     ≥1     ≥2    ≥3    ≥4    ≥6   ≥8  ≥10  ≥12  ≥15  ≥20
    56648  26882  13199  3699  2125  1007  637  372  264  156   78

Preuve par un cas : *Santa Maria Novella de Chiusi* (Q3673502) ne déclare que
« église », et `probe` répond « thème(s) qui la reconnaissent : AUCUN ».

`themes.yaml` écarte Q16970 explicitement, et la note dit pourquoi : le thème
`cathedrales` ne prend que ce qui porte un TITRE. C'est juste en France. En
Italie, le patrimoine religieux majeur s'appelle *chiesa* — et les grandes
basiliques florentines s'en tirent par leur titre de basilique mineure, mais
pas le reste.

La falaise est entre 2 et 3 langues (13 199 → 3 699). À 8, il reste 637
églises italiennes : borné, et du même ordre que ce que les autres classes
génériques rapportent.

### La conséquence architecturale, qui n'était pas prévue

**`themes.yaml` doit devenir propre à chaque pays**, pas seulement le scoring.
La même classe doit être ÉCARTÉE en France et COLLECTÉE en Italie, ce qu'un
fichier global ne peut pas dire.

Bonne nouvelle : ça ne demande aucun code. `--config` désigne déjà un
DOSSIER — `config/fr/` et `config/it/` suffisent. C'est aussi pour cela que
`config_floors()` ne relit plus le dossier par défaut : elle aurait affiché
les planchers français sous un tableau italien.

### Les lieux qui appartiennent à deux pays

`montagne : 227 absents sur 244` — la seule ligne du recensement où les
absents ne font pas le total. **Dix-sept montagnes italiennes sont déjà dans
la collecte française** : le Mont Blanc, le massif du Mont-Cenis, le mont
Clapier, le mont Chaberton. Elles portent deux pays chez Wikidata.

**Décision du curateur : ils appartiennent aux DEUX.** Qui valide le Mont
Blanc le valide en France et en Italie. C'est le bon choix pour un guide —
on y est allé, la frontière est une abstraction — et il a une conséquence
technique : le pays n'est pas un attribut du lieu mais une APPARTENANCE
multiple, et une visite se propage à toutes les collections nationales qui
contiennent le lieu. La question vaut pour tout l'arc alpin et les Pyrénées.

## La partition par pays, telle qu'elle est faite

**L'entonnoir n'a pas changé d'une ligne : il tourne une fois par pays.**
`build_all` groupe les lieux par pays et déroule pour chacun la construction
entière — plancher, plafond communal, plafond de thème, dédoublonnage,
niveaux, repêchage par territoire. Tout ce qui CLASSE se fait donc à
l'intérieur d'un pays, ce qui est exactement la promesse : le Colisée ne
dispute pas sa place au Pont du Gard, et douze châteaux italiens très
documentés ne repoussent aucun château français hors de sa collection
nationale (c'est un test).

**Le pays d'un lieu, VIDE, veut dire « celui du dépôt ».** Ce n'est pas une
paresse : tant qu'un seul pays est collecté, écrire son code sur chacun des
onze mille lieux n'apprendrait rien et ajouterait un champ constant à la
collecte versionnée. Le jour où un lieu d'un autre pays entre dans le dépôt,
c'est lui qui porte la mention — et lui seul. La collecte française n'a donc
pas bougé d'une ligne.

**Le suffixe d'adresse n'apparaît que s'il désambiguïse.** Un catalogue d'un
seul pays garde `theme-chateaux` ; dès qu'un second arrive, tout devient
`theme-chateaux-fr` et `theme-chateaux-it`. Deux exceptions à la règle du
suffixe : « Le meilleur de France » porte déjà son pays dans son adresse
(`geo-country-fr`), et `tiers.csv` est indexé par Q-id, donc un renommage
d'adresses ne coûte aucune revue.

Ce qui reste, côté application : elle affiche aujourd'hui TOUTES les
collections du catalogue. Avec deux pays, il lui faudra n'en montrer qu'un à
la fois — et c'est là que se posera la question du chargement à la demande,
celle que les 22 Mo de contours américains rendent inévitable.

## Le sélecteur de pays, tel qu'il est fait

Un catalogue par pays, **un seul chargé à la fois**, et deux exigences
opposées à tenir ensemble : pouvoir changer de pays depuis chez soi — on
prépare un voyage avant de partir — sans que ce soit une corvée.

    France → Italie   186 ms   premier chargement
    Italie → France    89 ms   déjà en main, aucune requête
    France → Italie    70 ms   déjà en main
    Italie → France    76 ms

Mesuré sur l'application construite, en attendant que le compte de lieux
change à l'écran — pas un délai fixe. Un pays déjà visité revient donc sans
rien demander à personne.

**Le catalogue est un lien vivant.** `places`, `collections`, `themes` et
`areas` sont des `let` exportés : en modules ES, une importation est un lien,
pas une copie, et les quinze modules qui les lisent voient le nouveau
catalogue sans changer d'une ligne. Ce qui ne suit pas tout seul, ce sont les
valeurs dérivées UNE FOIS au chargement — les étoiles, les noms de région, la
table des départements — d'où un abonnement `surChangement` auquel ces
modules-là se raccrochent. Deux tests échouent si on le retire : c'est le
pire des défauts, une carte italienne notée à la française, qui ne plante pas.

**Les écrans s'abonnent au catalogue** par `useCatalogue`, un
`useSyncExternalStore` sur la version. La première version remontait la
navigation à chaque bascule ; c'était plus simple et c'était faux — remonter
la pile en pleine promenade rend la carte à son point de départ, soit
exactement le contraire d'invisible.

Les visites et les envies, elles, ne bougent pas : indexées par identifiant de
lieu, qui est mondial. Revenir en France, c'est retrouver son carnet intact.

**Le sélecteur est invisible tant qu'un seul pays est disponible.** Un choix à
une entrée n'est pas un choix, c'est un encombrement — même règle que pour le
suffixe des adresses de collections.

### La bascule est INVISIBLE : elle se fait à la carte

Pas de menu, pas de question. On se promène, on passe la frontière, le
catalogue suit — c'est la carte qui est déjà le geste. Mesuré sur
l'application construite, en pilotant la carte de Paris à Rome puis retour :

    Paris                    2 081 lieux, 203 collections
    → Rome                       3 lieux,   1 collection    (it.json téléchargé)
    → Lyon                   2 081 lieux, 203 collections   (aucune requête)
    → Naples                     3 lieux,   1 collection    (aucune requête)

    réseau total : index.json + it.json

Deux règles font tout le confort, et elles sont pures et testées. **On ne
bascule que si l'on est SORTI du pays courant** : les emprises se chevauchent
le long d'une frontière, et sans cette hystérésis, se promener autour du mont
Blanc ferait clignoter le catalogue à chaque mouvement de doigt. **On ne
bascule que vers UN seul candidat** : au-dessus d'un point qui appartient à
deux voisins sans appartenir au courant, deviner serait pire que ne rien
faire.

Les catalogues sont servis par le DÉPÔT, en HTTPS et gratuitement :
`catalogues/index.json` dit ce qui existe et où, `catalogues/<pays>.json`
porte chacun. Une version du catalogue va donc toujours avec la version de
l'application qui la lit. `export-app` les écrit.

### Les contours suivent le pays

`<pays>-contours.json` voyage avec le catalogue. Ceux du pays de départ
restent EMBARQUÉS — la carte de conquête doit fonctionner au premier
lancement, sans réseau. Ils sont écrits par `export-outlines`, qui copie le
fichier de l'application plutôt que de le régénérer : deux tracés d'un même
pays finiraient par diverger, et une frontière qui bouge d'un mètre entre deux
versions se voit à l'écran — c'est tout le sujet de la jointivité.

**Un pays sans contours n'est pas une erreur.** `outlinesFor` rend `null` et
la carte de conquête retombe sur la liste, qui dit la même chose sans dessin.
C'est ce qui permet d'ouvrir un pays avant d'avoir tracé ses frontières.

Trois défauts trouvés en regardant l'écran italien, et corrigés :

- l'onglet du pays annonçait « France » — écrit en dur — au-dessus d'un
  catalogue italien ;
- les échelles dessinables étaient une CONSTANTE de module, figée au
  démarrage : la carte aurait proposé de colorier des départements qui
  n'existent pas ;
- « Aucune département au catalogue » — l'accord suivait le genre de la
  région, pas celui du niveau affiché.

Vérifié sur l'application construite : en Italie, l'onglet dit « Italie », les
pastilles de thème ne montrent que « Monuments », et le message d'échelle vide
s'accorde. En France, rien n'a bougé.

## L'objectif n'est pas le volume

Le catalogue italien ne doit pas égaler le français en nombre. L'objectif,
posé par le curateur : **les lieux les plus importants, répartis dans toutes
les régions.** Ce qui suit chiffre ce que la configuration ACTUELLE
produirait ; c'est un point de départ à borner, pas une cible.

Et la répartition n'est pas donnée d'avance. Sur le catalogue français, elle
va de 273 lieux à 8 :

    Occitanie 273 · Auvergne-Rhône-Alpes 262 · Nouvelle-Aquitaine 232
    PACA 200 · Île-de-France 154 · Grand Est 153 · Bretagne 148
    …
    Corse 51 · La Réunion 42 · Guadeloupe 22 · Martinique 12 · Mayotte 8

Trois leviers existent déjà pour la corriger, et aucun n'est utilisé à fond :
`min_per_departement` (un plancher par territoire, à 12), `max_per_departement`
(un quota, posé sur les seuls jardins) et `catalogue_cap` (un plafond par
thème, posé sur les seules cathédrales). Pour l'Italie, ce sont eux qui
décideront de la taille, pas l'offre.

## Éviter une revue de trois mille lieux

La revue française a coûté 3 188 décisions. Décomposées :

    2 080  sur des lieux qui SONT au catalogue        (la validation)
      792  des `drop` — c'est-à-dire pourquoi ils n'y sont pas
      316  sur des lieux qui n'y seraient pas entrés de toute façon

Deux conséquences pour l'Italie.

**Un catalogue plus petit fait une revue plus petite**, à peu près
proportionnellement. Viser mille lieux, c'est viser mille à mille cinq cents
décisions.

**Relire par RÉGION plutôt que d'affilée.** Sur un classement national, le
haut de liste est occupé par Rome, Florence et Venise : relire dans l'ordre,
c'est relire les régions riches et se lasser avant le Molise. Vingt régions à
cinquante lieux, c'est vingt séances courtes, et surtout c'est voir le haut de
CHACUNE — ce qui est exactement l'objectif.

La page de revue porte donc un sélecteur de région, à côté de celui des
thèmes. Il sert déjà pour la France.

## Combien de lieux ferait le catalogue italien ?

**Environ 3 000, dans une fourchette de 2 600 à 3 600**, à configuration
égale. Le raisonnement, parce que le chiffre seul ne sert à rien.

> Ce chiffre a été révisé. La première estimation, 2 500, reposait sur un
> vivier italien mal compté — `gaps` sommait des lignes et non des lieux. Une
> fois l'outil corrigé et le recensement refait à six langues, le vivier
> italien vaut **1,68 fois** le français, et l'estimation monte d'autant.

### La taille d'un catalogue n'est pas fixée par l'offre

    collecte française                              10 955 lieux
    au-dessus du plancher de leur thème               3 659
    au catalogue                                      2 079
        dont repêchés SOUS le plancher                  470

**Mille cinq cent quatre-vingts lieux franchissent leur plancher et sont
coupés quand même** — par le plafond communal, le plafond de thème, le
dédoublonnage, le filtre d'accès et la revue. Le plancher n'est pas la
contrainte qui mord : ce sont les plafonds.

### C'est donc la grille administrative qui donne l'ordre de grandeur

    France   101 départements · médiane 16 lieux · moyenne 20,6 · max 64
    Italie   107 provinces

À moyenne égale, 107 × 20,6 ≈ **2 200** — c'est le PLANCHER, celui d'un pays
qui n'aurait pas plus à offrir que la France.

Mais la plupart des thèmes n'ont aucun `catalogue_cap` : un vivier plus riche
se traduit donc bien par un catalogue plus gros. D'où le calcul, chaque
facteur étant mesuré sur la France :

    lieux au-dessus de leur plancher, France              3 659
    × 1,68 (vivier italien)                              ≈ 6 150
    × 65 %  taux de conservation HORS revue
            (2 383 au catalogue sans aucun verdict)      ≈ 4 000
    − 10 %  plafonds communaux, plus mordants dans
            les villes d'art que dans Paris seul         ≈ 3 600
    × 87 %  une revue d'égale sévérité (2 079 / 2 383)   ≈ 3 100

D'où **3 000**, et une fourchette large — 2 600 à 3 600 — parce que chacun de
ces facteurs est transposé et non observé.

### L'offre italienne vaut 1,68 fois la française — mesuré

    ⚠ Le total de `gaps` sommait les colonnes « absents » de chaque classe.
    Une entité porte plusieurs classes — la basilique Santa Maria Novella est
    à elle seule « basilique mineure », « musée », « musée d'un organisme
    public » et « musée religieux » — et se comptait donc quatre fois. La
    première lecture, « le double de l'offre française », était fausse pour
    cette raison. Le total compte désormais des LIEUX distincts.

    L'écart n'est pas uniforme, et c'est ce qui le rend traître : nul sur les
    communes, qui ne déclarent qu'une classe ; maximal sur le patrimoine,
    c'est-à-dire précisément là où on lit le tableau pour décider.

Recensement italien à six langues : 24 065 lignes, dont

    communes, frazioni, établissements humains,
    anciennes communes et municipalités                    15 204
    gares, haltes, métros, fleuves, batailles               1 658
                                                          ──────
                                                           16 862   (70 %)

Le recensement refait avec le total corrigé donne **6 318 lieux distincts
pour 8 246 lignes**, quatre classes n'ayant pas pu être examinées — et pas
n'importe lesquelles : commune, frazione, église et montagne, les quatre plus
fournies. L'arithmétique boucle exactement :

    8 246 lignes vues + 15 819 lignes des quatre classes = 24 065

Le vivier PATRIMONIAL distinct se reconstitue donc ainsi :

    lieux distincts vus                                   6 318
    − bruit visible (établissements humains, gares,
      métros, fleuves, batailles, haltes, anciennes
      communes et municipalités)                        − 2 792
    + églises (952) et montagnes (797), mesurées au
      passage précédent                                 + 1 749
                                                        ───────
    vivier patrimonial italien à six langues              5 275
    vivier français à six langues                         3 144
                                                        ───────
    rapport                                                1,68

Les étoiles, elles, se normalisent d'elles-mêmes — les niveaux sont
proportionnels à leur collection, pas absolus — ce qui est exactement l'effet
recherché : trois étoiles en Italie voudront dire « le haut de l'Italie ».

### Ce que le recensement à six langues a montré de plus

**Les églises passent de 246 à 952.** L'angle mort ne s'élargit pas
linéairement : c'est la classe qui grossit le plus vite quand le plancher
descend, et c'est bien celle qui décide du catalogue italien.

**La piazza est un thème que la France n'a pas.** `place (Q174782)`, 112
absents — Piazza Santa Trinita, Piazza San Sepolcro. En France une place est
un carrefour ; en Italie c'est une destination, et le catalogue n'a aucun
thème pour la recevoir. À trancher au moment d'écrire `config/it/`.

**`palazzo` (Q2651004), 189 : COUVERT.** Le cas propre a tranché — le palais
des Conservateurs (Q64103) ne déclare QUE `palazzo`, et `probe` lui donne
« ✓ monuments via palais ». La classe est donc sous `palais` (Q16560). Le
palais Carignan ne prouvait rien, déclarant aussi « palais urbain » ; il
fallait une entité à classe unique.

**Deux classes utiles apparaissent, déjà collectées** : `château fort` (131)
et `lac` (106). Elles n'étaient pas visibles à douze langues.

### Les classes indécises, sondées une à une

    palazzo (Q2651004)             189   COUVERT — palais des Conservateurs,
                                         classe unique, ✓ monuments via palais
    musée privé (Q614316)          105   le CAS est couvert, la classe non
                                         prouvée : le Museo Egizio déclare
                                         cinq classes dont « musée national »
                                         et « musée archéologique ». Enjeu
                                         faible — un musée notable en déclare
                                         presque toujours une autre.
    villa (Q3950)                  102   COUVERT, mais SEULEMENT au-dessus de
                                         8 langues (voir ci-dessous)
    ensemble architectural (98)          non sondé
    place (Q174782) (112)                non sondé — question de THÈME plutôt
                                         que de classe

### Les villas italiennes tombent dans un trou de quatre langues

La villa Torlonia de Rome ne déclare QUE `villa` (Q3950), et sa seule route
est « ✓ maisons via **maison** — exige 8 langues ». Or `maisons` AFFICHE à
partir de 4. Entre 4 et 8 langues, une villa italienne est donc affichable
par le thème et collectée par personne.

Le plancher de 8 est celui de la classe GÉNÉRIQUE `maison` (Q3947), et il a
été posé pour la France, où le collecter plus bas ramènerait tous les
pavillons du pays. En Italie, `villa` n'est pas une catégorie d'habitation
mais de monument — les villas médicéennes et palladiennes sont au patrimoine
mondial.

Le remède, dans `config/it/`, est de déclarer `Q3950` en classe PRÉCISE du
thème plutôt que de compter sur la porte générique : le plancher redevient
celui du thème, et l'entrée cesse d'être marquée `via_broad_class`, ce qui
lui faisait perdre tout dédoublonnage contre une classe précise d'un autre
thème.

C'est le DEUXIÈME exemple, après les églises, d'une décision juste pour la
France et fausse pour l'Italie. Deux suffisent à confirmer que `themes.yaml`
doit être propre à chaque pays.

    python -m roam_pipeline gaps --pays Q38 --class Q3950

donnera le plancher, comme Q4421 l'a donné pour les forêts.

### Le recensement peut perdre ses classes les plus grosses

L'unique lot en échec de la mesure italienne portait commune, frazione,
église et montagne. La réponse de WDQS n'était pas refusée mais TRONQUÉE
(JSON incomplet), et c'est d'autant plus probable que la classe est fournie :
le recensement perd donc en priorité ce pour quoi on le lance.

`gaps` réessaie désormais classe par classe après un lot perdu — une seule
reste alors hors de portée, pas ses trois voisines.

## `config/it/` est écrit — ce qu'il contient, ce qu'il attend

Une SURCOUCHE, pas une copie. `config/it/*.yaml` ne dit que les écarts, et
`fusionner()` les pose sur la configuration du dépôt :

- deux dictionnaires fusionnent en profondeur ;
- une liste d'objets portant un `id` fusionne par cet identifiant, et
  `retire: true` en enlève un ;
- tout le reste remplace, `null` explicite compris — c'est ainsi qu'on retire
  un plafond.

    python -m roam_pipeline --pays-config it <commande>

L'option se place avant ou après le nom de la commande : argparse ne la
reconnaît nativement qu'avant, et refuse le reste par un « unrecognized
arguments » qui ne dit pas pourquoi. Elle est donc rendue à chaque
sous-commande — sans défaut, sans quoi la sous-commande reposerait le sien
par-dessus la valeur donnée avant elle, et chargerait la France en silence.

`--pays-config` et non `--pays` : ce dernier existe déjà sur `gaps` et
`label-probe`, où il prend un Q-id et ne fait que MESURER un pays sans rien
engager. Celui-ci engage tout.

**Les données d'un pays ajouté vont dans `data/<code>/`.** Sans cela,
`--pays-config it` collecterait l'Italie par-dessus la France : même
`places_raw.json`, même `decisions.csv`. Une revue de deux mille lieux
disparaîtrait sous une collecte étrangère, sans un avertissement. La France
reste où elle est — ses fichiers sont versionnés à leur place depuis le début,
et les déplacer demanderait de reconstruire le catalogue pour vérifier qu'il
n'a pas bougé d'un octet. Le jour où un troisième pays arrivera, la symétrie
vaudra ce déplacement.

Vérifié : la France est inchangée, et le build est déterministe — deux
constructions d'affilée rendent le même octet.

### Ce que `config/it/` contient

| fichier | ce qu'il dit |
|---|---|
| `scoring.yaml` | Q38 / IT / Italie / d'Italie, et les contours des 110 provinces |
| `themes.yaml` | `villages` rendu par la liste italienne, `forets` et `cirques` retirés, `maisons` sans liste d'État, les églises entrent et leur plafond tombe |
| `labels.yaml` | quatorze listes françaises retirées, l'UNESCO gardée, les Borghi più belli ajoutés |

Les contours viennent d'`openpolis/geojson-italy`, découpage officiel de
l'ISTAT, vérifié : 110 provinces, 5,4 Mo. Les noms de propriétés ne se
devinent pas — `prov_istat_code`, `prov_name`, `reg_istat_code` — et c'est à
peu près tout ce qui change d'un pays à l'autre.

### Le référentiel italien — FAIT

`data/reference/it/regions.csv` et `departements.csv` : vingt régions, cent dix
provinces. Codes, rattachements et noms italiens viennent du GeoJSON de l'ISTAT
— celui-là même que `geo-layers` télécharge. Ce qui est écrit à la main, et
qu'aucune donnée ne porte, ce sont les noms FRANÇAIS et leur complément :
« des Pouilles » ne se dérive pas de « Puglia ». Le générateur est versionné :
`python scripts/referentiel-it.py`.

**Les collections italiennes portent des noms français** — « Châteaux de
Toscane », « Le meilleur du Latium ». C'est une décision du curateur : le
catalogue est écrit en français. Le jour où l'application proposera d'autres
langues, ce sont ces tables qui auront leur équivalent, pas la mécanique qui
les lit — `geo.py` ne connaît ni langue ni pays, il lit un dossier.

Les exonymes sont posés seulement là où le français en a un d'usage : on écrit
Florence, Padoue, Plaisance et Côme, mais personne n'écrit « Bellune » pour
Belluno. Sur-franciser est une faute aussi sûre que sous-franciser.

⚠ **La source porte le découpage sarde d'avant 2016** : quatre provinces
supprimées depuis y figurent encore, sous des noms de promotion touristique
(« Gallura Nord-Est Sardegna »). Elles retrouvent ici leur nom administratif,
que la source connaît par son sigle — OT, CI, VS. Les polygones, eux, pavent
bien la Sardaigne : aucun lieu ne restera sans province.

`geo.py` lit maintenant `data/reference/<code>/`, la France restant à la
racine. `utiliser_pays()` est appelé une fois, au démarrage, et vide les
caches — sans quoi on obtiendrait des départements français et des provinces
italiennes selon l'ordre des appels.

Et `area("country")` ne rend plus la France par défaut hors de France : c'était
intituler « Le meilleur de France » des lieux italiens, une faute qui ne plante
pas et qu'on lirait dans l'application.

### Ce que la revue française apprend sur les labels

Mesuré sur les 3 191 verdicts enregistrés, par label :

| liste | gardés | écartés | |
|---|---:|---:|---|
| Plus Beaux Villages | 185 | **0** | jury |
| Plus Beaux Détours | 102 | **0** | jury |
| Grands Sites de France | 54 | **0** | jury |
| Forêts d'Exception | 11 | **0** | jury |
| Monuments historiques classés | 920 | 273 | inventaire — 22 % |
| Monuments historiques inscrits | 373 | 187 | inventaire — 31 % |
| Maisons des Illustres | 200 | 76 | inventaire — 26 % |

Les listes de JURY ne se relisent pas : une commission a déjà fait le travail.
Les inventaires d'État, si — ils disent « protégé », pas « vaut le voyage ».

`garde_d_office: true` dans `labels.yaml` pose la règle, label par label et sur
la mesure, jamais sur la catégorie « officiel ». Un verdict enregistré
l'emporte toujours : une liste propose, le curateur dispose.

L'UNESCO n'est pas déclaré, et c'est un cas intéressant : huit écartés, mais
aucun pour sa qualité. Ce sont des inscriptions qui ne sont pas une visite —
« Monuments romains et romans d'Arles », « Les Plages du Débarquement » — et
des doublons entre thèmes. Le pipeline ne sait pas distinguer une inscription
d'un lieu ; tant qu'il ne le sait pas, ces huit-là valent d'être relus.

Effet sur la France : **aucun**. Les 352 lieux concernés étaient tous déjà
relus et gardés — le catalogue est identique à l'octet. La règle vaut pour ce
qui ENTRE ensuite, et pour les listes équivalentes des autres pays.

### Ce qui refuse poliment hors de France — audité avant la première collecte

Trois dépendances françaises étaient sur le chemin de `fetch` → `enrich`, et
aucune ne se serait signalée :

**Les API de l'État français**, en secours du rattachement. Interrogées sur des
coordonnées italiennes, elles ne répondent pas « hors de mon territoire » :
elles rendent la commune française la plus proche, ou rien. La passe
« communes » les aurait appelées pour CHAQUE lieu italien — les contours
locaux, eux, ne donnent pas la commune. Elles sont maintenant gardées par le
code du pays, et le disent dans le journal.

⚠ **La conséquence écrite ici était fausse, et le premier build l'a prouvée.**
« Hors de France, la commune vient de Wikidata seule » : non. `resolve_admin`
ne remplit QUE le département depuis Wikidata ; il n'écrit ni `commune_code` ni
`commune_name`, et il n'existe que deux endroits dans tout le pipeline qui les
écrivent — l'API française, et les contours. Le premier catalogue italien est
donc sorti avec **zéro commune sur 2 563 lieux**. Trois conséquences, toutes
visibles dans sa sortie :

- `max_per_commune: 6` n'a pas mordu une seule fois — la colonne `commune` du
  tableau en entonnoir est identique à `plancher` pour les vingt et un thèmes.
  Rome garde ainsi quatre-vingts églises, là où le même plafond en retire cent
  vingt à Paris.
- la commune manque à chaque fiche de l'application, qui retombe sur la
  province.
- la maille la plus fine de la carte de conquête est vide.

**Corrigé** : `enrich` rattache maintenant la commune par point-dans-polygone
quand une couche communale existe, avant tout appel d'API. `config/it/`
déclare celle de l'ISTAT — 7 896 communes, 35 Mo, `com_istat_code` /
`name` / `prov_istat_code`. Mesuré ici : 2,8 s de chargement, 231 Mo en
mémoire, 12 000 points rattachés en 0,7 s, et huit points de contrôle justes,
y compris les pièges (Cinque Terre → Riomaggiore, les trulli → Alberobello).
La France ne déclare pas de couche communale et garde ses deux API : rien n'y
change.

**`discover`** délimite la France en dur, par un rectangle et par une zone
`ISO3166-1="FR"`. Il ne plantait pas : il aurait proposé des lieux français
dans un catalogue italien, mêlés au même fichier de candidats. Il refuse
désormais, en nommant la raison.

**`normalize_dept_code`** complète à deux chiffres — un usage INSEE. Les codes
ISTAT en font trois. Le rattachement par contours ne passe pas par là (il rend
le code du polygone, déjà juste), donc ce n'est pas bloquant ; ça le
deviendrait le jour où un code de province viendrait de Wikidata.

### Ce qu'il manque encore pour collecter l'Italie

**Le référentiel des provinces et des régions.** `geo.py` lit
`data/reference/regions.csv` et `departements.csv` en dur : ils sont français.
Il faut leur équivalent italien — 110 provinces, 20 régions — et rendre leur
lecture dépendante du pays. Les codes et les noms se tirent du GeoJSON déjà
vérifié ; le `de_form` français d'un nom italien (« de Toscane », « des
Pouilles ») est du travail éditorial, pas de la dérivation.

**Les dérogations communales.** Rome, Florence, Venise et Naples en demanderont
chacune une. Elles se posent sur un code ISTAT de commune, et se décident sur
un décrochage MESURÉ dans le vivier de chaque ville — c'est ainsi que celle de
Paris a été posée. Elles viennent donc après la première collecte, pas avant.

**Le plafond des églises.** Retiré, pas relevé : les quatre-vingts français ont
été posés après un build, en lisant que le catalogue en portait 193 pour 61
montrés. Le premier build italien donnera la même lecture.

**Les listes italiennes restantes.** Les monuments nationaux, les jardins
historiques, les parcs nationaux et régionaux, les réserves naturelles : rien
n'est écrit tant que `suggest-qids` puis `verify-qids` ne l'ont pas résolu. Les
Borghi più belli, eux, sont faits — section suivante.

### Les trois thèmes que la mesure italienne a tranchés — FAIT

**Villages : rendus.** `suggest-qids` sur « I borghi più belli » rend six
résultats ; c'est **Q127107** qui est l'association — « association culturelle
italienne » —, comme Q1010307 l'est en France. Les Q110890335/6/7 sont des
pages de listes régionales : `member_of` sur elles ne rendrait qu'une région.
Le label est écrit dans `config/it/labels.yaml` sur le modèle exact du
français : `member_of`, bonus 30, `makes_collection`, `garde_d_office`.

Ce dernier est une **extrapolation assumée**, et c'est la seule ligne de tout
`config/it/` qui n'est pas une mesure. La revue française a relu 352 lieux de
listes à jury et n'en a écarté aucun (185 villages, 102 détours, 54 Grands
Sites, 11 forêts d'exception) ; les Borghi sont du même genre — association,
jury, liste finie — mais n'ont jamais été relus. Si la première revue italienne
écarte des bourgs, c'est cette ligne qui saute, et elle seule.

Le plancher d'affichage du thème (3 langues) ne bouge pas : un lieu porté par
une liste officielle de son thème le franchit d'office
(`collections.py`, `apply_notoriety_floor`), comme les Maisons des Illustres en
France — 147 d'entre elles ne tenaient qu'à cette dispense.

**Forêts : retirées.** `gaps --pays Q38 --class Q4421` :

    forêt (Q4421)
     ≥0   ≥1   ≥2   ≥3   ≥4   ≥6   ≥8  ≥10  ≥12  ≥15  ≥20
     93   83   18    5    2    1    0    0    0    0    0

Contre 2 920 françaises, dont 156 à trois langues. Le plancher d'affichage du
thème est à 4 : **deux** forêts italiennes le passent. Et rien ne les repêche —
la classe propre du thème, `Q3079027`, est la forêt *domaniale*, un statut du
droit français ; le label Forêt d'Exception, qui portait sept des trente-deux
forêts françaises du catalogue, est une liste de l'ONF. Abaisser le plancher à
2 rendrait 18 lieux, mais c'est la bande des bois communaux, que la mesure
française écarte à dessein.

**Cirques : retirés.** `gaps --pays Q38 --class Q388227` :

    cirque glaciaire (Q388227)
     ≥0   ≥1   ≥2   ≥3   ≥4   ≥6   ≥8  ≥10  ≥12  ≥15  ≥20
      2    2    1    1    1    0    0    0    0    0    0

Et la collecte le confirme sur les trois classes du thème réunies : **un** lieu
candidat pour toute l'Italie. Ce n'est pas une lacune de Wikidata, c'est de la
géographie — le cirque est une forme pyrénéenne et jurassienne.

Dans les deux cas, le motif est celui qui avait retiré `villages` avant que la
liste italienne ne le rende : un thème qui promet une catégorie et rend deux
lignes est pire qu'un thème absent. C'est une décision de curation, pas de
configuration, et elle tient en une ligne à retirer.

### Le plafond par commune, une fois les communes là — MESURÉ

Le build suivant, avec les communes rattachées, a fait mordre `max_per_commune`
pour la première fois : **1 118 lieux retirés** — Rome 572, Venise 213, Milan
64, Florence 61, Naples 53. Le catalogue passe de 2 563 à **2 373 lieux**, et
les lieux jetés faute de collection tombent de 702 à 44.

Ce que le plafond a coûté, thème par thème, entre la colonne `plancher` et la
colonne `commune` : églises 550 → 235, monuments 617 → 189, mégalithes 454 →
235, îles 116 → 90, musées 184 → 134, ponts 45 → 32.

Et il a emporté **dix collections entières**, dont « Îles de Venise » (28
lieux), « Sommets du Piémont » (23) et « Littoral et plages de Sicile » (18).
Les vingt-huit îles de Venise sont toutes dans la même commune : à six par
thème, il en reste six. C'est exactement le cas qu'une dérogation existe pour
traiter — Paris a la sienne pour la même raison.

**`derogations` rend cette décision refaisable.** Celle de Paris avait été
mesurée à la main, une ville et un thème à la fois ; la commande donne
maintenant, pour les villes que le plafond coupe le plus, le vivier au pied du
plafond thème par thème, la plus forte chute et le **pas courant** à côté. Ce
dernier n'est pas décoratif : une plus forte chute existe toujours, même dans
une liste régulière, et c'est leur rapport qui dit s'il y a un décrochage. Sur
Paris, la commande retrouve ce que le curateur avait lu — jardins, chute de
15,0 pour un pas courant de 1,3 (une falaise) ; musées, chute de 5,1 pour un pas
de 0,9 (« trente-deux institutions se suivent sans rupture »).

Les codes ISTAT des villes concernées, lus dans la couche communale et non de
mémoire : Rome 058091, Venise 027042, Milan 015146, Florence 048017, Naples
063049, Turin 001272, Palerme 082053, Bologne 037006.

### Les huit dérogations italiennes — MESURÉES

Sorties de `derogations`, chacune à la plus forte chute quand elle sort du pas
courant. Là où elle n'en sort pas, il n'y a pas de ligne.

| ville | thème | candidats | chute / pas | plafond |
|---|---|---|---|---|
| Rome `058091` | églises | 203 | 2,3 / 0,5 | **9** |
| | sites antiques | 203 | 4,8 / 0,4 | **8** |
| | monuments | 140 | 5,4 / 0,6 | **10** |
| | musées | 29 | 9,8 / 1,5 | **10** |
| Venise `027042` | îles | 29 | 9,1 / 0,9 | **8** |
| | églises | 58 | 3,6 / 0,6 | **10** |
| | monuments | 131 | 2,5 / 0,4 | **8** |
| Florence `048017` | musées | 16 | 18,2 / 1,6 | **13** |

**Milan et Naples n'en ont aucune, et c'est un résultat.** Leurs viviers sont
des plateaux : onze palais milanais entre 67 et 70 points, dix-sept palais
napolitains entre 55 et 65. Le plafond y coupe exactement ce qu'il doit couper.
Deux mesures confirment même le six en s'y arrêtant d'elles-mêmes — les maisons
de Milan chutent de 6,6 juste après le sixième, les monuments de Florence de
2,4 pour un pas de 0,4, au sixième également.

Les huit îles de Venise sont la raison d'être de tout ceci : à six, la
collection « Îles de Venise » disparaissait en entier.

**Deux observations à porter en revue**, lues dans ces mêmes viviers :

- **Le Vatican n'est pas l'Italie, et Rome perd Saint-Pierre.** Les 203 églises
  romaines du vivier ne contiennent ni Saint-Pierre, ni la chapelle Sixtine, ni
  les musées du Vatican : `apply_geographic_scope` les situe en Q237. Le filtre
  a raison, le guide a tort — un voyageur français qui va à Rome va au Vatican.
  Saint-Marin pose la même question.
- **Quatre des vingt-cinq premiers « monuments » de Venise sont des théâtres
  DISPARUS** — San Cassiano (démoli en 1812), San Benedetto, San Samuele, San
  Moisè. `fantomes` est fait pour ça.

### Les piazzas : le seul thème que la France n'a pas — ÉCRIT

`gaps --pays Q38 --class Q174782`, lieux italiens par plancher :

     ≥0    ≥1   ≥2   ≥3   ≥4   ≥6   ≥8  ≥10  ≥12  ≥15  ≥20
   1711  1241  561  297  193  115   74   53   42   35   20

Aucune falaise au-dessus de deux langues : la seule vraie rupture est entre 1 et
2 (1 241 → 561), la bande des places de quartier qui n'ont qu'un article
italien — le même piège que les 2 884 forêts françaises à une langue. Le
plancher est donc un choix, et il est calé sur `monuments`, le thème le plus
proche par nature : 6 en affichage (115 lieux), 4 en collecte (193), les 78
d'écart laissant de quoi repêcher.

Le thème arrive **en dernier** dans l'ordre fusionné, et c'est voulu : l'ordre
est la priorité éditoriale, et une piazza qui est aussi un site antique — le
Forum, le Campidoglio — doit rester un site antique.

**Le glyphe devait exister AVANT le thème.** `ThemeIcon` rend `null` quand
`TRACES` ne connaît pas l'identifiant, et la carte native n'enregistre que les
PNG présents : un thème sans tracé disparaît des deux côtés sans un mot. Un
test du pipeline lit maintenant `themeIcons.tsx` et vérifie que chaque thème de
chaque pays a le sien.

### Le plafond des églises : la question a changé de main

Avant les communes, `cathedrales` portait 549 lieux au catalogue et la question
était « quel `catalogue_cap` ? ». Le plafond par commune en a retiré 315 à lui
seul, et le thème en compte **253**. Le travail que le `catalogue_cap` français
faisait — empêcher une capitale d'occuper tout un thème — est fait ici par
l'échelon en dessous, et mieux : il coupe Rome sans toucher à Assise, Orvieto
ou Sienne. Un plafond de thème posé maintenant couperait précisément l'inverse.

À revoir après la première revue italienne, pas avant : une revue qui écarte des
églises change le chiffre sur lequel un plafond se poserait.

### Ce qu'on sait déjà pour écrire `config/it/`

Trois planchers mesurés, à ne pas remesurer. Les tableaux sont ceux de
`gaps --pays Q38 --class <QID>`, lieux italiens situés par plancher :

    église (Q16970)
      ≥0     ≥1     ≥2    ≥3    ≥4    ≥6   ≥8  ≥10  ≥12  ≥15  ≥20
    56648  26882  13199  3699  2125  1007  637  372  264  156   78

    villa (Q3950)
      ≥0     ≥1     ≥2    ≥3    ≥4    ≥6   ≥8  ≥10  ≥12  ≥15  ≥20
     4704   2376   1322   577   275   107   50   35   24   10    4

**Villas : `Q3950` en classe PRÉCISE de son thème, plancher 3.** Aujourd'hui
elles n'entrent que par la porte générique « maison » à 8 langues, ce qui en
capte cinquante. À 3, elles sont 577 collectées et 275 franchissent le
plancher d'affichage du thème (4) : c'est un gain net d'environ 225 lieux,
soit 7 % du catalogue italien estimé. Le 3 est choisi comme pour les forêts —
une langue sous le plancher d'affichage, pour laisser de quoi repêcher.

⚠ Mais 275 villas dans `maisons`, qui en compte 143 en France, noieraient les
maisons sous les villas. Les villas palladiennes de Vénétie et les villas
médicéennes sont deux séries du patrimoine mondial : elles méritent
probablement un thème à elles. Décision de curation, pas de configuration.

**Églises : le plancher n'est pas le problème, le PLAFOND l'est.** À 6
langues, 1 007 églises ; à 8, 637 ; à 10, 372. Mais `cathedrales` porte un
`catalogue_cap: 80`, et l'Italie présente déjà, au-dessus du plancher
d'affichage de ce thème, environ 900 candidats — 372 églises, 362 basiliques
mineures, 169 cathédrales. Quatre-vingts places pour neuf cents prétendants,
dans le pays dont les églises SONT le patrimoine principal.

`config/it/` devra donc, sur ce thème, faire deux choses à la fois : déclarer
`Q16970` — en classe générique à 8, ou précise à 6 — et relever ou retirer le
`catalogue_cap`. L'un sans l'autre ne sert à rien.

### Trois décisions déplaceraient le chiffre, et elles ne sont pas prises

**Le plancher des églises.** Q16970 en compte 637 à huit langues. À lui seul
il peut ajouter plusieurs centaines de candidats — ou zéro si on ne le
déclare pas.

**`catalogue_cap: 80` sur `cathedrales`.** En France il borne les cathédrales
et basiliques. En Italie, il bornerait cathédrales + basiliques mineures +
églises à QUATRE-VINGTS lieux au total, alors que le recensement en donne
déjà 460 à douze langues. Pour un pays dont les églises sont le patrimoine
principal, ce plafond est un contresens.

**`max_per_commune: 6`.** Paris a sa dérogation, écrite en toutes lettres.
Rome, Florence, Venise et Naples en demanderont chacune une — Paris pèse 59
lieux au catalogue français, et Rome n'est pas moins riche.

### Ce qui transformerait l'estimation en mesure

    python -m roam_pipeline gaps --pays Q38 --min-sitelinks 6

Le recensement à douze langues ne voit que le sommet : la médiane du
catalogue français est à HUIT langues. Refait à six, le même tableau donne le
vivier aux planchers réellement utilisés, et le compte cesse d'être une
projection.

## Mesurer avant de s'engager

Rien de tout cela n'est nécessaire pour COMPTER ce qu'un pays rapporterait :

    python -m roam_pipeline gaps --pays Q38                    # classes notoires
    python -m roam_pipeline gaps --pays Q38 --class <QID>      # comptes par plancher
    python -m roam_pipeline label-probe <QID> --pays Q38       # une liste nationale

`--pays` ne touche à rien : il interroge Wikidata pour un autre pays et
n'écrit aucun fichier. Le pays du catalogue, lui, se change dans
`scoring.yaml` — et ne suffit pas à porter le pipeline.
