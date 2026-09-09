import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import React from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { CelebrationProvider } from '../src/store/celebration';
import { EnviesProvider } from '../src/store/envies';
import { PaysProvider, usePays } from '../src/store/pays';
import { VisitsProvider } from '../src/store/visits';
import { colors } from '../src/theme';

export default function RootLayout() {
  return (
    <SafeAreaProvider>
      {/* AVANT tout le reste : le catalogue que les autres magasins lisent
          dépend du pays choisi. */}
      <PaysProvider>
      <VisitsProvider>
        {/* Dans VisitsProvider, et pas à côté : la liste d'envies lit les
            visites pour retirer d'elle-même un lieu qu'on vient de valider. */}
        <EnviesProvider>
        <CelebrationProvider>
        <StatusBar style="dark" />
        <Navigation />
        </CelebrationProvider>
        </EnviesProvider>
      </VisitsProvider>
      </PaysProvider>
    </SafeAreaProvider>
  );
}

/**
 * La navigation, REMONTÉE à chaque changement de pays.
 *
 * Le catalogue est un module : le remplacer change ce que `places` et
 * `collections` valent, mais aucun écran ne le sait — React ne redessine que
 * ce dont l'état a bougé, et l'état n'a pas bougé.
 *
 * Une clé sur la pile règle cela d'un mot, et c'est aussi la bonne SÉMANTIQUE :
 * changer de pays n'est pas un rafraîchissement, c'est un changement de sujet.
 * Rester sur la fiche du Colisée en affichant la France serait faux ; la pile
 * repart de la carte, du bon pays.
 *
 * La clé est posée ICI, sous les magasins : visites, envies et catalogue leur
 * survivent. Un carnet de visites rechargé depuis le stockage à chaque bascule
 * clignoterait à vide.
 */
function Navigation() {
  const { pays } = usePays();
  return (
    <React.Fragment key={pays}>
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
          <Stack.Screen name="reconnaitre" options={{ headerShown: false }} />
      </Stack>
    </React.Fragment>
  );
}
