import type { Coordinates, Place } from '../types';

/**
 * Ce que la carte montre, et dans quel ordre.
 *
 * L'application est d'abord un guide : on y cherche quoi faire autour de soi
 * ou sur la route d'un voyage. La carte n'est donc pas un décor, c'est l'écran
 * principal — et deux mille points ne s'y jettent pas tels quels.
 *
 * Deux contraintes, l'une technique et l'autre humaine :
 *
 * 1. **Le cadre d'abord.** Un point hors de l'écran ne coûte rien à personne
 *    s'il n'est pas dessiné. Sur mobile natif, chaque marqueur est un
 *    composant : deux mille marqueurs pour vingt visibles, c'est la carte qui
 *    rame.
 * 2. **Le meilleur d'abord.** Quand le cadre en contient trop, on garde les
 *    mieux classés. Un guide qui montre tout ne recommande rien : à l'échelle
 *    d'une région, on veut les incontournables, pas les deux cents lieux qui
 *    se chevauchent.
 */

export type Cadre = { ouest: number; sud: number; est: number; nord: number };

export function dansLeCadre(place: Place, cadre: Cadre): boolean {
  return (
    place.lat >= cadre.sud &&
    place.lat <= cadre.nord &&
    place.lon >= cadre.ouest &&
    place.lon <= cadre.est
  );
}

/**
 * Les lieux à dessiner : ceux du cadre, les mieux classés d'abord, plafonnés.
 *
 * Le plafond ne s'applique qu'au DESSIN. La recherche, elle, continue de voir
 * tout le catalogue : ne pas trouver Étretat parce qu'on regarde les Alpes
 * serait absurde.
 */
export function aDessiner(places: Place[], cadre: Cadre | null, plafond: number): Place[] {
  const dedans = cadre ? places.filter((place) => dansLeCadre(place, cadre)) : places;
  if (dedans.length <= plafond) return dedans;
  return [...dedans].sort((a, b) => b.score - a.score).slice(0, plafond);
}

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
