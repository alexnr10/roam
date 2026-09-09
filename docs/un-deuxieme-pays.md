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

## Mesurer avant de s'engager

Rien de tout cela n'est nécessaire pour COMPTER ce qu'un pays rapporterait :

    python -m roam_pipeline gaps --pays Q38                    # classes notoires
    python -m roam_pipeline gaps --pays Q38 --class <QID>      # comptes par plancher
    python -m roam_pipeline label-probe <QID> --pays Q38       # une liste nationale

`--pays` ne touche à rien : il interroge Wikidata pour un autre pays et
n'écrit aucun fichier. Le pays du catalogue, lui, se change dans
`scoring.yaml` — et ne suffit pas à porter le pipeline.
