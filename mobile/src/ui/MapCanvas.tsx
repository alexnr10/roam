import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { colors, radius, spacing, type } from '../theme';
import type { Coordinates, Place } from '../types';

/**
 * Carte.
 *
 * `react-native-maps` n'est pas disponible dans tous les environnements
 * d'exécution (Expo Go selon les versions, web). Plutôt que de planter au
 * démarrage, on charge le module de façon défensive et on retombe sur un
 * message explicite : le reste de l'app — listes, validation, progression —
 * continue de fonctionner.
 */
let Maps: typeof import('react-native-maps') | null = null;
try {
  Maps = require('react-native-maps');
} catch {
  Maps = null;
}

export const mapAvailable = Maps !== null;

export type MapCanvasProps = {
  places: Place[];
  visitedIds: ReadonlySet<string>;
  position: Coordinates | null;
  onSelectPlace: (place: Place) => void;
  /** Lieu à mettre en avant (celui qu'on propose de valider). */
  highlightedId?: string | null;
};

/** Vue par défaut : la France entière. */
const FRANCE_REGION = {
  latitude: 46.6,
  longitude: 2.4,
  latitudeDelta: 9.5,
  longitudeDelta: 9.5,
};

export function MapCanvas({
  places,
  visitedIds,
  position,
  onSelectPlace,
  highlightedId,
}: MapCanvasProps) {
  if (!Maps) {
    return (
      <View style={styles.fallback}>
        <Text style={type.subheading}>Carte indisponible ici</Text>
        <Text style={[type.small, styles.fallbackBody]}>
          Le module de carte natif n'est pas chargé dans cet environnement. La liste
          des lieux, la validation et la progression restent utilisables.
        </Text>
      </View>
    );
  }

  const MapView = Maps.default;
  const { Marker } = Maps;

  const initialRegion = position
    ? {
        latitude: position.latitude,
        longitude: position.longitude,
        latitudeDelta: 1.2,
        longitudeDelta: 1.2,
      }
    : FRANCE_REGION;

  return (
    <MapView
      style={StyleSheet.absoluteFill}
      initialRegion={initialRegion}
      showsUserLocation
      showsMyLocationButton
      toolbarEnabled={false}
    >
      {places.map((place) => {
        const visited = visitedIds.has(place.id);
        return (
          <Marker
            key={place.id}
            coordinate={{ latitude: place.lat, longitude: place.lon }}
            title={place.name}
            description={place.summary}
            onCalloutPress={() => onSelectPlace(place)}
            onPress={() => onSelectPlace(place)}
          >
            <View
              style={[
                styles.marker,
                visited ? styles.markerVisited : styles.markerTodo,
                place.id === highlightedId && styles.markerHighlighted,
              ]}
            />
          </Marker>
        );
      })}
    </MapView>
  );
}

const styles = StyleSheet.create({
  marker: {
    width: 16,
    height: 16,
    borderRadius: 8,
    borderWidth: 2.5,
    borderColor: '#FFFFFF',
  },
  // Visité : plein et vert. À visiter : creux et terracotta.
  markerVisited: { backgroundColor: colors.verified },
  markerTodo: { backgroundColor: colors.primary, opacity: 0.55 },
  markerHighlighted: { width: 24, height: 24, borderRadius: 12, opacity: 1 },
  fallback: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: spacing.xl,
    backgroundColor: colors.surfaceAlt,
    borderRadius: radius.lg,
  },
  fallbackBody: { textAlign: 'center', marginTop: spacing.sm },
});
