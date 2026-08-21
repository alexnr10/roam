import type { Coordinates, Place } from '../types';

const EARTH_RADIUS_M = 6_371_000;

const toRad = (deg: number) => (deg * Math.PI) / 180;

/** Distance orthodromique en mètres. */
export function distanceM(
  lat1: number,
  lon1: number,
  lat2: number,
  lon2: number,
): number {
  const p1 = toRad(lat1);
  const p2 = toRad(lat2);
  const dp = p2 - p1;
  const dl = toRad(lon2 - lon1);
  const a =
    Math.sin(dp / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2;
  return 2 * EARTH_RADIUS_M * Math.asin(Math.sqrt(a));
}

export function distanceToPlace(position: Coordinates, place: Place): number {
  return distanceM(position.latitude, position.longitude, place.lat, place.lon);
}

/** « 240 m », « 3,2 km », « 87 km » — jamais de décimale inutile. */
export function formatDistance(meters: number): string {
  if (!Number.isFinite(meters)) return '—';
  if (meters < 1000) return `${Math.round(meters / 10) * 10} m`;
  if (meters < 10_000) return `${(meters / 1000).toFixed(1).replace('.', ',')} km`;
  return `${Math.round(meters / 1000)} km`;
}

/**
 * Emprise carte englobant une position et un rayon, pour cadrer la vue.
 * `latitudeDelta` / `longitudeDelta` sont les unités attendues par react-native-maps.
 */
export function regionAround(
  latitude: number,
  longitude: number,
  radiusM: number,
) {
  const latitudeDelta = (radiusM * 2) / 111_320;
  const cos = Math.max(Math.cos(toRad(latitude)), 0.01);
  return {
    latitude,
    longitude,
    latitudeDelta,
    longitudeDelta: latitudeDelta / cos,
  };
}

/** Lieux dans un rayon donné, du plus proche au plus lointain. */
export function placesNear(
  places: Place[],
  position: Coordinates,
  radiusM: number,
): Array<{ place: Place; distanceM: number }> {
  return places
    .map((place) => ({ place, distanceM: distanceToPlace(position, place) }))
    .filter((entry) => entry.distanceM <= radiusM)
    .sort((a, b) => a.distanceM - b.distanceM);
}
