import type { Coordinates, Place } from '../types';

/**
 * L'ordre du bandeau sous la carte.
 *
 * L'application est d'abord un guide : on y cherche quoi faire autour de soi
 * ou sur la route d'un voyage. Le bandeau répond à cette question en photos,
 * et l'ordre où il les pose EST la réponse.
 *
 * Il y avait ici, jusqu'à la carte native, un plafond de marqueurs : chacun
 * était un composant React, et deux mille composants pour vingt points
 * visibles faisaient ramer la carte. Les deux cartes dessinent maintenant
 * leurs lieux dans une couche MapLibre, sur le processeur graphique — le
 * plafond n'avait plus rien à plafonner.
 */

/** Distance en mètres entre deux points, par la formule de haversine. */
function metres(a: Coordinates, lat: number, lon: number): number {
  const R = 6_371_000;
  const dLat = ((lat - a.latitude) * Math.PI) / 180;
  const dLon = ((lon - a.longitude) * Math.PI) / 180;
  const lat1 = (a.latitude * Math.PI) / 180;
  const lat2 = (lat * Math.PI) / 180;
  const h =
    Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
}

/**
 * L'ordre du bandeau sous la carte.
 *
 * Avec une position, le plus proche d'abord : « qu'est-ce qu'il y a autour de
 * moi » est la question qu'on pose le plus souvent. Sans position, le mieux
 * classé d'abord — un guide ouvert au hasard doit tomber sur ce qui vaut le
 * détour, pas sur le premier lieu du fichier.
 */
export function bandeau(
  places: Place[],
  position: Coordinates | null,
  combien: number,
): Place[] {
  const lot = [...places];
  if (!position) {
    lot.sort((a, b) => b.score - a.score || a.name.localeCompare(b.name));
    return lot.slice(0, combien);
  }
  return lot
    .map((place) => ({ place, d: metres(position, place.lat, place.lon) }))
    .sort((a, b) => a.d - b.d)
    .slice(0, combien)
    .map((entry) => entry.place);
}
