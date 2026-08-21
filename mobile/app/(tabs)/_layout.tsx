import { Tabs } from 'expo-router';
import React from 'react';
import { ColorValue, Text } from 'react-native';

import { colors } from '../../src/theme';

const icon = (glyph: string) =>
  function TabIcon({ color }: { color: ColorValue }) {
    return <Text style={{ fontSize: 20, color: color as string }}>{glyph}</Text>;
  };

export default function TabsLayout() {
  return (
    <Tabs
      screenOptions={{
        tabBarActiveTintColor: colors.primary,
        tabBarInactiveTintColor: colors.muted,
        headerStyle: { backgroundColor: colors.bg },
        headerTitleStyle: { color: colors.text },
        sceneStyle: { backgroundColor: colors.bg },
        tabBarStyle: { backgroundColor: colors.surface, borderTopColor: colors.border },
      }}
    >
      <Tabs.Screen
        name="index"
        options={{ title: 'Carte', tabBarIcon: icon('🗺️'), headerShown: false }}
      />
      <Tabs.Screen
        name="collections"
        options={{ title: 'Collections', tabBarIcon: icon('🎯') }}
      />
      <Tabs.Screen name="profil" options={{ title: 'Profil', tabBarIcon: icon('🎖️') }} />
    </Tabs>
  );
}
