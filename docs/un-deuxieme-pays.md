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

**Environ 2 500, dans une fourchette de 2 200 à 2 800**, à configuration
égale. Le raisonnement, parce que le chiffre seul ne sert à rien :

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

À moyenne égale, 107 × 20,6 ≈ **2 200**. L'Italie étant mieux documentée, la
médiane monte et les repêchages diminuent : d'où le centre à 2 500.

### L'offre italienne est le double, et ça ne change pas le compte

    lieux à ≥12 langues, collecte française          1 306
    lieux à ≥12 langues, vivier italien réel        ~2 575

Le double. Mais l'offre excédentaire est absorbée par les plafonds : elle
change la QUALITÉ du catalogue, pas sa taille. Et les étoiles se
normalisent d'elles-mêmes — les niveaux sont proportionnels à leur
collection, pas absolus — ce qui est exactement l'effet recherché : trois
étoiles en Italie voudront dire « le haut de l'Italie », comme en France.

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
