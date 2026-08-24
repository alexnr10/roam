import * as maplibregl from 'maplibre-gl';

/**
 * Où MapLibre va chercher son worker.
 *
 * Sans worker, MapLibre ne traite **aucune** donnée — ni tuiles, ni sources
 * GeoJSON — et la carte reste muette : pas de lieux, pas de territoires, et
 * aucune erreur visible pour le dire. C'est la panne la plus coûteuse de tout
 * l'écran, parce qu'elle ne ressemble pas à une panne.
 *
 * Metro n'émet pas ce fichier : `scripts/sync-maplibre-worker.mjs` le recopie
 * dans `public/maplibre/`, et c'est là qu'on l'envoie chercher. Une page repliée
 * en un seul fichier n'a pas ce voisin ; elle fabrique alors le worker
 * elle-même et en dépose l'adresse dans `window` (cf. `inline-web-build.mjs`).
 *
 * **Appelé explicitement par chaque carte avant de créer la sienne.** Le confier
 * à un effet de bord de module a déjà coûté un écran vide : la carte de conquête
 * n'importait pas celui de la carte des lieux, et ouvrir l'onglet Conquête en
 * premier laissait MapLibre chercher son worker à côté du bundle, où il n'est
 * pas.
 */

declare global {
  interface Window {
    __ROAM_MAPLIBRE_WORKER__?: string;
  }
}

const DEFAULT_WORKER = '/maplibre/maplibre-gl-worker.mjs';

let done = false;

export function prepareMapLibre(): void {
  if (done) return;
  done = true;
  maplibregl.setWorkerUrl(
    (typeof window !== 'undefined' && window.__ROAM_MAPLIBRE_WORKER__) || DEFAULT_WORKER,
  );
}
