# Comment savoir qu'un lieu naturel se visite

Pour le bâti, la question était réglée : des horaires ou un tarif dans OpenStreetMap
prouvent qu'on accueille du public. Un site naturel n'a ni l'un ni l'autre — une cascade
n'ouvre pas à 9 h. Il faut donc d'autres signaux, et tous ne se valent pas.

## Le sentier balisé ne prouve rien

`highway=path` couvre aussi bien le chemin de promenade que la voie d'accès à un refuge
d'alpinisme. En montagne il y en a partout — y compris exactement là où on ne veut pas
envoyer les gens. Pris seul, c'est un signal creux.

## Le parking est un bon signal

`amenity=parking` à quelques centaines de mètres d'un site naturel dit deux choses : on
vient là en voiture, et quelqu'un a jugé utile d'aménager de quoi se garer. C'est
littéralement le test de la charte — « ferait-on 45 minutes de route pour ça ? ». Un lieu
avec un parking a déjà répondu oui pour d'autres.

Deux compagnons du même ordre : `tourism=information` avec `information=board` (un panneau
d'interprétation est un aménagement délibéré) et `highway=trailhead` (départ de sentier
balisé).

## Mais le meilleur signal répond à une autre question

`sac_scale` est l'échelle suisse de difficulté, portée sur les chemins :

| Valeur | Ce que ça veut dire |
|---|---|
| `hiking` (T1) | chemin de promenade, chaussures de ville suffisent |
| `mountain_hiking` (T2) | sentier de randonnée, terrain parfois raide |
| `demanding_mountain_hiking` (T3) | passages exposés, mains parfois nécessaires |
| `alpine_hiking` (T4) et au-delà | crampons, corde, expérience de montagne |

**C'est la réponse exacte à la question que le filtre d'altitude approxime.** Aujourd'hui,
tout sommet au-dessus de 2 500 m est écarté faute de preuve du contraire — 370 sommets,
soit la moitié du naturel perdu d'un coup. Le seuil a été posé par le curateur et il est
juste tant qu'on n'a rien de mieux, mais c'est une règle par défaut, pas une mesure.

Un sommet desservi par un chemin en `sac_scale=hiking` ou `mountain_hiking` **est** une
randonnée, quelle que soit son altitude. Un sommet dont tous les accès sont en
`alpine_hiking` ne l'est pas, même à 1 800 m.

## Ce que ça donnerait

Trois états, comme pour l'ouverture au public — et le troisième compte autant que les
deux autres :

| Signal | Lecture |
|---|---|
| parking, panneau, ou chemin en T1/T2 à proximité | **accessible** |
| tous les accès en T4 et au-delà | **alpin** |
| rien de tout ça | **non renseigné** — ni bonus ni exclusion |

Le filtre d'altitude deviendrait alors le repli du troisième cas, et non la règle
générale : on n'écarterait plus par défaut ce qu'on peut mesurer.

## Ce que ça coûte

Une passe Overpass supplémentaire dans `discover`, sur `amenity=parking`,
`tourism=information` et `highway=path[sac_scale]`, puis un rapprochement par proximité —
la même mécanique que celle qui rapproche déjà le catalogue des sites OpenStreetMap. Le
volume est plus élevé (les chemins sont nombreux), donc la requête doit se limiter au
voisinage des lieux du catalogue plutôt que balayer la France.

Rien de cela n'est fait. C'est la suite logique une fois les nouveaux thèmes collectés :
sans eux, il n'y aurait pas grand-chose à qualifier.
