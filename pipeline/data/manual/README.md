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
