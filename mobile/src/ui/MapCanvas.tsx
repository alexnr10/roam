import React, { useEffect, useMemo, useRef, useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { aDessiner, type Cadre } from '../lib/carte';
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
  /** Lieu à mettre en avant (celui qu'on propose de valider, ou le lieu choisi). */
  highlightedId?: string | null;
  /** Lieu sur lequel recentrer la carte, quand le choix vient d'ailleurs. */
  focus?: { lat: number; lon: number } | null;
  /**
   * La carte a été touchée AILLEURS que sur un point.
   *
   * Sans ce signal, la fiche ouverte par un point restait à l'écran sans
   * qu'aucun geste ne la referme : le bandeau des lieux voisins disparaissait
   * pour de bon, et il fallait changer d'onglet pour le retrouver.
   */
  onDeselect?: () => void;
  /**
   * La région ouverte a changé.
   *
   * Elle est dérivée du zoom autant que du clic : au-delà du seuil, c'est la
   * région qui remplit l'écran qui s'ouvre. L'écran s'en sert pour titrer le
   * bandeau et montrer la pastille de retour.
   */
  onRegionChange?: (code: string | null) => void;
  /**
   * Le centre de la vue, après chaque déplacement.
   *
   * C'est par là que le catalogue change de pays sans qu'on le demande : la
   * carte ne sait rien des pays, elle dit seulement où l'on regarde, et le
   * magasin en tire ce qu'il faut charger.
   */
  onCentre?: (lon: number, lat: number) => void;
  /**
   * Demande de retour à la France entière.
   *
   * Un compteur plutôt qu'un booléen : chaque incrément est UN retour demandé,
   * et deux retours d'affilée se distinguent. Dézoomer referme aussi, mais un
   * chemin qu'on voit vaut mieux qu'un geste qu'il faut deviner.
   */
  retour?: number;
  /**
   * Une région à ouvrir, demandée depuis un autre écran.
   *
   * De la forme `code#nonce` : le nonce distingue deux demandes portant sur la
   * même région, sans quoi rouvrir la Bretagne après l'avoir refermée ne
   * changerait rien.
   */
  ouvrir?: string | null;
};

/**
 * Combien de marqueurs au maximum, sur mobile natif.
 *
 * Chaque marqueur y est un composant React : deux mille pour vingt visibles,
 * c'est la carte qui rame. Le plafond ne touche QUE le dessin — la recherche
 * continue de voir tout le catalogue.
 */
const PLAFOND_NATIF = 120;

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
  focus,
  onDeselect,
  onCentre,
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
    <NativeMap
      MapView={MapView}
      Marker={Marker}
      initialRegion={initialRegion}
      places={places}
      visitedIds={visitedIds}
      onSelectPlace={onSelectPlace}
      highlightedId={highlightedId}
      focus={focus}
      onDeselect={onDeselect}
      onCentre={onCentre}
    />
  );
}

/**
 * La carte native, une fois le module chargé.
 *
 * Séparée parce qu'elle tient un état — le cadre visible — et qu'un composant
 * ne peut pas appeler `useState` après un `return` conditionnel.
 */
function NativeMap({
  MapView,
  Marker,
  initialRegion,
  places,
  visitedIds,
  onSelectPlace,
  highlightedId,
  focus,
  onDeselect,
  onCentre,
}: {
  MapView: typeof import('react-native-maps').default;
  Marker: typeof import('react-native-maps').Marker;
  initialRegion: typeof FRANCE_REGION;
  places: Place[];
  visitedIds: ReadonlySet<string>;
  onSelectPlace: (place: Place) => void;
  highlightedId?: string | null;
  focus?: { lat: number; lon: number } | null;
  onDeselect?: () => void;
  onCentre?: (lon: number, lat: number) => void;
}) {
  const [cadre, setCadre] = useState<Cadre | null>(null);
  const vue = useRef<import('react-native-maps').default | null>(null);
  const dessines = useMemo(
    () => aDessiner(places, cadre, PLAFOND_NATIF),
    [places, cadre],
  );

  // Recentrage IMPÉRATIF, et sur les coordonnées plutôt que sur l'objet.
  // Passer `region` en propriété la rendrait contrôlée : la carte reviendrait à
  // sa place à chaque rendu, et on ne pourrait plus la déplacer du doigt.
  const focusLat = focus?.lat ?? null;
  const focusLon = focus?.lon ?? null;
  useEffect(() => {
    if (focusLat === null || focusLon === null) return;
    vue.current?.animateToRegion(
      {
        latitude: focusLat,
        longitude: focusLon,
        latitudeDelta: 0.08,
        longitudeDelta: 0.08,
      },
      600,
    );
  }, [focusLat, focusLon]);

  return (
    <MapView
      ref={vue}
      style={StyleSheet.absoluteFill}
      initialRegion={initialRegion}
      showsUserLocation
      showsMyLocationButton
      toolbarEnabled={false}
      // `onPress` de la carte ne se déclenche PAS sur un marqueur : toucher le
      // fond veut donc dire « je regarde autre chose ».
      onPress={() => onDeselect?.()}
      onRegionChangeComplete={(vue: {
        latitude: number;
        longitude: number;
        latitudeDelta: number;
        longitudeDelta: number;
      }) => {
        // Même question que sur le web, au même moment : où regarde-t-on ?
        onCentre?.(vue.longitude, vue.latitude);
        setCadre({
          sud: vue.latitude - vue.latitudeDelta / 2,
          nord: vue.latitude + vue.latitudeDelta / 2,
          ouest: vue.longitude - vue.longitudeDelta / 2,
          est: vue.longitude + vue.longitudeDelta / 2,
        });
      }}
    >
      {dessines.map((place) => {
        const visited = visitedIds.has(place.id);
        return (
          <Marker
            key={place.id}
            coordinate={{ latitude: place.lat, longitude: place.lon }}
            title={place.name}
            description={place.summary ?? undefined}
            onCalloutPress={() => onSelectPlace(place)}
            onPress={() => onSelectPlace(place)}
          >
            {/* La pastille fait seize points, la zone tactile quarante-quatre :
                un point de carte se rate autrement une fois sur deux, et c'est
                le geste le plus fréquent de l'application. */}
            <View style={styles.hit}>
              <View
                style={[
                  styles.marker,
                  visited ? styles.markerVisited : styles.markerTodo,
                  place.id === highlightedId && styles.markerHighlighted,
                ]}
              />
            </View>
          </Marker>
        );
      })}
    </MapView>
  );
}

const styles = StyleSheet.create({
  hit: { width: 44, height: 44, alignItems: 'center', justifyContent: 'center' },
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
