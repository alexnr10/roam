# Application Roam (prototype)

Expo / React Native, une base de code iOS + Android.

## Lancer

```bash
cd mobile
npm install
npx expo start
```

Puis scanner le QR code avec **Expo Go** sur ton téléphone. La géolocalisation
fonctionne dans Expo Go ; si la carte native n'y est pas disponible, l'app le dit et
reste utilisable — liste, validation et progression continuent de marcher.

```bash
npm test           # logique métier (distances, validation, progression, badges)
npm run typecheck  # TypeScript strict
npm run export:web # build web autonome dans dist/
```

## Aperçu web

`npm run export:web` produit une version web utilisable sans installer quoi que ce
soit — pratique pour montrer la boucle à quelqu'un, ou pour se faire une idée depuis
un téléphone sans serveur de développement.

Deux différences avec l'app :

- **la carte est une projection à plat** des lieux sur l'emprise de la France, sans
  fond de carte (`react-native-maps` ne fonctionne pas sur le web, et des tuiles
  demanderaient un service externe) ;
- **un bouton « me téléporter ici »** apparaît sur chaque fiche lieu, pour éprouver le
  moment de validation sans faire la route. Il est strictement réservé au web
  (`Platform.OS === 'web'`) : sur téléphone, seul le vrai GPS fait foi, sans quoi le
  jeu n'a plus de sens.

## Ce que fait le prototype

- **Carte** avec filtre *Tous / À visiter / Visités*, et pastilles colorées selon l'état
- **Détection d'arrivée** : quand tu es dans le rayon d'un lieu non validé, un bandeau
  « Tu y es » propose la validation — c'est l'app qui vient à toi
- **Validation GPS** avec rayon propre à chaque lieu (120 m pour une cathédrale,
  2 km pour des gorges), refusée si le signal est trop imprécis
- **Visite déclarée** (« j'y suis déjà allé ») pour remplir sa carte à l'inscription
- **Collections** par thème, label et géographie, avec pourcentage et prochain palier
- **Niveaux** : le niveau 2 reste verrouillé tant que le niveau 1 n'est pas terminé,
  mais reste visible — on doit voir ce qu'on va gagner
- **Célébration à la validation** : une onde part du médaillon, et les barres des
  collections concernées montent de leur ancien pourcentage au nouveau — c'est le
  mouvement qui récompense, pas le chiffre. Retour haptique sur téléphone, et
  `AccessibilityInfo` respecté si l'utilisateur a réduit les animations
- **Badges** aux paliers 25 / 50 / 75 / 100 % et à chaque niveau terminé
- **Persistance locale** via AsyncStorage

## Organisation

```
app/                    routes expo-router
  (tabs)/index.tsx      carte + lieux autour de moi
  (tabs)/collections    liste des collections et progression
  (tabs)/profil         statistiques et badges
  place/[id].tsx        fiche lieu et validation
  collection/[slug].tsx détail d'une collection, par niveau
src/lib/                logique métier pure — c'est ce qui est testé
src/store/visits.tsx    carnet de visites, persisté
src/data/               catalogue
src/ui/                 composants et carte
```

## Limites connues

- **Le catalogue** est `src/data/catalog.json`, produit par
  `python -m roam_pipeline export-app`. Tant que le pipeline n'a pas tourné, le dépôt
  embarque un jeu de démonstration de la même forme — 46 lieux saisis à la main, aux
  coordonnées approximatives (`python3 mobile/scripts/build-demo-catalog.py`).
- **Descriptions et images viennent de Wikipédia et Wikimedia Commons** (CC BY-SA). La
  fiche d'un lieu cite la source et renvoie vers l'article : c'est une obligation de la
  licence, pas une politesse.
- **Pas de compte utilisateur** : tout est local à l'appareil. Le branchement Supabase
  viendra avec le vrai catalogue.
- **Carte via `react-native-maps`**, choisi pour fonctionner dans Expo Go sans build
  natif — c'est ce qui permet de tester sur son téléphone tout de suite. Le passage à
  MapLibre + PMTiles est prévu quand il faudra un fond de carte personnalisé, gratuit
  et disponible hors ligne.
- **Pas de photo** pour l'instant : elle est prévue comme bonus optionnel, jamais
  comme condition de validation.
