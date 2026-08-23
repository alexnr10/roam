/**
 * Copie le worker de MapLibre dans `public/`.
 *
 * MapLibre délègue à un web worker tout le traitement des données — tuiles
 * vectorielles comme sources GeoJSON. Il le charge depuis un fichier voisin de
 * son propre bundle, mais Metro regroupe tout en un seul fichier et n'émet pas
 * ce voisin : le worker répond alors 404, et la carte reste muette sans lever
 * la moindre erreur. Ni le fond, ni les lieux ne s'affichent.
 *
 * Les deux fichiers sont donc copiés dans `public/`, qu'Expo sert à la racine
 * du site, et `setWorkerUrl` les y envoie chercher. Ils sont recopiés à chaque
 * installation pour rester alignés sur la version installée.
 */
import { copyFileSync, mkdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const from = join(here, '..', 'node_modules', 'maplibre-gl', 'dist');
const to = join(here, '..', 'public', 'maplibre');

// Le worker importe le module partagé par un chemin relatif : les deux doivent
// rester côte à côte.
const FILES = ['maplibre-gl-worker.mjs', 'maplibre-gl-shared.mjs'];

try {
  mkdirSync(to, { recursive: true });
  for (const file of FILES) copyFileSync(join(from, file), join(to, file));
  console.log(`maplibre : ${FILES.length} fichiers copiés dans public/maplibre/`);
} catch (error) {
  console.warn(`maplibre : copie du worker impossible (${error.message})`);
  console.warn('La carte web ne fonctionnera pas tant que ce fichier manque.');
}
