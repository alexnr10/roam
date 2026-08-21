# Démarrer Roam sur ton téléphone

À faire une fois, depuis un ordinateur. Ensuite tu pourras itérer depuis le téléphone :
le serveur recharge l'app à chaque modification du code.

Compte 15 minutes la première fois, dont l'essentiel en téléchargement.

## Avant de commencer

| Sur l'ordinateur | Sur le téléphone |
|---|---|
| **Node.js 20 ou plus** — [nodejs.org](https://nodejs.org), version LTS | **Expo Go** — App Store ou Play Store |
| **Git** | |

Vérifier Node : `node --version` doit afficher `v20.x` ou plus.

L'ordinateur et le téléphone doivent être **sur le même réseau Wi-Fi**.

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
| Le QR code scanne mais rien ne charge | Téléphone et ordinateur sur des réseaux différents, ou Wi-Fi d'entreprise qui isole les appareils | `npx expo start --tunnel` (plus lent, mais passe partout) |
| `command not found: npx` | Node.js absent ou mal installé | Réinstaller Node.js LTS, rouvrir le terminal |
| Erreurs pendant `npm install` | Cache abîmé | `rm -rf node_modules package-lock.json && npm install` |
| L'app se lance mais la carte est vide | Permission de localisation refusée | Réglages du téléphone → Expo Go → Localisation |

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
