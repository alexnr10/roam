# Roam — concept et décisions actées

> « Collectionner le monde », en commençant par la France.

## 1. Le principe

L'unité de base est le **lieu**. Un lieu alimente **plusieurs collections à la fois** :

- **thématiques** — châteaux, cascades, plages, abbayes, sommets…
- **géographiques** — commune, département, région, pays
- **labellisées** — Plus Beaux Villages de France, Grands Sites de France, UNESCO…

L'utilisateur valide un lieu en s'y rendant. Il progresse en pourcentage sur chaque
collection, débloque des badges à des paliers, et monte de niveau dans une collection.

Le différenciant n'est pas la couverture, c'est **la curation** : peu de lieux, mais qui
valent le déplacement. Une collection doit rester **finissable**.

## 2. Les paliers (le mécanisme central)

Chaque collection est découpée en trois niveaux, par ordre de qualité décroissante :

| Niveau | Taille visée | Contenu |
|---|---|---|
| 1 | ~10 lieux | les incontournables, ceux que tout le monde cite |
| 2 | ~25 lieux | la deuxième ligne, très bons mais moins connus |
| 3 | reste, plafonné | les pépites locales, pour les complétistes |

Ce découpage résout trois problèmes d'un coup :

1. **la sévérité de la sélection** — pas de choix binaire « dedans / dehors », un curseur ;
2. **la densité locale** — un utilisateur en zone creuse a quand même du niveau 3 à faire ;
3. **la progression** — monter de niveau, c'est débloquer le palier suivant.

Le niveau 1 se termine en une saison : c'est l'accroche.

## 3. Validation d'une visite

- **GPS = mode par défaut.** Rayon adapté au type de lieu (80 m pour une chapelle,
  jusqu'à 2 km pour un site naturel étendu). Détection d'arrivée → notification
  « tu es à 300 m du Château de X, il te manque pour finir ta collection ».
  La validation est une récompense, pas une formalité.
- **Photo = optionnelle et gratifiante.** Elle alimente le carnet de voyage personnel et
  donne un bonus. Jamais une condition — une photo obligatoire transformerait le jeu en corvée.
- **Déclaratif = onboarding.** L'utilisateur peut cocher les lieux visités *avant* l'app,
  sinon il démarre à 0 % partout et décroche. Les visites déclarées comptent dans le
  pourcentage ; seules les visites vérifiées au GPS donnent le badge « vérifié ».

Anti-triche : le spoofing GPS est trivial sur Android. Tant qu'il n'y a pas de classement
compétitif à enjeu, ce n'est pas un problème — ne pas sur-ingénierer.

## 4. Décisions actées

| Sujet | Décision |
|---|---|
| Périmètre | France uniquement en v1. Le modèle reste multi-pays (`country_code`). |
| Géométrie d'un lieu | **Toujours un point.** Pour un site étendu (gorges, massif), on prend le point d'entrée ou le point de vue emblématique ; c'est le rayon de validation qui porte la taille. |
| Cible | Les deux profils — l'habitant qui fait des week-ends près de chez lui, et le voyageur. Départage par le profil utilisateur, pas par le catalogue. |
| Social | Prévu, mais **v2**. Le modèle de données le réserve (pas de refonte plus tard). |
| Contribution communautaire | Oui, encadrée par une charte (`docs/curation-charter.md`) et une modération. |
| Feedback communautaire | Oui : les utilisateurs peuvent faire monter, descendre ou sortir un lieu — en signal, jamais en automatique. |
| Curation finale | **Validation humaine obligatoire.** Le pipeline propose et classe, il ne publie pas. |
| Labels | Les référencements existants servent à la fois de **signal de qualité** et de **collections dédiées**. |
| Monétisation | Reportée. Contrainte retenue dès maintenant : le catalogue reste **côté serveur**, jamais entièrement embarqué en clair dans le client. |

## 5. Contraintes du projet

Développeur seul, **budget zéro**. La pile est choisie pour tenir sur des offres gratuites :

- **App** — Expo / React Native (une base de code iOS + Android)
- **Backend** — Supabase (Postgres + PostGIS + Auth + Storage), palier gratuit
- **Carte** — MapLibre GL, fonds de carte à héberger soi-même (PMTiles) ou palier gratuit
- **Pipeline de curation** — scripts Python hors ligne, sortie versionnée dans le dépôt

La seule ressource réellement coûteuse est **le temps éditorial** de validation du
catalogue. C'est aussi la barrière à l'entrée du produit.

## 6. Chemin critique

1. **Catalogue** ← *on est ici*. Sans lieux, il n'y a pas d'app.
2. Schéma de base + import du catalogue
3. Prototype Expo : carte, fiche lieu, check-in GPS
4. Progression, paliers, badges
5. Contribution et feedback communautaires
6. Social
