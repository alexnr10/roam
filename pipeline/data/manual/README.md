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

Ils sont séparés à dessein. Renommer et écarter sont deux gestes différents :
un lieu peut être renommé **et** gardé, renommé **et** écarté. Fondus dans un
seul fichier, la colonne `decision` deviendrait ambiguë.

`names.csv` s'écrit à la main ou par la commande :

```bash
python -m roam_pipeline rename Q3330248 "Musée des impressionnismes"
python -m roam_pipeline rename                    # liste les renommages
python -m roam_pipeline rename Q3330248 --clear   # revenir au libellé Wikidata
```

**`decisions.csv` n'est pas versionné.** C'est plusieurs soirées de relecture :
il ne survit qu'à une sauvegarde de la machine.
