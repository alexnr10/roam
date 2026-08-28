# Démarrer Roam sur ton téléphone

À faire une fois, depuis un ordinateur. Ensuite tu pourras itérer depuis le téléphone :
le serveur recharge l'app à chaque modification du code.

Compte 15 minutes la première fois, dont l'essentiel en téléchargement.

## Le plus simple : l'aperçu publié

Chaque poussée sur le dépôt reconstruit l'application et la publie. Rien à
installer, rien à allumer :

**https://alexnr10.github.io/roam/**

C'est une vraie adresse en HTTPS, ce qui change deux choses par rapport à un
serveur de développement joint par le Wi-Fi : le fond de carte se charge, et
**le navigateur autorise la géolocalisation** — la validation par GPS est donc
éprouvable depuis le téléphone.

La page embarque le catalogue tel qu'il est **dans le dépôt**. Pour y voir le
tien, il faut l'y mettre :

```bash
python -m roam_pipeline export-app
git add mobile/src/data/catalog.json pipeline/data/manual/*.csv
git commit -m "Catalogue du <date>" && git push
```

Deux ou trois minutes plus tard, l'adresse sert la nouvelle version. Tout se
fait donc depuis un téléphone sous Termux, sans jamais rallumer le Mac.

> Si le dépôt est privé et le forfait GitHub gratuit, Pages n'est pas
> disponible : la page reste récupérable en pièce jointe de la construction,
> sous l'onglet **Actions** du dépôt. Rendre le dépôt public lève la
> limitation.

## Relire depuis le téléphone

```bash
python -m roam_pipeline review --host 0.0.0.0
```

La commande affiche alors une adresse en `192.168.x.x` à ouvrir dans Chrome.

Le défaut `127.0.0.1` suffit sur un ordinateur, mais sur certains Android
Chrome n'atteint pas la boucle locale d'une autre application : la connexion
est refusée alors que le serveur tourne. Passer par l'adresse de l'appareil sur
le Wi-Fi contourne le problème — la requête sort et revient par l'interface
réseau au lieu de rester à l'intérieur.

> La page est alors lisible par tout le monde sur le même réseau. Chez soi
> c'est sans conséquence ; dans un train, préfère attendre.

Garde Termux au premier plan, ou pose un `termux-wake-lock` avant : Android tue
volontiers les processus en arrière-plan, et le serveur avec.

## Avant de commencer

| Sur l'ordinateur | Sur le téléphone |
|---|---|
| **Node.js 20 ou plus** — [nodejs.org](https://nodejs.org), version LTS | **Expo Go** — App Store ou Play Store |
| **Git** | |

Vérifier ce qui est déjà là, dans le Terminal :

```bash
node --version    # doit afficher v20.x ou plus
git --version     # doit afficher une version, cf. ci-dessous si ce n'est pas le cas
```

L'ordinateur et le téléphone doivent être **sur le même réseau Wi-Fi**.

### Installer Git sur macOS

macOS ne livre pas Git, mais il sait l'installer seul. Tape `git --version` dans le
Terminal : une fenêtre propose alors d'installer les **outils de développement en ligne
de commande**. Accepter, patienter (~5 min, environ 1 Go), et c'est fini. Aucun compte,
aucun téléchargement à chercher.

En ligne de commande directement, c'est la même chose :

```bash
xcode-select --install
```

Si la fenêtre indique que les outils sont déjà installés, c'est que Git est là — vérifier
avec `git --version`.

#### Erreur `xcrun: error: invalid active developer path`

Message typique après une mise à jour de macOS : le chemin vers les outils est enregistré,
mais le dossier est vide ou incomplet. D'abord la solution douce :

```bash
sudo xcode-select --reset
git --version
```

Si l'erreur persiste, il faut réinstaller. La suppression ne touche que les outils en
ligne de commande, qui sont réinstallés juste après — ni le projet, ni les autres
applications ne sont concernés :

```bash
sudo rm -rf /Library/Developer/CommandLineTools
xcode-select --install
```

Si l'installateur répond que le logiciel *n'est pas disponible sur le serveur de mise à
jour* — panne connue chez Apple —, télécharger le paquet « Command Line Tools for Xcode »
à la main sur [developer.apple.com/download/all](https://developer.apple.com/download/all)
(identifiant Apple gratuit requis), en prenant la version correspondant à ton macOS.

**Cette erreur ne bloque que Git.** Node et npm sont installés séparément et ne dépendent
pas des outils Xcode : tu peux lancer l'app tout de suite par le ZIP ci-dessous pendant
que l'installation se règle.

### Se passer de Git

Git n'est pas indispensable pour lancer l'app une première fois. Sur la page du dépôt :

1. cliquer sur le sélecteur de branche (il affiche `main`) et choisir
   `claude/roam-location-collection-app-uq63os` ;
2. bouton vert **Code** → **Download ZIP** ;
3. double-cliquer le ZIP téléchargé, puis dans le Terminal :

```bash
cd ~/Downloads/roam-claude-roam-location-collection-app-uq63os/mobile
npm install
npx expo start
```

⚠️ **Sans Git, il faudra retélécharger le ZIP à chaque nouvelle version.** Comme on va
itérer, autant installer Git tout de suite : un `git pull` suffira ensuite à récupérer
les modifications, sans rien perdre de ce que tu auras testé.

## Les commandes, dans l'ordre

```bash
git clone https://github.com/alexnr10/roam.git
cd roam
git checkout claude/roam-location-collection-app-uq63os

cd mobile
npm install          # ~2 min, télécharge les dépendances
npx expo start
```

Un QR code s'affiche dans le terminal.

- **iPhone** : le scanner avec l'appareil photo, puis ouvrir le lien proposé.
- **Android** : ouvrir Expo Go, « Scan QR code », scanner.

L'app se télécharge sur le téléphone (~30 s la première fois), puis se lance.
**Accepter la demande de localisation** quand elle apparaît : sans elle, la
validation GPS ne peut pas fonctionner.

## Si ça ne marche pas

| Symptôme | Cause probable | Solution |
|---|---|---|
| « Project is incompatible with this version of Expo Go » | Expo Go en retard : il ne prend en charge que le SDK le plus récent | Mettre Expo Go à jour depuis l'App Store / Play Store, cf. ci-dessous |
| Le QR code scanne mais rien ne charge | Téléphone et ordinateur sur des réseaux différents, ou Wi-Fi d'entreprise qui isole les appareils | `npx expo start --tunnel` (plus lent, mais passe partout) |
| `command not found: npx` | Node.js absent ou mal installé | Réinstaller Node.js LTS, rouvrir le terminal |
| `xcrun: error: invalid active developer path` | Outils en ligne de commande cassés par une mise à jour de macOS | `sudo xcode-select --reset`, cf. section Git ci-dessus |
| `EACCES: permission denied` sur `npm install -g` | Installation globale dans un dossier système | Passer par `npx eas-cli@latest …`, jamais `sudo` |
| `zsh: command not found: python` | Environnement virtuel non activé dans ce terminal | `source .venv/bin/activate` depuis `pipeline/` |
| Erreurs pendant `npm install` | Cache abîmé | `rm -rf node_modules package-lock.json && npm install` |
| L'app se lance mais la carte est vide | Permission de localisation refusée | Réglages du téléphone → Expo Go → Localisation |

## Expo Go dit que le projet est incompatible

Expo Go ne sait faire tourner que **le SDK le plus récent**. Le projet est sur le SDK 57 ;
si l'app installée est plus ancienne, elle refuse de l'ouvrir. Le message nomme les deux
versions — c'est lui qui dit laquelle Expo Go accepte.

1. **Mettre Expo Go à jour.** App Store (icône de profil → liste des mises à jour) ou
   Play Store (profil → Gérer les applications). Si le bouton affiche « Ouvrir » et non
   « Mettre à jour », désinstaller puis réinstaller force la dernière version.
2. Relancer ensuite le serveur proprement : `npx expo start -c` (le `-c` vide le cache,
   qui garde parfois l'ancienne version en mémoire).

Si Expo Go est déjà à jour et refuse toujours, c'est que le téléphone est trop ancien
pour la dernière version de l'app : l'App Store installe alors la dernière version
compatible avec le système, qui peut être bloquée sur un SDK antérieur. Dans ce cas c'est
**le projet** qu'il faut ramener au SDK pris en charge, avec `npx expo install --fix`
après avoir changé la version d'`expo` dans `mobile/package.json`.

En attendant, `npx expo start` puis la touche **`w`** ouvre l'application dans le
navigateur du Mac : tout fonctionne sauf la carte native et le GPS réel.

## Installer l'application sur un téléphone Android

Expo Go a besoin d'un serveur de développement, et sa version en magasin peut être en
retard sur le SDK du projet. Pour avoir Roam installé comme une vraie application, la voie
est **EAS Build** : la compilation se fait dans le cloud d'Expo, gratuitement, et rend un
fichier `.apk` qu'Android sait installer directement.

```bash
npx eas-cli@latest login     # compte Expo gratuit, à créer si besoin
cd mobile
npx eas-cli@latest build --platform android --profile preview
```

`npx` exécute l'outil sans l'installer dans les dossiers système : c'est ce qui évite le
`EACCES: permission denied` que renvoie `npm install -g` sur un Mac. Inutile de passer par
`sudo` — installer un outil de développement en administrateur crée plus de problèmes
qu'il n'en règle.

Le profil `preview` est déjà configuré dans `eas.json` pour produire un APK plutôt qu'un
paquet destiné au Play Store. La compilation part en file d'attente — compte dix à trente
minutes sur l'offre gratuite — puis la commande affiche un lien de téléchargement, avec un
QR code à scanner depuis le téléphone.

Android demandera d'autoriser l'installation depuis une source inconnue : c'est normal
pour une application qui ne vient pas du Play Store.

### ⚠️ La carte sera grise sans clé Google Maps

Dans Expo Go, `react-native-maps` utilise la clé de Google fournie par Expo. Une
application autonome doit avoir la sienne, sans quoi la carte s'affiche vide — le reste
de l'application fonctionne normalement.

Trois options, par ordre de coût :

| Option | Ce que ça demande | Résultat |
|---|---|---|
| Vivre avec la carte grise | rien | liste, validation, collections et badges marchent ; la carte est vide |
| Clé Google Maps | un compte Google Cloud avec facturation activée — gratuit sous quota, mais carte bancaire exigée | carte complète |
| Migrer vers MapLibre | du travail de développement | carte complète, sans clé ni compte, et c'est de toute façon nécessaire pour la carte de conquête |

La clé se pose dans `app.json`, sous `expo.android.config.googleMaps.apiKey`.

**La troisième option est la bonne à terme.** MapLibre ne demande ni clé ni compte, et le
coloriage des territoires (`docs/carte-de-conquete.md`) l'exigera de toute façon. Ce n'est
pas la peine de payer un détour par Google si c'est pour le défaire ensuite.

## Ce qu'il faut regarder

Le catalogue de démonstration contient 46 lieux répartis dans toute la France, donc tu
ne seras probablement à côté d'aucun. Pour éprouver la boucle malgré tout : ouvre une
fiche de lieu et utilise « **j'y suis déjà allé** » — l'écran de validation se déclenche
pareil, seul le badge « vérifié » manque.

Trois questions à te poser en manipulant :

1. **Le moment de validation donne-t-il quelque chose ?** C'est le cœur du jeu.
2. **Les collections donnent-elles envie ?** Est-ce qu'on voit ce qu'on va gagner ?
3. **Le verrouillage du niveau 2 frustre-t-il ou motive-t-il ?**

## Ensuite, si tu veux avancer sur le catalogue

```bash
cd ../pipeline
python3 -m venv .venv && source .venv/bin/activate   # Windows : .venv\Scripts\activate
pip install -r requirements.txt

python -m roam_pipeline verify-qids   # ⚠️ à faire avant tout le reste
```

> **À chaque nouveau terminal, réactive l'environnement.** `python` (sans le `3`)
> n'existe qu'à l'intérieur : un onglet neuf répond `command not found: python`.
>
> ```bash
> cd ~/Documents/Roam/roam/pipeline
> source .venv/bin/activate
> ```
>
> L'invite affiche alors `(.venv)` en tête de ligne. C'est le seul signe fiable.

`verify-qids` affiche le libellé réel de chaque identifiant Wikidata de la
configuration. Un identifiant erroné ne provoque aucune erreur : il renvoie zéro
résultat. C'est le bug le plus silencieux du pipeline, et il coûte une collecte
complète.

Si tout est vert :

```bash
python -m roam_pipeline fetch    # 15-30 min, Wikidata limite le débit
python -m roam_pipeline build    # produit data/out/review.csv
```

`review.csv` est la feuille de revue éditoriale — la vraie matière du projet.
