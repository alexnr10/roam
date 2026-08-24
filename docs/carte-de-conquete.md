# La carte de conquête

> Étapes 2 à 5 faites : les règles sont implémentées et testées, et l'écran « Conquête »
> montre **la carte coloriée** des départements et des régions, avec la liste dessous.
> Restent les communes et la carte par thème (étape 6).

## Le principe

La récompense ne s'arrête pas au lieu validé. Elle se propage sur le territoire :

1. **À la validation** — une animation célèbre le mouvement des collections. *(fait)*
2. **Au niveau du lieu** — le point se colore sur la carte, visible en zoom rapproché.
3. **Au niveau du département** — quand un thème y est complété, tout le département se
   colore sur la carte de ce thème.
4. **Au niveau de la région** — même chose à l'échelle supérieure.

La **couleur dépend du niveau atteint**, pas seulement du fait d'avoir fini.

Deux familles de cartes :

- **une carte par thème** — « où ai-je conquis les châteaux ? »
- **une carte générale** — une commune n'y est colorée que si elle est achevée **tous
  thèmes confondus**, ne serait-ce qu'au niveau 1.

C'est ce qui transforme une liste de cases cochées en territoire. Et c'est ce qui donne
une raison d'aller dans la Creuse.

## Les deux couleurs

Le curateur a tranché : deux états se distinguent à l'œil, à chaque échelle.

| État | Signification | Couleur |
|---|---|---|
| **Une collection finie** | tous les lieux d'un thème dans le territoire | or |
| **Territoire complet** | tous les lieux du territoire, tous thèmes confondus | terracotta pleine |

Le second implique le premier pour chaque thème : c'est une conquête totale, et elle se
lit comme un aboutissement. Entre les deux, un territoire entamé porte une teinte pâle
proportionnelle à son avancement — sans quoi la carte serait binaire et ne montrerait
aucune progression.

Les quatre échelles — commune, département, région, pays — répondent aux mêmes règles.

## La difficulté centrale : quel niveau pour quel lieu ?

Aujourd'hui, **le niveau est relatif à chaque collection**. Le même château est niveau 1
dans « Châteaux du Cantal » et niveau 3 dans « Châteaux » (national). Pour colorer un
territoire, il faut une règle unique. Trois options :

| Option | Règle | Verdict |
|---|---|---|
| **A. Niveau local** | Le niveau du lieu dans la collection (thème × territoire) correspondant à l'échelle regardée | ✅ recommandé |
| B. Niveau canonique | Un niveau unique stocké sur le lieu | ❌ un département sans lieu de niveau 1 serait « complété niveau 1 » à vide |
| C. Seuil de pourcentage | X % des lieux du thème dans le territoire | ❌ perd la notion de niveau, qui est tout l'intérêt |

**L'option A correspond à l'intuition** : « j'ai fait les 10 meilleurs châteaux du
Cantal, donc le Cantal est doré sur la carte des châteaux ». Et elle réutilise le
mécanisme de niveaux déjà en place.

Elle implique qu'un lieu ait un niveau différent selon l'échelle regardée — ce n'est pas
un défaut, c'est exactement ce qu'on veut : la carte des départements utilise le classement
départemental, celle des régions le classement régional.

## Seuil de jouabilité

Sans garde-fou, un département contenant **un** château se colore en or au premier
château visité — et l'or ne veut plus rien dire.

Les collections croisées n'existent qu'à partir de 8 lieux (cf. charte de curation). Ce
seuil est trop haut pour la carte : la plupart des couples thème × département seraient
neutres, et la carte resterait vide.

**Proposition : un seuil propre à la conquête, à 3 lieux.**

- moins de 3 lieux du thème dans le territoire → **non jouable**, rendu neutre ;
- à partir de 3 → niveaux calculés localement, avec des paliers réduits (niveau 1 = les 3
  meilleurs, niveau 2 = les 8 meilleurs, niveau 3 = tous).

**Le seuil ne vaut que pour un thème.** L'unité « tous thèmes confondus » y échappe : une
commune d'un seul lieu se conquiert en une visite, et c'est exactement l'effet voulu — la
carte générale se remplit vite, les cartes de thème sont le jeu long.

Un dernier garde-fou est venu de l'implémentation : le niveau atteint plafonne à la
**profondeur du territoire**. Trois châteaux dans un département, tous validés, c'est le
niveau 1 et la collection complète — pas le niveau 3. Sinon un territoire pauvre vaudrait
autant qu'un département de quatre-vingts châteaux.

### Où vit ce calcul

Dans l'application (`mobile/src/lib/conquest.ts`), et non dans le pipeline. Le découpage
en territoires est une pure fonction de données que l'application a déjà — scores, thèmes,
codes de territoire — et l'y calculer évite d'embarquer huit mille appartenances dans le
catalogue. Le pipeline n'a eu qu'à fournir ce qui manquait : les **codes** de territoire,
dont ceux des communes, qu'il ne connaissait pas.

## Le code couleur

Piège écarté : trois couleurs de niveau × seize thèmes auraient donné un patchwork
illisible. Le choix retenu est **deux couleurs, et une seule teinte pâle entre les deux**.

| État | Rendu |
|---|---|
| Vierge | gris neutre |
| Entamé | terracotta très pâle, opacité proportionnelle au pourcentage |
| Une collection finie | **or** |
| Territoire complet | **terracotta pleine** |

Sur une **carte de thème**, seule cette collection-là décide. Sur la **carte générale**,
c'est le territoire entier, tous thèmes confondus.

Le niveau atteint (1, 2, 3) ne change pas la teinte mais son intensité : il dit la
profondeur de la conquête sans ajouter une couleur à lire.

## Rendu : ce que ça change techniquement

Colorer des polygones administratifs, c'est une carte choroplèthe. Il faut deux choses.

**Les contours administratifs.** Disponibles en open data (data.gouv.fr, Wikidata,
OpenStreetMap) :

| Échelon | Volume simplifié | Remarque |
|---|---|---|
| Régions (18) | ~300 Ko | trivial |
| Départements (101) | ~1-2 Mo | acceptable en embarqué |
| Communes (~35 000) | 30-80 Mo | **hors de question en entier** — ne charger que les communes contenant au moins un lieu du catalogue, soit quelques milliers |

**Un moteur qui sait styler un polygone par donnée.** `react-native-maps` dessine des
polygones, mais quelques milliers de communes le mettent à genoux. **MapLibre** est fait
exactement pour ça (source vectorielle + `feature-state`, coloration sans redessiner la
géométrie).

> **C'est cette fonctionnalité, plus que le fond de carte, qui justifie la migration vers
> MapLibre.** Bon à savoir avant d'investir davantage sur `react-native-maps`.

## Transition par niveau de zoom

Tout afficher en même temps serait illisible. L'échelle regardée décide de ce qui est
colorié :

| Zoom | Ce qui se colore |
|---|---|
| Rapproché (ville et en dessous) | les **lieux** validés, en couleur pleine |
| Intermédiaire | les **communes** et **départements** conquis |
| Pays | les **régions** conquises |

La carte raconte donc la même progression à trois échelles, et le zoom devient un geste
de lecture, pas seulement de navigation.

## Ordre de réalisation

1. **Animation de validation** ✅
2. **Règles de conquête** ✅ — `mobile/src/lib/conquest.ts`, dix-sept tests
3. **Écran « Conquête » en liste** ✅ — quatre échelles, les deux couleurs, sans carte
4. **Contours des régions et départements** ✅ — `roam_pipeline export-outlines`, arcs
   partagés, 460 Ko pour 119 territoires
5. **Coloriage sur la carte MapLibre** ✅ — carte au-dessus, liste dessous ; taper un
   territoire y réduit la liste
6. Communes, et une carte par thème

Les étapes 2 et 3 ont validé les règles avant tout investissement dans le rendu
géographique — et l'écran en liste reste utile après : il dit ce qu'il reste à faire, là
où un aplat de couleur ne dit que ce qui est fait.

## Ce qui manque encore

- **Les communes.** Le fichier de contours n'en contient pas : trente-cinq mille
  polygones ne s'embarquent pas. Il faudra n'exporter que celles qui portent un lieu du
  catalogue — quelques milliers, soit un volume comparable aux départements.
- **L'outre-mer sort du cadre.** La vue initiale se cale sur l'emprise de la métropole ;
  un département des Antilles conquis se colorie, mais hors champ. La liste, elle, les
  montre. À traiter par un cartouche ou un raccourci de cadrage.
- **La carte par thème** — « où ai-je conquis les châteaux ? ». Les règles la permettent
  déjà (le niveau est calculé par thème × territoire), il ne manque que le sélecteur.

## À trancher

- **Le seuil de 3 lieux** est-il le bon ? À regarder sur le vrai catalogue : combien de
  couples thème × département deviennent jouables selon qu'on met 3, 4 ou 5.
- **Que se passe-t-il quand le catalogue s'enrichit ?** Un département conquis qui reçoit
  un nouveau lieu redevient incomplet. Retirer une couleur acquise est une très mauvaise
  sensation. Piste : geler le niveau atteint et signaler le nouveau lieu comme un bonus,
  sans faire régresser la carte.
