import type { CollectionProgress } from './progress';
import type { Collection, Coordinates, Place } from '../types';

/**
 * Dans quel ordre présenter deux cent quatre-vingts collections.
 *
 * Le tri par progression décroissante ne trie RIEN tant qu'aucun lieu n'est
 * collecté : tout vaut 0 %, et l'ordre des cartes est celui du fichier. Le
 * nouvel arrivant voyait donc 253 collections géographiques sans le moindre
 * principe d'organisation, et c'est ce qui rendait la liste interminable.
 *
 * Trois questions, dans cet ordre, et une seule section par question :
 *
 * 1. « Qu'est-ce que je peux finir ? » — une collection à laquelle il ne
 *    manque qu'un ou deux lieux se termine, où qu'elle soit. La distance
 *    n'entre pas dans ce calcul : c'est même tout l'intérêt, ces collections
 *    sont ce qui donne envie de traverser le pays.
 * 2. « Qu'est-ce que je fais ce week-end ? » — la proximité, et elle seule.
 * 3. « Où pourrais-je aller ? » — le reste, thèmes nationaux d'abord parce
 *    qu'ils portent le voyage lointain, puis la géographie par distance.
 */

const EARTH_RADIUS_M = 6_371_000;

export function haversineM(a: Coordinates, b: Coordinates): number {
  const p1 = (a.latitude * Math.PI) / 180;
  const p2 = (b.latitude * Math.PI) / 180;
  const dp = p2 - p1;
  const dl = ((b.longitude - a.longitude) * Math.PI) / 180;
  const h =
    Math.sin(dp / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2;
  return 2 * EARTH_RADIUS_M * Math.asin(Math.sqrt(h));
}

/**
 * Distance au lieu le PLUS PROCHE de la collection, pas à son centre.
 *
 * Le centre d'une collection nationale tombe au milieu de la France et n'a
 * aucun sens pour personne. Ce qui compte est : « le premier lieu de cette
 * collection, il est à combien ? »
 */
export function nearestPlaceM(
  places: Pick<Place, 'lat' | 'lon'>[],
  from: Coordinates,
): number | null {
  let best: number | null = null;
  for (const place of places) {
    const d = haversineM(from, { latitude: place.lat, longitude: place.lon });
    if (best === null || d < best) best = d;
  }
  return best;
}

export type Ranked = {
  collection: Collection;
  progress: CollectionProgress;
  /** null quand la position est inconnue ou la collection vide. */
  distanceM: number | null;
  remaining: number;
};

/** Il ne manque qu'un ou deux lieux : c'est à portée de main. */
export const ALMOST_DONE_REMAINING = 2;
/** Au-delà, « près de toi » ne veut plus rien dire. */
export const NEARBY_RADIUS_M = 150_000;

export type Shortlists = {
  almostDone: Ranked[];
  nearby: Ranked[];
  rest: Ranked[];
};

export function rank(
  collections: Collection[],
  progressOf: (collection: Collection) => CollectionProgress,
  placesOf: (collection: Collection) => Pick<Place, 'lat' | 'lon'>[],
  position: Coordinates | null,
): Ranked[] {
  return collections.map((collection) => {
    const progress = progressOf(collection);
    return {
      collection,
      progress,
      distanceM: position ? nearestPlaceM(placesOf(collection), position) : null,
      remaining: Math.max(0, progress.total - progress.visited),
    };
  });
}

const byDistance = (a: Ranked, b: Ranked) =>
  (a.distanceM ?? Infinity) - (b.distanceM ?? Infinity);

export function shortlists(ranked: Ranked[], limit = 5): Shortlists {
  // Commencée ET presque finie. Sans la première condition, toute collection
  // de deux lieux serait « presque finie » avant qu'on ait rien fait.
  const almostDone = ranked
    .filter((r) => r.progress.visited > 0 && !r.progress.complete
      && r.remaining <= ALMOST_DONE_REMAINING)
    .sort((a, b) => a.remaining - b.remaining || byDistance(a, b));

  const retenus = new Set(almostDone.map((r) => r.collection.slug));
  const nearby = ranked
    .filter((r) => !retenus.has(r.collection.slug)
      && !r.progress.complete
      && r.distanceM !== null && r.distanceM <= NEARBY_RADIUS_M)
    .sort(byDistance)
    .slice(0, limit);

  for (const r of nearby) retenus.add(r.collection.slug);
  const rest = ranked.filter((r) => !retenus.has(r.collection.slug));
  return { almostDone, nearby, rest };
}

/**
 * L'ordre du reste : la progression d'abord — elle reprend la main dès la
 * première visite — puis la distance, qui la remplace tant que tout vaut 0 %.
 */
export function byProgressThenDistance(a: Ranked, b: Ranked): number {
  return b.progress.pct - a.progress.pct || byDistance(a, b);
}

export function formatDistance(metres: number | null): string | null {
  if (metres === null) return null;
  if (metres < 1000) return `${Math.round(metres / 100) * 100} m`;
  if (metres < 100_000) return `${Math.round(metres / 1000)} km`;
  return `${Math.round(metres / 10_000) * 10} km`;
}
