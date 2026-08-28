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
| `tiers.csv` | photographie du niveau ET du thème tels qu'ils ont été VUS à la dernière revue |

Ils sont séparés à dessein. Renommer et écarter sont deux gestes différents :
un lieu peut être renommé **et** gardé, renommé **et** écarté. Fondus dans un
seul fichier, la colonne `decision` deviendrait ambiguë.

`names.csv` s'écrit à la main ou par la commande :

```bash
python -m roam_pipeline rename Q3330248 "Musée des impressionnismes"
python -m roam_pipeline rename                    # liste les renommages
python -m roam_pipeline rename Q3330248 --clear   # revenir au libellé Wikidata
```

### Ces fichiers se committent

C'est plusieurs soirées de relecture, et ce sont des fichiers texte de quelques
dizaines de kilo-octets. **Le dépôt est leur sauvegarde** — il n'y a rien de
mieux à inventer :

```bash
git add pipeline/data/manual/decisions.csv pipeline/data/manual/names.csv \
        pipeline/data/manual/tiers.csv
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
