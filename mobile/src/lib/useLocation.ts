import * as Location from 'expo-location';
import { useEffect, useRef, useState } from 'react';

import type { Coordinates } from '../types';

export type LocationState = {
  position: Coordinates | null;
  /** null tant que l'utilisateur n'a pas répondu à la demande d'autorisation. */
  granted: boolean | null;
  error: string | null;
};

/**
 * Position de l'appareil, suivie en continu.
 *
 * Le suivi est volontairement peu gourmand : la validation se joue à la
 * centaine de mètres, pas au mètre, et la batterie compte quand on marche
 * toute une journée.
 */
export function useLocation(active = true): LocationState {
  const [state, setState] = useState<LocationState>({
    position: null,
    granted: null,
    error: null,
  });
  const subscription = useRef<Location.LocationSubscription | null>(null);

  useEffect(() => {
    if (!active) return;
    let cancelled = false;

    (async () => {
      try {
        const { status } = await Location.requestForegroundPermissionsAsync();
        if (cancelled) return;

        if (status !== 'granted') {
          setState({ position: null, granted: false, error: null });
          return;
        }
        setState((current) => ({ ...current, granted: true }));

        subscription.current = await Location.watchPositionAsync(
          {
            accuracy: Location.Accuracy.Balanced,
            timeInterval: 5000,
            distanceInterval: 20,
          },
          (reading) => {
            if (cancelled) return;
            setState({
              position: {
                latitude: reading.coords.latitude,
                longitude: reading.coords.longitude,
                accuracy: reading.coords.accuracy,
              },
              granted: true,
              error: null,
            });
          },
        );
      } catch (error) {
        if (cancelled) return;
        setState({
          position: null,
          granted: null,
          error: error instanceof Error ? error.message : 'Localisation indisponible',
        });
      }
    })();

    return () => {
      cancelled = true;
      subscription.current?.remove();
      subscription.current = null;
    };
  }, [active]);

  return state;
}
