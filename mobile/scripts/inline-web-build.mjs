/**
 * Replie le build web en une seule page HTML.
 *
 * Sert à faire relire l'application sur un téléphone sans PC ni hébergeur :
 * une page autonome se publie et s'ouvre n'importe où. Le fragment produit n'a
 * ni `<html>` ni `<head>` — l'hôte les fournit.
 *
 * Ce que la page NE peut pas faire : joindre le serveur de tuiles, ni charger
 * le worker de MapLibre, qui vit dans un fichier voisin. L'onglet Carte reste
 * donc en fond dégradé ; tout le reste fonctionne.
 */
import { readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const dist = join(here, '..', 'dist');
const out = process.argv[2] ?? join(dist, 'roam-apercu.html');

const pick = (folder, extension) => {
  const found = readdirSync(join(dist, folder)).filter((name) => name.endsWith(extension));
  if (found.length !== 1) {
    throw new Error(`${folder} : ${found.length} fichiers ${extension}, un seul attendu`);
  }
  return readFileSync(join(dist, folder, found[0]), 'utf8');
};

const css = pick('_expo/static/css', '.css');
const js = pick('_expo/static/js/web', '.js');

// Le worker de MapLibre et le module qu'il importe, embarqués tels quels. La
// page les reconstitue en blobs : sans worker, MapLibre ne traite AUCUNE
// donnée — ni tuiles, ni sources GeoJSON — et la carte reste grise sans lever
// la moindre erreur.
const worker = readFileSync(join(dist, 'maplibre', 'maplibre-gl-worker.mjs'), 'utf8');
const shared = readFileSync(join(dist, 'maplibre', 'maplibre-gl-shared.mjs'), 'utf8');

// Le reset de react-native-web, repris du gabarit d'Expo : sans lui la racine
// n'occupe pas la hauteur et l'application se replie sur quelques pixels.
const reset = `
  html, body { height: 100%; }
  body { overflow: hidden; }
  #root { display: flex; height: 100%; flex: 1; }
`;

// Une chaîne du bundle contenant « </script> » refermerait la balise au milieu
// du code. L'échappement est sans effet sur la valeur de la chaîne.
const safe = js.replaceAll('</script', '<\\/script');

// Expo Router lit `location.pathname` pour choisir la route. Publiée sous un
// chemin quelconque, la page demanderait donc une route qui n'existe pas et
// n'afficherait qu'« Unmatched Route ». On ramène le chemin à la racine avant
// que le bundle ne s'exécute — même origine, donc autorisé, sauf en `file://`
// où l'échec est sans conséquence puisque rien n'y est publié.
const bootstrap = `
  // Expo Router lit \`location.pathname\` au démarrage pour choisir la route.
  // Publiée sous un chemin quelconque, la page demanderait une route qui
  // n'existe pas et n'afficherait qu'« Unmatched Route ».
  //
  // Trois gestes, dans cet ordre : ramener le chemin à la racine avant que le
  // bundle ne s'exécute, empêcher le routeur d'écrire l'onglet courant dans
  // l'adresse, puis rendre l'adresse d'origine une fois l'application montée —
  // faute de quoi un rafraîchissement partirait sur « / » ou sur « /conquete »,
  // que l'hébergeur ne connaît pas.
  var initial = location.href;
  var replace = history.replaceState.bind(history);
  try {
    if (location.pathname !== '/') replace(null, '', '/');
  } catch (error) {
    console.warn('Roam : chemin non réinitialisable', error);
  }

  ['pushState', 'replaceState'].forEach(function (method) {
    var native = history[method].bind(history);
    history[method] = function (state) { native(state, '', location.href); };
  });

  addEventListener('load', function () {
    setTimeout(function () {
      try { replace(null, '', initial); } catch (error) {}
    }, 0);
  });

  // Le worker de MapLibre, fabriqué sur place. Il importe son module partagé
  // par un chemin relatif, que le blob n'a pas : on réécrit le spécificateur
  // vers un second blob. Si la politique de sécurité de l'hôte refuse les
  // workers en blob, l'application retombe sur son fond dégradé — les lieux
  // s'affichent, la carte reste grise, rien ne casse.
  try {
    var sharedUrl = URL.createObjectURL(
      new Blob([SHARED_SOURCE], { type: 'text/javascript' })
    );
    var workerSource = WORKER_SOURCE.replace('./maplibre-gl-shared.mjs', sharedUrl);
    window.__ROAM_MAPLIBRE_WORKER__ = URL.createObjectURL(
      new Blob([workerSource], { type: 'text/javascript' })
    );
  } catch (error) {
    console.warn('Roam : worker MapLibre indisponible', error);
  }
`;

writeFileSync(
  out,
  [
    '<title>Roam</title>',
    `<style>${reset}\n${css}</style>`,
    '<div id="root"></div>',
    // Les sources du worker passent par des constantes JSON : elles
    // contiennent des apostrophes, des accents graves et des barres obliques
    // que toute autre forme de citation trahirait.
    `<script>const WORKER_SOURCE = ${JSON.stringify(worker)};\n` +
      `const SHARED_SOURCE = ${JSON.stringify(shared)};\n${bootstrap}</script>`,
    `<script>${safe}</script>`,
    '',
  ].join('\n'),
  'utf8',
);

const size = (Buffer.byteLength(readFileSync(out)) / 1024 / 1024).toFixed(1);
console.log(`page autonome écrite : ${out} (${size} Mo)`);
