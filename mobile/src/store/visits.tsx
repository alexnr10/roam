import AsyncStorage from '@react-native-async-storage/async-storage';
import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';

import { makeVisit } from '../lib/visit';
import type { Place, Visit, VisitMethod } from '../types';

const STORAGE_KEY = 'roam.visits.v1';

type VisitsContextValue = {
  visits: Visit[];
  visitedIds: Set<string>;
  /** Faux tant que le stockage local n'a pas été relu. */
  ready: boolean;
  hasVisited: (placeId: string) => boolean;
  addVisit: (place: Place, method: VisitMethod, distanceM?: number) => void;
  /**
   * Enregistre un LOT de visites en une fois.
   *
   * Le quadrillage en marque cinquante d'un geste. Les ajouter une à une
   * ferait cinquante rendus et cinquante écritures dans le stockage, pour un
   * seul geste de l'utilisateur.
   */
  addVisits: (places: Place[], method: VisitMethod) => void;
  removeVisit: (placeId: string) => void;
  removeVisits: (placeIds: string[]) => void;
  reset: () => void;
};

const VisitsContext = createContext<VisitsContextValue | null>(null);

async function readStored(): Promise<string | null> {
  try {
    return await AsyncStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

export function VisitsProvider({ children }: { children: React.ReactNode }) {
  const [visits, setVisits] = useState<Visit[]>([]);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let cancelled = false;
    // Certains environnements (iframe restreinte, navigation privée) font lever
    // l'accès au stockage de façon synchrone : `Promise.resolve().then` seul ne
    // suffirait pas à l'attraper.
    readStored()
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
    try {
      AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(visits)).catch(() => {});
    } catch {
      // Stockage indisponible : la session reste utilisable, sans persistance.
    }
  }, [visits, ready]);

  const addVisit = useCallback(
    (place: Place, method: VisitMethod, distanceM?: number) => {
      setVisits((current) => {
        // Un lieu ne compte qu'une fois ; revenir sur place ne double pas le score.
        if (current.some((visit) => visit.placeId === place.id)) return current;
        return [...current, makeVisit(place, method, distanceM)];
      });
    },
    [],
  );

  const addVisits = useCallback((lot: Place[], method: VisitMethod) => {
    setVisits((current) => {
      const connus = new Set(current.map((visit) => visit.placeId));
      const nouveaux = lot
        .filter((place) => !connus.has(place.id))
        .map((place) => makeVisit(place, method));
      return nouveaux.length ? [...current, ...nouveaux] : current;
    });
  }, []);

  const removeVisit = useCallback((placeId: string) => {
    setVisits((current) => current.filter((visit) => visit.placeId !== placeId));
  }, []);

  const removeVisits = useCallback((placeIds: string[]) => {
    const partants = new Set(placeIds);
    setVisits((current) => current.filter((visit) => !partants.has(visit.placeId)));
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
      addVisits,
      removeVisit,
      removeVisits,
      reset,
    };
  }, [visits, ready, addVisit, addVisits, removeVisit, removeVisits, reset]);

  return <VisitsContext.Provider value={value}>{children}</VisitsContext.Provider>;
}

export function useVisits(): VisitsContextValue {
  const context = useContext(VisitsContext);
  if (!context) throw new Error('useVisits doit être utilisé dans <VisitsProvider>');
  return context;
}
