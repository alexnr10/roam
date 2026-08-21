import { useCallback } from 'react';

import { collections } from '../data/catalog';
import { useCelebration } from '../store/celebration';
import { useVisits } from '../store/visits';
import { describeCheckIn } from './progress';
import { makeVisit } from './visit';
import type { Place, VisitMethod } from '../types';

/**
 * Valider un lieu : enregistrer la visite ET célébrer ce qu'elle fait bouger.
 *
 * Les deux vont ensemble — une validation silencieuse ne récompense rien — donc
 * les écrans passent toujours par ici plutôt que d'appeler `addVisit` en direct.
 */
export function useCheckIn() {
  const { visits, addVisit } = useVisits();
  const { celebrate } = useCelebration();

  return useCallback(
    (place: Place, method: VisitMethod, distanceM?: number) => {
      // Un lieu ne compte qu'une fois : pas de seconde célébration.
      if (visits.some((visit) => visit.placeId === place.id)) return;

      const after = [...visits, makeVisit(place, method, distanceM)];
      const reward = describeCheckIn(collections, place, visits, after);

      addVisit(place, method, distanceM);
      celebrate(place, reward);
    },
    [visits, addVisit, celebrate],
  );
}
