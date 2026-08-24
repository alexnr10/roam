import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { colors, radius, spacing, type } from '../theme';
import type { ZoneConquest } from '../lib/conquest';
import type { AreaLevel } from '../types';

/**
 * Carte de conquête coloriée.
 *
 * Colorier des polygones administratifs — une carte choroplèthe — demande un
 * moteur qui sache styler une géométrie par la donnée. `react-native-maps` ne
 * le fait pas : il dessine des polygones, mais recolorier cent un départements
 * lui coûte un redessin complet, et quelques milliers de communes le mettront
 * à genoux. MapLibre est fait pour ça.
 *
 * D'ici la bascule complète, le natif n'a pas de carte de conquête et le dit.
 * La liste, elle, fonctionne partout — et elle dit ce qu'il RESTE à faire, là
 * où un aplat de couleur ne dit que ce qui est fait.
 */

export type ConquestMapProps = {
  zones: ZoneConquest[];
  level: AreaLevel;
  selectedCode: string | null;
  onSelectZone: (code: string | null) => void;
};

export const conquestMapAvailable = false;

/**
 * Aucune échelle n'a de contours ici — et c'est délibéré : le module natif
 * n'importe pas `outlines.json`, qui pèse un demi-mégaoctet pour une carte
 * qu'il ne sait pas dessiner.
 */
export const conquestOutlinesExist = (_level: AreaLevel): boolean => false;

export function ConquestMap(_props: ConquestMapProps) {
  return (
    <View style={styles.fallback}>
      <Text style={type.subheading}>Carte de conquête indisponible ici</Text>
      <Text style={[type.small, styles.body]}>
        Le coloriage des territoires demande MapLibre, que la version native n'embarque
        pas encore. La liste ci-dessous dit exactement la même chose.
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  fallback: {
    alignItems: 'center',
    justifyContent: 'center',
    padding: spacing.xl,
    backgroundColor: colors.surfaceAlt,
    borderRadius: radius.lg,
  },
  body: { textAlign: 'center', marginTop: spacing.sm },
});
