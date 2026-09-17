# Le Vatican n'a aucune subdivision administrative

Les deux fichiers sont VIDES, et c'est une donnée, pas un oubli : l'État de la
Cité du Vatican fait quarante-quatre hectares et ne se divise en rien. Il n'a
ni région ni province, et il n'en aura pas.

Les fichiers existent quand même, parce que leur PRÉSENCE dit qu'on a répondu à
la question. Un dossier absent voudrait dire « personne n'a regardé » — et
c'est ce qui s'est produit au premier `build --pays-config va`, qui a échoué
sur un `FileNotFoundError` sans expliquer ce qu'il attendait.

Deux conséquences, et les deux sont voulues :

- `geo.require_departement: false` dans `config/va/scoring.yaml`. Sans lui, un
  lieu sans département sortirait du catalogue avant d'être jugé, et le
  catalogue du Vatican serait vide.
- La carte de conquête n'a aucune région à colorier : elle retombe sur la
  liste, qui dit la même chose sans dessin. C'est prévu.
