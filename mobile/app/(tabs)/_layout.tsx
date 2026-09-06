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
        options={{ title: 'Explorer', tabBarIcon: icon('🧭') }}
      />
      {/* La conquête reste un écran, plus un onglet : c'est une récompense, et
          une récompense ne réclame pas le quart de la barre. On y entre depuis
          « Moi ». Trois onglets valent mieux que quatre — chacun devient plus
          large, donc plus facile à atteindre du pouce. */}
      <Tabs.Screen
        name="conquete"
        options={{ href: null, title: 'Conquête', headerShown: false }}
      />
      <Tabs.Screen name="profil" options={{ title: 'Moi', tabBarIcon: icon('🎖️') }} />
    </Tabs>
  );
}
