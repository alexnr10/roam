import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import React from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { VisitsProvider } from '../src/store/visits';
import { colors } from '../src/theme';

export default function RootLayout() {
  return (
    <SafeAreaProvider>
      <VisitsProvider>
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
          <Stack.Screen name="place/[id]" options={{ title: '' }} />
          <Stack.Screen name="collection/[slug]" options={{ title: '' }} />
        </Stack>
      </VisitsProvider>
    </SafeAreaProvider>
  );
}
