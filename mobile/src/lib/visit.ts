import type { Place, Visit, VisitMethod } from '../types';

/**
 * Construit l'enregistrement d'une visite.
 *
 * Partagé entre le carnet et le calcul de récompense, pour que la projection
 * « après validation » soit exactement ce qui sera enregistré.
 */
export function makeVisit(
  place: Place,
  method: VisitMethod,
  distanceM?: number,
): Visit {
  return {
    placeId: place.id,
    method,
    // Seule une validation GPS sur place vaut « vérifiée ».
    verified: method === 'gps',
    visitedAt: new Date().toISOString(),
    distanceM,
  };
}
