import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import React from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { CelebrationProvider } from '../src/store/celebration';
import { VisitsProvider } from '../src/store/visits';
import { colors } from '../src/theme';

export default function RootLayout() {
  return (
    <SafeAreaProvider>
      <VisitsProvider>
        <CelebrationProvider>
        <StatusBar style="dark" />
        <Stack
          screenOptions={{
            headerStyle: { backgroundColor: colors.bg },
            headerTitleStyle: { color: colors.text },
            headerTintColor: colors.primary,
            contentStyle: { backgroundColor: colors.bg },
          }}
        >
          <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
          {/* Pas d'en-tête de pile : son bouton retour dépend de l'historique
              du navigateur, que la page repliée en un seul fichier fige. Les
              écrans portent leur propre `BackBar`, qui marche partout. */}
          <Stack.Screen name="place/[id]" options={{ headerShown: false }} />
          <Stack.Screen name="collection/[slug]" options={{ headerShown: false }} />
        </Stack>
        </CelebrationProvider>
      </VisitsProvider>
    </SafeAreaProvider>
  );
}
