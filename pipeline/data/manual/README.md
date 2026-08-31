# Listes de labels saisies à la main

Certains labels n'ont pas de propriété Wikidata exploitable (`kind: manual` dans
`config/labels.yaml`). Leur liste de membres se saisit ici, dans un fichier
`<identifiant-du-label>.csv` :

```csv
name,wikidata_id,note
Salers,Q220962,
Rocamadour,Q206697,vérifié sur le site de l'association
```

Seule la colonne `wikidata_id` est lue par le pipeline ; `name` et `note` servent à la
relecture humaine. Un fichier absent ne provoque pas d'erreur : le label est simplement
ignoré, avec un avertissement.


## Les deux mémoires de la curation

Deux fichiers de ce dossier ne sont pas des listes de labels mais la trace du
travail éditorial. Ils sont relus à **chaque** construction :

| Fichier | Rôle |
|---|---|
| `decisions.csv` | verdicts d'inclusion — `keep`, `drop`, `promote`, `demote` |
| `names.csv` | noms d'affichage choisis, quand le libellé de Wikidata ne convient pas |
| `themes.csv` | rattachements redressés, quand la classe Wikidata décrit une partie du lieu |
| `tiers.csv` | photographie du niveau ET du thème tels qu'ils ont été VUS à la dernière revue |
| `candidates.csv` | candidats adoptés depuis OpenStreetMap — une ligne retirée à la main le reste |

`data/out/review.csv` en revanche NE se committe pas : c'est une sortie de
`build`, réécrite à chaque construction avec une colonne `decision` vide. Tes
décisions vont du navigateur à `decisions.csv` par `apply-review`, jamais par
là.

`data/out/candidates.csv`, la sortie de `discover`, se committe aussi. Ce n'est
pas une sortie comme les autres : elle coûte vingt minutes de requêtes Overpass
et elle porte les seuls faits de terrain du catalogue — horaires, tarifs, accès
refusé. Sans elle, le filtre d'accès n'écarte rien et le repêchage ne sauve
personne : le catalogue perd plusieurs centaines de lieux sans qu'aucune ligne
ne l'explique.

Ils sont séparés à dessein. Renommer et écarter sont deux gestes différents :
un lieu peut être renommé **et** gardé, renommé **et** écarté. Fondus dans un
seul fichier, la colonne `decision` deviendrait ambiguë.

`names.csv` s'écrit à la main ou par la commande :

```bash
python -m roam_pipeline rename Q3330248 "Musée des impressionnismes"
python -m roam_pipeline rename                    # liste les renommages
python -m roam_pipeline rename Q3330248 --clear   # revenir au libellé Wikidata
```

`themes.csv` de même. Le pipeline range d'après les classes Wikidata, et se
trompe quand la classe décrit une **partie** du lieu : le musée Christian-Dior
est classé « jardin » parce que la villa en a un remarquable. Wikidata n'a pas
tort — c'est la hiérarchie des classes qui ne dit pas ce qu'on vient voir.

```bash
python -m roam_pipeline explain "christian dior"   # trouver le Q-id et voir son thème
python -m roam_pipeline retheme Q123456 musees --note "le jardin n'est pas le sujet"
python -m roam_pipeline retheme                    # liste les redressements
python -m roam_pipeline retheme Q123456 --clear    # revenir au rattachement automatique
```

La revue le fait aussi, et c'est la voie normale : chaque vignette porte un
**sélecteur de thème**, déjà positionné sur le rattachement du pipeline. Une
revue interrompue au milieu laisse donc un catalogue rangé, pas un catalogue en
attente — le sélecteur ne sert qu'à contredire.

Deux signaux marquent les vignettes qui méritent un second regard, et le filtre
**« Thème douteux — à trancher »** ne montre qu'elles :

- **plusieurs thèmes ont réclamé le lieu.** Le pipeline a tranché avec la règle
  du plus spécifique ; c'est un arbitrage, pas un fait. Après le dédoublonnage
  il n'en reste aucune trace, d'où le calcul sur le catalogue brut.
- **le nom annonce autre chose.** Le nom français d'un lieu commence par son
  type — « Musée Christian-Dior », « Abbaye Saint-Victor ». C'est le seul signal
  que Wikidata ne donne pas quand la classe décrit une *partie* du lieu. Les
  mots reconnus sont dans `config/themes.yaml`, champ `name_hints` ; un mot que
  deux thèmes revendiquent ne prouve rien et n'est pas retenu.

C'est un indice, pas un verdict : « Maison Carrée » est un temple romain, et
« Le Mont-Saint-Michel » n'est pas un sommet. Le défaut reste le bon dans ces
cas-là, il suffit de ne rien toucher.

Un lieu redressé **quitte ses autres rattachements** : changer l'étiquette d'un
seul exemplaire ne suffirait pas, le doublon inter-thèmes resterait et la règle
du plus spécifique continuerait de trancher toute seule.

Ce n'est pas un verdict d'inclusion : le lieu doit encore franchir le plancher
de notoriété de son nouveau thème, qui est souvent plus haut — `musees` demande
douze langues là où `jardins` en demande cinq. `build` nomme les redressements
qui ne sortent plus dans aucune collection, et `explain` dit à quelle étape.
Quand le lieu mérite d'y rester malgré tout, un `keep` dans la revue l'épingle
et le plancher ne s'y applique plus.

### Le trajet d'une décision

```
navigateur  →  data/out/review-decisions.csv  →  apply-review  →  decisions.csv
   clic            écrit à chaque clic              relit           versionné
```

Le serveur de `review` recueille les décisions **au fil des clics** et les écrit
sur le disque. Le témoin « enregistré à 12:02 » en haut de la page le confirme ;
s'il passe au rouge, c'est que le serveur ne répond plus et qu'il faut
télécharger avant de fermer.

`apply-review` sans argument reprend ce fichier. Plus rien à nommer :

```bash
python -m roam_pipeline apply-review
```

> Faire dépendre une soirée de relecture d'un bouton qu'il faut penser à
> cliquer, puis d'un fichier qu'il faut reconnaître parmi ses homonymes
> numérotés par le navigateur (`review-decisions (1).csv`), ne pouvait que
> casser. C'est arrivé deux fois, et la seconde a coûté une heure de travail.
> Le bouton de téléchargement reste, comme secours quand la page est ouverte
> sans serveur.

### Revenir sur une décision

Chaque vignette de la revue porte un bouton **✕** dès qu'un verdict a été pris.
Il retire la décision : le lieu retrouve son classement automatique, et
`apply-review` **efface la ligne** de `decisions.csv`. Sans lui, se dédire
demandait d'éditer le CSV à la main — et un curateur qui doit ouvrir un fichier
pour revenir sur une décision finit par ne plus revenir sur ses décisions.

### Monter ou descendre d'un niveau

`promote` et `demote` déplacent un lieu d'**exactement un niveau**, dans la
limite des trois. Ils s'appliquent APRÈS le classement, et c'est ce qui les rend
fiables : un lieu monté monte, un lieu descendu descend, quel que soit son
voisinage.

Ils ne retirent JAMAIS un lieu du catalogue. Écarter, c'est `drop` — deux gestes
distincts, et qui le restent.

> La première version corrigeait le SCORE de soixante points. Un décalage de
> score ne peut pas exprimer une intention de rang : deux lieux au même score ne
> sont pas dans le même voisinage. Mesuré sur le catalogue réel, seuls 25
> `demote` sur 73 descendaient d'un cran — 27 en perdaient deux, et 15
> disparaissaient du catalogue sans que personne ait décidé de les écarter.
> Baisser le montant ne réglait rien : à 15 points, 25 lieux ne bougeaient plus
> du tout et les `promote` cessaient de fonctionner.

Un déplacement peut porter une collection à onze lieux de niveau 1. Le plafond
est une heuristique, ta décision est un jugement : faire redescendre quelqu'un
d'autre en silence serait pire.

```bash
python -m roam_pipeline adjustments
```

Signale les déplacements qui ne produisent rien : un `promote` sur un lieu déjà
au niveau 1, un `demote` sur un niveau 3, ou une décision portant sur un lieu
qu'un plancher écarte de toute façon.

### Quand deux revues se croisent

Ces fichiers sont réécrits en entier, triés par identifiant. Deux soirées de
relecture menées sur deux machines produisent donc deux versions du même
fichier, et git ne sait pas les départager : il pose des marqueurs de conflit au
milieu d'un travail que personne n'a perdu.

Ce ne sont pourtant pas des textes mais des tables dont la clé est le Q-id, et
la fusion juste est l'union des deux côtés :

```bash
git pull                        # git signale le conflit
python -m roam_pipeline merge   # fusionne data/manual/
python -m roam_pipeline build   # vérifie
git add pipeline/data/manual && git commit
```

Le seul cas qui demande un humain est le lieu tranché **différemment** des deux
côtés. La commande garde alors ta version locale et **nomme le lieu**, plutôt
que d'inventer une règle qui déciderait à ta place.

### Ces fichiers se committent

C'est plusieurs soirées de relecture, et ce sont des fichiers texte de quelques
dizaines de kilo-octets. **Le dépôt est leur sauvegarde** — il n'y a rien de
mieux à inventer :

```bash
git add pipeline/data/manual/decisions.csv pipeline/data/manual/names.csv \
        pipeline/data/manual/themes.csv pipeline/data/manual/tiers.csv
git commit -m "Revue du <date>"
```

`apply-review` le rappelle à chaque passage.

### Un niveau qui bouge sans qu'on l'ait décidé

Le niveau d'un lieu n'est pas une propriété du lieu : c'est son **rang** dans sa
collection. Ajouter un signal au score — la fréquentation, par exemple — ou
seulement collecter dix lieux de plus suffit à faire reculer un incontournable
déjà validé.

`tiers.csv` est la photographie du dernier état vu. `build` compare et signale
les écarts ; `apply-review` met la photographie à jour, parce que c'est le
moment où le curateur a regardé. La prendre à chaque `build` effacerait le
changement avant qu'il ne soit lu.

Le **thème** est photographié avec le niveau, et il prime sur lui : changer de
thème, c'est changer de collection, de voisins et de sens. Un lieu validé
comme maison d'artiste et rendu aux musées doit être revu comme musée, quel que
soit le rang qu'il y prend — sa décision avait été prise dans un autre contexte.

Les lieux qui **changent de thème** et ceux qui **descendent** sont nommés dans le journal — ce sont les seuls qui
demandent un second regard, un lieu qui monte gardant sa décision valable. Dans
la page de revue, le menu des niveaux offre « ce qui a changé de niveau ».
