import { Tabs } from 'expo-router';
import React from 'react';
import { ColorValue } from 'react-native';

import { colors } from '../../src/theme';
import { IconeBoussole, IconeCarte, IconeJalon } from '../../src/ui/icons';

/**
 * Les trois onglets.
 *
 * Icônes dessinées plutôt qu'emoji : un emoji est rendu par le système, donc
 * jamais deux fois pareil — couleur, épaisseur, cadrage —, et la barre d'une
 * application de voyage y ressemblait à un clavier de messagerie.
 */
const icone = (Dessin: typeof IconeCarte) =>
  function TabIcon({ color }: { color: ColorValue }) {
    return <Dessin size={25} color={color as string} />;
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
        tabBarLabelStyle: { fontSize: 11 },
      }}
    >
      <Tabs.Screen
        name="index"
        options={{ title: 'Carte', tabBarIcon: icone(IconeCarte), headerShown: false }}
      />
      <Tabs.Screen
        name="collections"
        options={{ title: 'Explorer', tabBarIcon: icone(IconeBoussole) }}
      />
      {/* La conquête reste un écran, plus un onglet : c'est une récompense, et
          une récompense ne réclame pas le quart de la barre. On y entre depuis
          « Moi ». Trois onglets valent mieux que quatre — chacun devient plus
          large, donc plus facile à atteindre du pouce. */}
      <Tabs.Screen
        name="conquete"
        options={{ href: null, title: 'Conquête', headerShown: false }}
      />
      <Tabs.Screen
        name="profil"
        options={{ title: 'Moi', tabBarIcon: icone(IconeJalon) }}
      />
    </Tabs>
  );
}
