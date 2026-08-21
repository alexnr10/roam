# La carte de conquête

> Conception. Rien n'est implémenté à ce stade — la fonctionnalité a besoin du vrai
> catalogue pour avoir un sens : avec 46 lieux de démonstration, aucun département n'est
> conquérable.

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

- moins de 3 lieux du thème dans le territoire → **non jouable**, rendu neutre et hachuré ;
- à partir de 3 → niveaux calculés localement, sur les mêmes règles que les collections
  mais avec des paliers réduits (niveau 1 = les 3 meilleurs, niveau 2 = 60 %, niveau 3 = tous).

Le pipeline produirait donc, en plus des collections, une **table de conquête** :
`(territoire, thème, niveau) → liste de lieux requis`. Ce n'est pas une collection
navigable, c'est une condition de coloriage.

## Le code couleur

Piège à éviter : trois couleurs de niveau × seize thèmes donnent un patchwork illisible.

**Une teinte par thème, une intensité par niveau.**

| État | Rendu |
|---|---|
| Non jouable | gris neutre, hachuré léger |
| Entamé | teinte du thème à très faible opacité, proportionnelle au pourcentage |
| Niveau 1 | teinte du thème, saturation moyenne |
| Niveau 2 | teinte du thème, saturation forte |
| Niveau 3 | teinte du thème, saturation maximale + liseré |

Sur la **carte générale**, la teinte n'est plus celle d'un thème mais celle de Roam, et
l'intensité dit la profondeur d'achèvement du territoire.

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

## Ordre de réalisation proposé

1. **Animation de validation** ✅ *(faite)*
2. Table de conquête produite par le pipeline — pur calcul, testable hors carte
3. Écran « conquête » en liste, sans carte : départements et régions conquis par thème.
   Permet de valider les règles avant d'investir dans le rendu géographique.
4. Migration MapLibre + contours des régions et départements
5. Coloriage des départements et régions, par thème
6. Communes et carte générale

Les étapes 2 et 3 ne dépendent d'aucune décision technique lourde et se testent
immédiatement. C'est par là qu'il faut commencer.

## À trancher

- **Le seuil de 3 lieux** est-il le bon ? À regarder sur le vrai catalogue : combien de
  couples thème × département deviennent jouables selon qu'on met 3, 4 ou 5.
- **La commune est-elle la bonne maille** pour la carte générale ? Beaucoup de communes
  n'ont qu'un seul lieu, donc se conquièrent en une visite. C'est peut-être exactement
  l'effet voulu — la carte générale se remplit vite, les cartes de thème sont le jeu
  long — mais ça mérite d'être décidé plutôt que subi.
- **Que se passe-t-il quand le catalogue s'enrichit ?** Un département conquis qui reçoit
  un nouveau lieu redevient incomplet. Retirer une couleur acquise est une très mauvaise
  sensation. Piste : geler le niveau atteint et signaler le nouveau lieu comme un bonus,
  sans faire régresser la carte.
