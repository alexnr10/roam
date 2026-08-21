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
npm test          # logique métier (distances, validation, progression, badges)
npm run typecheck # TypeScript strict
```

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

- **Le catalogue est une démonstration** : 46 lieux saisis à la main, coordonnées
  approximatives, notoriété appréciée à l'œil. Il a exactement la forme produite par le
  pipeline de curation, donc le remplacer ne touchera que `src/data/catalog.ts`.
  Régénération : `python3 mobile/scripts/build-demo-catalog.py`.
- **Pas de compte utilisateur** : tout est local à l'appareil. Le branchement Supabase
  viendra avec le vrai catalogue.
- **Carte via `react-native-maps`**, choisi pour fonctionner dans Expo Go sans build
  natif — c'est ce qui permet de tester sur son téléphone tout de suite. Le passage à
  MapLibre + PMTiles est prévu quand il faudra un fond de carte personnalisé, gratuit
  et disponible hors ligne.
- **Pas de photo** pour l'instant : elle est prévue comme bonus optionnel, jamais
  comme condition de validation.
