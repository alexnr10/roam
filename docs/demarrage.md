# Démarrer Roam sur ton téléphone

À faire une fois, depuis un ordinateur. Ensuite tu pourras itérer depuis le téléphone :
le serveur recharge l'app à chaque modification du code.

Compte 15 minutes la première fois, dont l'essentiel en téléchargement.

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
