import { useSyncExternalStore } from 'react';

import type { Coordinates } from '../types';

/**
 * Position simulée — mode démo uniquement.
 *
 * Sert à éprouver le moment de validation sans être physiquement sur place.
 * L'appel est réservé au build web (`Platform.OS === 'web'`) : sur téléphone,
 * seul le vrai GPS fait foi, sans quoi le jeu n'a plus de sens.
 */

let simulated: Coordinates | null = null;
const listeners = new Set<() => void>();

function emit() {
  for (const listener of listeners) listener();
}

export function setSimulatedPosition(position: Coordinates | null) {
  simulated = position;
  emit();
}

export function getSimulatedPosition(): Coordinates | null {
  return simulated;
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function useSimulatedPosition(): Coordinates | null {
  return useSyncExternalStore(subscribe, getSimulatedPosition, getSimulatedPosition);
}
