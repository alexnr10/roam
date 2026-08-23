import React, { useState } from 'react';
import { LayoutChangeEvent, Pressable, StyleSheet, Text, View } from 'react-native';

import { colors, radius, spacing, type } from '../theme';
import type { MapCanvasProps } from './MapCanvas';

/**
 * Carte du build web.
 *
 * `react-native-maps` ne fonctionne pas sur le web, et un fond de carte en
 * tuiles demanderait un service externe. On projette donc les lieux à plat sur
 * l'emprise de la France métropolitaine : c'est suffisant pour juger la
 * répartition, l'état visité / à visiter, et la boucle de validation — qui est
 * ce qu'on cherche à éprouver ici.
 */

// Emprise de la France métropolitaine.
const BOUNDS = { minLat: 41.3, maxLat: 51.2, minLon: -5.2, maxLon: 9.6 };

const toRad = (deg: number) => (deg * Math.PI) / 180;

/**
 * Projection plate à rapport d'aspect conservé.
 *
 * Un degré de longitude ne vaut pas un degré de latitude : au milieu de la
 * France, il vaut environ 0,69 fois moins en distance. Étirer l'emprise pour
 * remplir le cadre écrasait donc le pays du nord au sud. On calcule ici une
 * échelle unique, et on centre ce qui reste.
 */
function projector(width: number, height: number) {
  const midLat = (BOUNDS.minLat + BOUNDS.maxLat) / 2;
  const lonScale = Math.cos(toRad(midLat));

  const spanX = (BOUNDS.maxLon - BOUNDS.minLon) * lonScale;
  const spanY = BOUNDS.maxLat - BOUNDS.minLat;
  // Une seule échelle pour les deux axes : c'est elle qui garde les proportions.
  const scale = Math.min(width / spanX, height / spanY);
  const offsetX = (width - spanX * scale) / 2;
  const offsetY = (height - spanY * scale) / 2;

  return (lat: number, lon: number) => ({
    left: offsetX + (lon - BOUNDS.minLon) * lonScale * scale,
    // La latitude croît vers le nord, l'axe des ordonnées vers le bas.
    top: offsetY + (BOUNDS.maxLat - lat) * scale,
  });
}

export const mapAvailable = true;

export function MapCanvas({
  places,
  visitedIds,
  position,
  onSelectPlace,
  highlightedId,
}: MapCanvasProps) {
  const [size, setSize] = useState({ width: 0, height: 0 });

  const onLayout = (event: LayoutChangeEvent) => {
    const { width, height } = event.nativeEvent.layout;
    setSize({ width, height });
  };

  const ready = size.width > 0 && size.height > 0;
  const project = ready ? projector(size.width, size.height) : null;

  return (
    <View style={styles.canvas} onLayout={onLayout}>
      <View style={styles.grid} pointerEvents="none">
        {[0.25, 0.5, 0.75].map((ratio) => (
          <View key={`h${ratio}`} style={[styles.gridLine, { top: `${ratio * 100}%` }]} />
        ))}
        {[0.25, 0.5, 0.75].map((ratio) => (
          <View
            key={`v${ratio}`}
            style={[styles.gridLineVertical, { left: `${ratio * 100}%` }]}
          />
        ))}
      </View>

      {project
        ? places.map((place) => {
            const { left, top } = project(place.lat, place.lon);
            const visited = visitedIds.has(place.id);
            const highlighted = place.id === highlightedId;
            return (
              <Pressable
                key={place.id}
                onPress={() => onSelectPlace(place)}
                style={[styles.hit, { left: left - 13, top: top - 13 }]}
                accessibilityRole="button"
                accessibilityLabel={place.name}
              >
                <View
                  style={[
                    styles.dot,
                    visited ? styles.dotVisited : styles.dotTodo,
                    highlighted && styles.dotHighlighted,
                  ]}
                />
              </Pressable>
            );
          })
        : null}

      {project && position ? (
        (() => {
          const { left, top } = project(position.latitude, position.longitude);
          return <View style={[styles.me, { left: left - 7, top: top - 7 }]} />;
        })()
      ) : null}

      <View style={styles.legend} pointerEvents="none">
        <Text style={type.tiny}>● visité   ○ à visiter   ◆ moi</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  canvas: { flex: 1, backgroundColor: colors.surfaceAlt, overflow: 'hidden' },
  grid: { position: 'absolute', top: 0, left: 0, right: 0, bottom: 0 },
  gridLine: {
    position: 'absolute',
    left: 0,
    right: 0,
    height: StyleSheet.hairlineWidth,
    backgroundColor: colors.border,
  },
  gridLineVertical: {
    position: 'absolute',
    top: 0,
    bottom: 0,
    width: StyleSheet.hairlineWidth,
    backgroundColor: colors.border,
  },
  hit: {
    position: 'absolute',
    // La zone tactile reste large même si la pastille est fine.
    width: 26,
    height: 26,
    alignItems: 'center',
    justifyContent: 'center',
  },
  dot: { width: 8, height: 8, borderRadius: 4, borderWidth: 1.5, borderColor: '#FFFFFF' },
  dotVisited: { backgroundColor: colors.verified },
  dotTodo: { backgroundColor: colors.primary, opacity: 0.5 },
  dotHighlighted: { width: 18, height: 18, borderRadius: 9, opacity: 1 },
  me: {
    position: 'absolute',
    width: 14,
    height: 14,
    borderRadius: 7,
    backgroundColor: '#2563EB',
    borderWidth: 3,
    borderColor: '#FFFFFF',
  },
  legend: {
    position: 'absolute',
    left: spacing.sm,
    bottom: spacing.sm,
    backgroundColor: colors.surface,
    paddingHorizontal: spacing.sm,
    paddingVertical: 4,
    borderRadius: radius.sm,
  },
});
