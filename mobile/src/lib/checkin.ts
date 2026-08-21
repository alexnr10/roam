import { distanceToPlace, formatDistance } from './geo';
import type { Coordinates, Place } from '../types';

/**
 * Règles de validation d'une visite.
 *
 * Le GPS est le mode par défaut : une seule tape, sur place. La photo reste
 * optionnelle et gratifiante — l'imposer transformerait le jeu en corvée.
 * Le mode déclaratif existe pour l'onboarding : sans lui, l'utilisateur démarre
 * à 0 % partout et décroche.
 */

/** Au-delà, la position du téléphone est trop imprécise pour trancher. */
export const MAX_ACCURACY_M = 100;

/** En deçà de `radius × ce facteur`, on affiche « tu y es presque ». */
export const APPROACH_FACTOR = 4;

export type CheckInStatus =
  | 'ready'          // sur place, validation possible
  | 'approaching'    // tout près, mais pas encore dans le rayon
  | 'far'            // trop loin
  | 'imprecise'      // dans le rayon, mais position trop imprécise pour valider
  | 'unknown';       // pas de position disponible

export type CheckInEvaluation = {
  status: CheckInStatus;
  canCheckIn: boolean;
  distanceM: number | null;
  /** Message prêt à afficher, à la deuxième personne. */
  message: string;
};

export function evaluateCheckIn(
  place: Place,
  position: Coordinates | null,
): CheckInEvaluation {
  if (!position) {
    return {
      status: 'unknown',
      canCheckIn: false,
      distanceM: null,
      message: 'Position indisponible',
    };
  }

  const distance = distanceToPlace(position, place);
  const accuracy = position.accuracy ?? 0;
  const inRadius = distance <= place.radiusM;

  if (inRadius && accuracy > MAX_ACCURACY_M) {
    return {
      status: 'imprecise',
      canCheckIn: false,
      distanceM: distance,
      // On ne valide pas sur une position floue : un faux positif abîme la
      // confiance dans la collection bien plus qu'une validation retardée.
      message: 'Signal GPS trop imprécis, attends quelques secondes',
    };
  }

  if (inRadius) {
    return {
      status: 'ready',
      canCheckIn: true,
      distanceM: distance,
      message: 'Tu y es — valide ta visite',
    };
  }

  if (distance <= place.radiusM * APPROACH_FACTOR) {
    return {
      status: 'approaching',
      canCheckIn: false,
      distanceM: distance,
      message: `Encore ${formatDistance(distance - place.radiusM)}`,
    };
  }

  return {
    status: 'far',
    canCheckIn: false,
    distanceM: distance,
    message: `À ${formatDistance(distance)} d'ici`,
  };
}

/**
 * Lieu à proposer spontanément à l'utilisateur : le plus proche parmi ceux
 * qu'il n'a pas encore validés et où il se trouve effectivement.
 *
 * C'est ce qui fait de la validation une récompense plutôt qu'une formalité :
 * l'app propose, l'utilisateur confirme.
 */
export function suggestCheckIn(
  places: Place[],
  position: Coordinates | null,
  visitedIds: ReadonlySet<string>,
): Place | null {
  if (!position) return null;

  let best: Place | null = null;
  let bestDistance = Infinity;

  for (const place of places) {
    if (visitedIds.has(place.id)) continue;
    const evaluation = evaluateCheckIn(place, position);
    if (evaluation.canCheckIn && (evaluation.distanceM ?? Infinity) < bestDistance) {
      best = place;
      bestDistance = evaluation.distanceM ?? Infinity;
    }
  }
  return best;
}
