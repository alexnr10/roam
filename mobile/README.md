# Application Roam (prototype)

Expo / React Native, une base de code iOS + Android.

## Lancer

```bash
cd mobile
npm install
npx expo start
```

Puis scanner le QR code. La géolocalisation, les listes, la recherche, la validation
et la progression marchent partout — y compris dans **Expo Go**, où l'app le dit
franchement : la carte y affiche « carte indisponible ici » plutôt que de tomber.

**La carte demande une application compilée.** MapLibre est un module natif, absent
d'Expo Go par construction. Une seule compilation suffit, ensuite on développe comme
avant :

```bash
npx eas-cli@latest build --platform android --profile development
# puis, à chaque session :
npx expo start --dev-client
```

À refaire uniquement quand une dépendance native change — pas à chaque modification
de code.

```bash
npm test           # logique métier (distances, validation, progression, badges)
npm run typecheck  # TypeScript strict
npm run glyphes    # réengendre les icônes de thèmes de la carte native
npm run export:web # build web autonome dans dist/
```

## Aperçu web

`npm run export:web` produit une version web utilisable sans installer quoi que ce
soit — pratique pour montrer la boucle à quelqu'un, ou pour se faire une idée depuis
un téléphone sans serveur de développement.

Une seule différence avec l'app, et elle est volontaire :

- **un bouton « me téléporter ici »** apparaît sur chaque fiche lieu, pour éprouver le
  moment de validation sans faire la route. Il est strictement réservé au web
  (`Platform.OS === 'web'`) : sur téléphone, seul le vrai GPS fait foi, sans quoi le
  jeu n'a plus de sens.

La carte, elle, est la même des deux côtés : même moteur, mêmes couches, mêmes
couleurs. C'est le web qui servait autrefois d'aperçu de ce que le natif ne savait
pas faire ; il n'y a plus d'écart à montrer.

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

## Installer sur un téléphone Android

```bash
npx eas-cli@latest login
npx eas-cli@latest build --platform android --profile preview
```

`npx` évite l'installation globale, qui échoue en `EACCES` sur un Mac.

Rend un APK installable directement. Aucune clé d'API : le fond de carte vient
d'OpenFreeMap, qui sert des tuiles vectorielles sans compte.

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
  MapCanvas.tsx         carte native (MapLibre)
  MapCanvas.web.tsx     carte web (MapLibre GL JS)
  couches.ts            LES COUCHES, pour les deux — une seule définition
  mapStyle.ts           couleurs, expressions, fond repeint
assets/glyphes/         icônes de thèmes en images, engendrées
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
- **La carte demande une application compilée** : MapLibre est un module natif, et
  Expo Go ne le porte pas. C'était le prix à payer pour que les deux plateformes
  aient la MÊME carte — mêmes aplats de régions, mêmes pastilles graduées, mêmes
  symboles de thèmes — au lieu d'une carte dessinée et d'une pluie d'épingles.
- **Les fondus de la carte native sont plus simples que ceux du web** : les lieux
  d'une région y arrivent en un fondu, là où le web les fait apparaître en cascade
  depuis le centre. Animer image par image demanderait de traverser le pont soixante
  fois par seconde ; le SDK natif interpole lui-même, mais d'un seul tenant.
- **Pas encore de carte de conquête sur natif** : elle attend d'être portée sur le
  même moteur. La liste, elle, fonctionne partout — et elle dit ce qu'il RESTE à
  faire, là où un aplat de couleur ne dit que ce qui est fait.
- **Pas de photo** pour l'instant : elle est prévue comme bonus optionnel, jamais
  comme condition de validation.
