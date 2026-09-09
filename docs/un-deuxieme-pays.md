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

**Le rattachement administratif, et c'est le seul vrai morceau.**
`geocode.py` (309 lignes) repose sur `api-adresse.data.gouv.fr` et
`geo.api.gouv.fr` : gratuits, sans clé, et strictement français.

Proposition : **s'en passer partout, France comprise.** On télécharge déjà les
contours des départements pour la carte de conquête ; rattacher un lieu à sa
province par point-dans-polygone local, c'est zéro API, zéro service national,
et ça vaut pour n'importe quel pays dont on a les contours.

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
    rattachement par point-dans-polygone                   2–3 j
    contours étrangers (source + machinerie existante)       ~1 j
    collections partitionnées par pays                     2–3 j
    app : littéraux, libellés, voile, carte de conquête      ~2 j
    calibration des planchers sur données étrangères       1–2 j
                                                          ─────
                                                           9–12 j

Dont environ six jours payés une seule fois ; le troisième pays coûterait deux
à trois jours plus la calibration.

## Une réserve, et elle n'est pas technique

La curation vaut ce que vaut la connaissance du pays. Descendre la Cité
radieuse d'un niveau, ranger le Familistère en musée parce qu'on y entre au
billet : ces jugements-là n'existeront pas pour l'Italie. Sans les labels
nationaux, le catalogue italien reposera donc ENTIÈREMENT sur la documentation
Wikipédia — exactement le mode de défaillance corrigé sur les forêts, où la
classe « forêt domaniale » ne voyait même pas Fontainebleau.

Les planchers d'un pays neuf méritent donc plus d'attention que les français
n'en ont reçu au départ, pas moins.

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

### Ce qui reste à vérifier, et comment

Quatre classes marquées `✗` restent indécises. Chacune se tranche par un
`probe` sur une entité à CLASSE UNIQUE, comme pour `palazzo` :

    musée privé (Q614316)          105   Museo Egizio de Turin, musée du cinéma
    villa (Q3950)                  102   villas médicéennes, villa Torlonia
    ensemble architectural         98    Santa Maria del Carmine, Rotonda
    place (Q174782)                112   Piazza della Rotonda, Piazza Arringo

Les deux premières comptent : le Museo Egizio est l'un des grands musées
d'Italie, et les villas médicéennes et palladiennes sont au patrimoine
mondial. Aucune n'est déclarée dans la configuration française, ce qui ne
prouve rien — `palazzo` ne l'était pas non plus.

### Le recensement peut perdre ses classes les plus grosses

L'unique lot en échec de la mesure italienne portait commune, frazione,
église et montagne. La réponse de WDQS n'était pas refusée mais TRONQUÉE
(JSON incomplet), et c'est d'autant plus probable que la classe est fournie :
le recensement perd donc en priorité ce pour quoi on le lance.

`gaps` réessaie désormais classe par classe après un lot perdu — une seule
reste alors hors de portée, pas ses trois voisines.

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
