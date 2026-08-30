# La collecte, versionnée

Un fichier par thème, plus `ajouts.json` pour les lieux épinglés à la main et
les candidats adoptés depuis OpenStreetMap.

## Pourquoi c'est dans le dépôt

La collecte n'est pas un produit de construction : elle ne se régénère pas à
l'identique. Wikidata évolue d'un jour à l'autre, une requête expire sans que
rien ne s'arrête, un thème échoue et son message se perd dans le journal.

Or les décisions éditoriales — `../manual/decisions.csv` — portent sur des Q-id
précis. Une décision prise sur un lieu que l'autre machine n'a jamais collecté
ne veut rien dire, et un niveau photographié sur un catalogue partiel fait
passer des centaines de lieux déjà relus pour des nouveautés.

## Ce que le découpage garantit

`fetch` ne réécrit que les fichiers des thèmes qu'il a **réellement** collectés.
Un thème qui échoue n'est pas dans cette liste : sa dernière collecte réussie
survit intacte. Avec un fichier unique réécrit d'un bloc, ce même échec effaçait
ses lieux sans que le décompte final ne bouge de façon lisible.

## Format

Du JSON, un lieu par ligne, trié par Q-id. C'est du JSON valide, et le dépôt
montre « trois lieux ajoutés » là où un document réindenté montrerait un fichier
entier réécrit.

## Les deux sens

```bash
python -m roam_pipeline sync                  # dépôt → copie de travail
python -m roam_pipeline sync --depuis-la-copie  # copie de travail → dépôt
```

`fetch`, `enrich`, `discover` et `adopt` écrivent ici automatiquement : le
second sens ne sert qu'à verser une collecte antérieure à ce découpage.
