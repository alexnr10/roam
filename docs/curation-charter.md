# Charte de curation Roam

> Brouillon à valider. C'est le document le plus important du projet : il définit ce que
> Roam est, en creux. Vagabond référence la moindre chapelle de village ; Roam ne
> référence que ce qui justifie de faire la route.

## 1. Le test d'entrée

Un lieu entre dans Roam s'il passe cette question :

> **« Est-ce que quelqu'un ferait 45 minutes de route uniquement pour voir ça ? »**

Si la réponse est « seulement si on passe devant », le lieu ne rentre pas. Il n'existe pas
de niveau 4.

## 2. Critères d'inclusion

Un lieu doit satisfaire **le test d'entrée** et **au moins un** critère objectif :

| # | Critère | Vérifiable via |
|---|---|---|
| C1 | Porte un label national ou international | UNESCO, Grand Site de France, Plus Beaux Villages, Jardin Remarquable, Pavillon Bleu… |
| C2 | Protégé au titre des Monuments Historiques **et** dispose d'un article Wikipédia | base Mérimée + Wikidata |
| C3 | Article Wikipédia présent dans ≥ 4 langues | Wikidata (`sitelinks`) |
| C4 | Site naturel remarquable dans un parc national ou un PNR | OSM + périmètres officiels |
| C5 | Notoriété locale forte et documentée, sans les critères ci-dessus | validation manuelle, quota limité |

C5 est la soupape pour les pépites que les bases institutionnelles ratent — cascades,
points de vue, curiosités géologiques. C'est aussi la porte d'entrée du dépôt
communautaire, donc la plus surveillée.

## 3. Critères d'exclusion

Un lieu est refusé, même s'il coche un critère d'inclusion, si :

- **il est fermé au public** ou visible depuis nulle part (propriété privée sans accès) ;
- **il n'est pas atteignable** raisonnablement (danger, interdiction, accès réglementé) ;
- **il est banal dans sa catégorie** — l'église du village, le lavoir, le monument aux morts,
  le énième donjon en ruine sans intérêt ni accès ;
- **il fait doublon** avec un lieu déjà présent (deux points pour le même site) ;
- **il est fragile** et la fréquentation lui nuit (site archéologique sensible, grotte ornée,
  habitat d'espèce protégée) — Roam envoie des gens sur place, c'est une responsabilité ;
- **il est éphémère** (exposition, festival, installation temporaire).

## 4. Le score

Le pipeline calcule un score indicatif pour **classer**, pas pour décider :

```
score = notoriété (log des versions linguistiques Wikipédia)
      + bonus de label   (UNESCO > Grand Site ≈ Plus Beaux Villages > Jardin Remarquable…)
      + bonus patrimonial (classé > inscrit)
      + bonus iconographique (image disponible sur Wikimedia Commons)
```

Le nombre de **versions linguistiques** de l'article Wikipédia est le meilleur signal
gratuit dont on dispose : il sépare remarquablement bien le lieu d'intérêt réel du clocher
de village, et il n'est pas manipulable comme un avis Google. Les avis Google, eux, ne
servent **jamais** à sélectionner — au mieux à repérer une anomalie (2,8/5 sur 400 avis
mérite un coup d'œil).

## 5. Attribution des niveaux

Le niveau est **relatif à chaque collection thématique**, pas absolu :

- niveau 1 → les 10 meilleurs scores de la collection
- niveau 2 → les 25 suivants
- niveau 3 → le reste, jusqu'au plafond

Un plancher de score absolu s'applique quand même : une collection peut avoir moins de
10 lieux au niveau 1 si le vivier ne suit pas. **On ne remplit pas pour remplir.**

## 6. Contribution communautaire

Un utilisateur peut proposer un lieu. La proposition doit fournir :

1. une **position** (le point exact, ou le point d'entrée si le site est étendu) ;
2. le **critère d'inclusion** revendiqué (C1–C5) avec sa source ;
3. une **photo prise sur place** ;
4. deux phrases sur **pourquoi ça vaut le déplacement**.

Rien n'est publié automatiquement. Une proposition passe en `pending`, puis en revue
manuelle. Un contributeur dont les propositions sont régulièrement acceptées voit ses
suivantes remonter en priorité de file — sans jamais court-circuiter la revue.

## 7. Feedback sur les lieux existants

Sur chaque lieu visité, l'utilisateur peut voter : **promouvoir**, **conserver**,
**rétrograder**, **retirer**. Ces votes ne modifient jamais le catalogue directement — ils
alimentent une file de revue.

Seuils de déclenchement d'une revue (à calibrer sur les vrais volumes) :

- ≥ 10 votes sur le lieu, **et**
- ≥ 60 % dans le même sens, **et**
- votes émis par des comptes ayant **effectivement validé le lieu**.

Cette dernière condition est essentielle : seul quelqu'un qui y est allé a le droit de dire
que ça ne valait pas le déplacement. C'est aussi ce qui rend le brigading coûteux.

## 8. Volumes visés (France, v1)

| | Objectif |
|---|---|
| Lieux publiés | 3 000 – 6 000 |
| Collections thématiques | 25 – 40 |
| Lieux par collection | 8 (plancher) – 80 (plafond) |
| Collections géographiques | dérivées, seulement si ≥ 8 lieux |

En dessous de 8 lieux, une collection géographique est absorbée par l'échelon supérieur :
« Cascades de la Creuse : 2 lieux » n'est pas une collection.
