import AsyncStorage from '@react-native-async-storage/async-storage';
import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';

import type { Place, Visit, VisitMethod } from '../types';

const STORAGE_KEY = 'roam.visits.v1';

type VisitsContextValue = {
  visits: Visit[];
  visitedIds: Set<string>;
  /** Faux tant que le stockage local n'a pas été relu. */
  ready: boolean;
  hasVisited: (placeId: string) => boolean;
  addVisit: (place: Place, method: VisitMethod, distanceM?: number) => void;
  removeVisit: (placeId: string) => void;
  reset: () => void;
};

const VisitsContext = createContext<VisitsContextValue | null>(null);

export function VisitsProvider({ children }: { children: React.ReactNode }) {
  const [visits, setVisits] = useState<Visit[]>([]);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let cancelled = false;
    AsyncStorage.getItem(STORAGE_KEY)
      .then((stored) => {
        if (cancelled || !stored) return;
        const parsed = JSON.parse(stored);
        if (Array.isArray(parsed)) setVisits(parsed as Visit[]);
      })
      .catch(() => {
        // Un stockage illisible ne doit pas empêcher l'app de démarrer :
        // on repart d'un carnet vide plutôt que d'afficher une erreur.
      })
      .finally(() => {
        if (!cancelled) setReady(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!ready) return;
    AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(visits)).catch(() => {});
  }, [visits, ready]);

  const addVisit = useCallback(
    (place: Place, method: VisitMethod, distanceM?: number) => {
      setVisits((current) => {
        // Un lieu ne compte qu'une fois ; revenir sur place ne double pas le score.
        if (current.some((visit) => visit.placeId === place.id)) return current;
        return [
          ...current,
          {
            placeId: place.id,
            method,
            verified: method === 'gps',
            visitedAt: new Date().toISOString(),
            distanceM,
          },
        ];
      });
    },
    [],
  );

  const removeVisit = useCallback((placeId: string) => {
    setVisits((current) => current.filter((visit) => visit.placeId !== placeId));
  }, []);

  const reset = useCallback(() => setVisits([]), []);

  const value = useMemo<VisitsContextValue>(() => {
    const visitedIds = new Set(visits.map((visit) => visit.placeId));
    return {
      visits,
      visitedIds,
      ready,
      hasVisited: (placeId: string) => visitedIds.has(placeId),
      addVisit,
      removeVisit,
      reset,
    };
  }, [visits, ready, addVisit, removeVisit, reset]);

  return <VisitsContext.Provider value={value}>{children}</VisitsContext.Provider>;
}

export function useVisits(): VisitsContextValue {
  const context = useContext(VisitsContext);
  if (!context) throw new Error('useVisits doit être utilisé dans <VisitsProvider>');
  return context;
}
