import * as Haptics from 'expo-haptics';
import React, { createContext, useCallback, useContext, useMemo, useState } from 'react';
import { Platform } from 'react-native';

import type { CheckInReward } from '../lib/progress';
import { CheckInCelebration } from '../ui/CheckInCelebration';
import type { Place } from '../types';

type Pending = { place: Place; reward: CheckInReward };

type CelebrationContextValue = {
  celebrate: (place: Place, reward: CheckInReward) => void;
};

const CelebrationContext = createContext<CelebrationContextValue | null>(null);

export function CelebrationProvider({ children }: { children: React.ReactNode }) {
  const [pending, setPending] = useState<Pending | null>(null);

  const celebrate = useCallback((place: Place, reward: CheckInReward) => {
    if (Platform.OS !== 'web') {
      // Le retour haptique fait la moitié du travail : on sent la validation
      // avant de la lire.
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
    }
    setPending({ place, reward });
  }, []);

  const value = useMemo(() => ({ celebrate }), [celebrate]);

  return (
    <CelebrationContext.Provider value={value}>
      {children}
      {pending ? (
        <CheckInCelebration
          place={pending.place}
          reward={pending.reward}
          onDismiss={() => setPending(null)}
        />
      ) : null}
    </CelebrationContext.Provider>
  );
}

export function useCelebration(): CelebrationContextValue {
  const context = useContext(CelebrationContext);
  if (!context) throw new Error('useCelebration doit être utilisé dans <CelebrationProvider>');
  return context;
}
