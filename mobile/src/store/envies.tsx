import AsyncStorage from '@react-native-async-storage/async-storage';
import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';

import { ajoutee, basculee, retiree, sansLesVisites } from '../lib/envies';
import { useVisits } from './visits';
import type { Envie } from '../types';

const STORAGE_KEY = 'roam.envies.v1';

/**
 * Les lieux qu'on s'est promis d'aller voir.
 *
 * Le carnet de visites dit d'où l'on vient ; celui-ci dit où l'on va. C'est la
 * moitié qui manquait à un guide : jusqu'ici l'app savait tout de ce qu'on
 * avait fait et rien de ce qu'on préparait.
 *
 * Volontairement absent de la CARTE. Une envie est une note qu'on se laisse à
 * soi-même, pas un état du territoire : la carte porte déjà trois couleurs de
 * note et un contour pour les lieux validés, et un quatrième signe la rendrait
 * illisible. La liste vit dans « Moi », là où l'on prépare.
 */
type EnviesContextValue = {
  envies: Envie[];
  /** Les identifiants seuls, pour tester l'appartenance sans parcourir. */
  envieIds: Set<string>;
  /** Faux tant que le stockage local n'a pas été relu. */
  ready: boolean;
  veutVoir: (placeId: string) => boolean;
  ajouter: (placeId: string) => void;
  retirer: (placeId: string) => void;
  /** Bascule, pour un bouton qui n'a qu'un état à changer. */
  basculer: (placeId: string) => void;
  reset: () => void;
};

const EnviesContext = createContext<EnviesContextValue | null>(null);

async function readStored(): Promise<string | null> {
  try {
    return await AsyncStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

export function EnviesProvider({ children }: { children: React.ReactNode }) {
  const [envies, setEnvies] = useState<Envie[]>([]);
  const [ready, setReady] = useState(false);
  const { visitedIds, ready: visitesPretes } = useVisits();

  useEffect(() => {
    let cancelled = false;
    // Même prudence que pour les visites : certains environnements font lever
    // l'accès au stockage de façon synchrone.
    readStored()
      .then((stored) => {
        if (cancelled || !stored) return;
        const parsed = JSON.parse(stored);
        if (Array.isArray(parsed)) setEnvies(parsed as Envie[]);
      })
      .catch(() => {
        // Un stockage illisible ne doit pas empêcher l'app de démarrer.
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
      AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(envies)).catch(() => {});
    } catch {
      // Stockage indisponible : la session reste utilisable, sans persistance.
    }
  }, [envies, ready]);

  /**
   * Une envie réalisée sort de la liste.
   *
   * Le nettoyage se fait ICI plutôt qu'au moment de la validation, et c'est ce
   * qui le rend fiable : un lieu se valide depuis la fiche, depuis le
   * quadrillage — qui en marque cinquante d'un geste — et depuis la roulette.
   * Accrocher le retrait à chacun de ces chemins, c'est en oublier un.
   *
   * On attend que les DEUX stockages soient relus : sans cette garde, la
   * première image du carnet de visites est vide, et la liste d'envies se
   * viderait de rien du tout.
   */
  useEffect(() => {
    if (!ready || !visitesPretes || visitedIds.size === 0) return;
    setEnvies((current) => sansLesVisites(current, visitedIds));
  }, [ready, visitesPretes, visitedIds]);

  const ajouter = useCallback((placeId: string) => {
    setEnvies((current) => ajoutee(current, placeId));
  }, []);

  const retirer = useCallback((placeId: string) => {
    setEnvies((current) => retiree(current, placeId));
  }, []);

  const basculer = useCallback((placeId: string) => {
    setEnvies((current) => basculee(current, placeId));
  }, []);

  const reset = useCallback(() => setEnvies([]), []);

  const value = useMemo<EnviesContextValue>(() => {
    const envieIds = new Set(envies.map((envie) => envie.placeId));
    return {
      envies,
      envieIds,
      ready,
      veutVoir: (placeId: string) => envieIds.has(placeId),
      ajouter,
      retirer,
      basculer,
      reset,
    };
  }, [envies, ready, ajouter, retirer, basculer, reset]);

  return <EnviesContext.Provider value={value}>{children}</EnviesContext.Provider>;
}

export function useEnvies(): EnviesContextValue {
  const context = useContext(EnviesContext);
  if (!context) throw new Error('useEnvies doit être utilisé dans <EnviesProvider>');
  return context;
}
