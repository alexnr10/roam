# Monaco n'a pas de subdivision au deuxième échelon

Les deux fichiers sont VIDES, et c'est une donnée, pas un oubli.

Monaco se divise en quartiers — Monaco-Ville, La Condamine, Monte-Carlo, la
Moneghetti, Fontvieille, le Larvotto et les autres. C'est la maille d'un
QUARTIER, pas d'une région ni d'un département : le pays fait deux kilomètres
carrés, le plus petit État du monde après le Vatican.

Les remplir en appelant les quartiers des « régions » donnerait une poignée de
collections régionales d'un ou deux lieux, là où le pays entier en comptera
quelques dizaines au mieux. Le dépôt écarte déjà les collections trop maigres
(`min_places`) ; il n'y a pas de raison d'en fabriquer.

Les fichiers existent quand même, parce que leur PRÉSENCE dit qu'on a répondu à
la question. Voir `data/reference/va/README.md`, qui raconte ce que coûtait
leur absence : le premier `build --pays-config va` plantait sur un
`FileNotFoundError`, et rien ne disait quoi mettre dedans.

Si les quartiers devaient un jour servir, c'est comme COMMUNES qu'ils
entreraient — la maille la plus fine de la carte de conquête. Monte-Carlo est
un quartier, pas une ville.
