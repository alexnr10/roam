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

const project = (
  lat: number,
  lon: number,
  width: number,
  height: number,
): { left: number; top: number } => ({
  left: ((lon - BOUNDS.minLon) / (BOUNDS.maxLon - BOUNDS.minLon)) * width,
  // La latitude croît vers le nord, l'axe des ordonnées vers le bas.
  top: ((BOUNDS.maxLat - lat) / (BOUNDS.maxLat - BOUNDS.minLat)) * height,
});

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

      {ready
        ? places.map((place) => {
            const { left, top } = project(place.lat, place.lon, size.width, size.height);
            const visited = visitedIds.has(place.id);
            const highlighted = place.id === highlightedId;
            return (
              <Pressable
                key={place.id}
                onPress={() => onSelectPlace(place)}
                style={[styles.hit, { left: left - 14, top: top - 14 }]}
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

      {ready && position ? (
        (() => {
          const { left, top } = project(
            position.latitude,
            position.longitude,
            size.width,
            size.height,
          );
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
    width: 28,
    height: 28,
    alignItems: 'center',
    justifyContent: 'center',
  },
  dot: { width: 12, height: 12, borderRadius: 6, borderWidth: 2, borderColor: '#FFFFFF' },
  dotVisited: { backgroundColor: colors.verified },
  dotTodo: { backgroundColor: colors.primary, opacity: 0.5 },
  dotHighlighted: { width: 20, height: 20, borderRadius: 10, opacity: 1 },
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
