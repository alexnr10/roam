// La feuille de style de MapLibre porte les contrôles et la mention
// d'attribution d'OpenStreetMap, qui est une obligation de la licence ODbL.
import 'maplibre-gl/dist/maplibre-gl.css';
import * as maplibregl from 'maplibre-gl';
import type { GeoJSONSource, MapLayerMouseEvent, Map as MapLibreMap } from 'maplibre-gl';
import React, { useEffect, useRef, useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { colors, spacing, type } from '../theme';
import type { Place } from '../types';
import type { MapCanvasProps } from './MapCanvas';
import {
  CLUSTER_MAX_ZOOM,
  CLUSTER_RADIUS,
  FRANCE_BOUNDS,
  mapColors,
  resolveBasemap,
} from './mapStyle';
import { prepareMapLibre } from './maplibreSetup';

/**
 * Carte du build web, sur MapLibre.
 *
 * Les lieux ne sont pas des marqueurs HTML mais une source GeoJSON dessinée par
 * le moteur : à mille six cents points, un nœud du DOM par lieu rendrait le
 * défilement poussif, là où le rendu vectoriel reste fluide et permet le
 * regroupement au dézoom.
 */

export const mapAvailable = true;

const SOURCE = 'places';

function toFeatureCollection(
  places: Place[],
  visitedIds: ReadonlySet<string>,
): GeoJSON.FeatureCollection<GeoJSON.Point> {
  return {
    type: 'FeatureCollection',
    features: places.map((place) => ({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [place.lon, place.lat] },
      properties: {
        id: place.id,
        name: place.name,
        visited: visitedIds.has(place.id) ? 1 : 0,
      },
    })),
  };
}

export function MapCanvas({
  places,
  visitedIds,
  position,
  onSelectPlace,
  highlightedId,
}: MapCanvasProps) {
  const container = useRef<HTMLDivElement | null>(null);
  const map = useRef<MapLibreMap | null>(null);
  const marker = useRef<maplibregl.Marker | null>(null);
  // Gardé dans une référence : le gestionnaire de clic est posé une seule fois,
  // mais doit toujours voir la liste courante.
  const byId = useRef(new Map<string, Place>());
  const onSelect = useRef(onSelectPlace);

  byId.current = new Map(places.map((place) => [place.id, place]));
  onSelect.current = onSelectPlace;

  const [degraded, setDegraded] = useState(false);
  // WebGL2 manque encore sur quelques WebViews Android et sur les machines
  // sans accélération : MapLibre lève à la construction, et sans ce garde-fou
  // l'écran restait un rectangle gris sans un mot d'explication.
  const [failed, setFailed] = useState(false);
  // Les couches ne peuvent être alimentées qu'une fois le style chargé. Sans cet
  // état, les effets de données s'exécutaient avant que la carte n'existe et ne
  // repassaient jamais : la carte restait vide.
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!container.current || map.current) return;
    let cancelled = false;
    let created: MapLibreMap | null = null;

    prepareMapLibre();

    (async () => {
      const { style, degraded: noBasemap } = await resolveBasemap();
      if (cancelled || !container.current) return;
      setDegraded(noBasemap);

      let instance: MapLibreMap;
      try {
        instance = new maplibregl.Map({
          container: container.current,
          style: style as maplibregl.StyleSpecification,
          bounds: FRANCE_BOUNDS,
          fitBoundsOptions: { padding: 12 },
          attributionControl: { compact: true },
        });
      } catch (error) {
        // WebGL2 absent : MapLibre lève ici même. Sans ce filet, l'exception
        // partait dans une promesse orpheline et l'écran restait gris, muet.
        console.warn('Roam : carte indisponible', error);
        setFailed(true);
        return;
      }
      map.current = instance;
    created = instance;
    instance.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');

    instance.on('load', () => {
      instance.addSource(SOURCE, {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] },
        cluster: true,
        clusterRadius: CLUSTER_RADIUS,
        clusterMaxZoom: CLUSTER_MAX_ZOOM,
      });

      // Paquets : la taille dit le nombre, sans jamais devenir envahissante.
      instance.addLayer({
        id: 'clusters',
        type: 'circle',
        source: SOURCE,
        filter: ['has', 'point_count'],
        paint: {
          'circle-color': mapColors.cluster,
          'circle-opacity': 0.9,
          // La taille dépend du nombre ET du zoom : des pastilles calibrées
          // pour un département deviennent envahissantes à l'échelle du pays.
          'circle-radius': [
            'interpolate',
            ['linear'],
            ['zoom'],
            4,
            ['step', ['get', 'point_count'], 9, 10, 12, 50, 16],
            9,
            ['step', ['get', 'point_count'], 15, 10, 20, 50, 26],
          ],
          'circle-stroke-width': 2,
          'circle-stroke-color': mapColors.halo,
        },
      });
      // Une couche de texte exige que le style fournisse des polices ; sans
      // elles, MapLibre tente de construire une URL vide et échoue. Le nombre
      // est alors omis — la taille du cercle dit déjà l'ordre de grandeur.
      if (instance.getStyle()?.glyphs) {
        instance.addLayer({
          id: 'cluster-count',
          type: 'symbol',
          source: SOURCE,
          filter: ['has', 'point_count'],
          layout: {
            'text-field': ['get', 'point_count_abbreviated'],
            'text-font': ['Noto Sans Bold'],
            'text-size': 12,
            'text-allow-overlap': true,
          },
          paint: { 'text-color': mapColors.clusterText },
        });
      }

      // Lieux : plein et vert quand c'est validé, creux et terracotta sinon.
      instance.addLayer({
        id: 'place',
        type: 'circle',
        source: SOURCE,
        filter: ['!', ['has', 'point_count']],
        paint: {
          'circle-color': [
            'case',
            ['==', ['get', 'visited'], 1],
            mapColors.visited,
            mapColors.todo,
          ],
          'circle-opacity': ['case', ['==', ['get', 'visited'], 1], 1, 0.65],
          'circle-radius': ['interpolate', ['linear'], ['zoom'], 5, 4, 10, 7, 14, 10],
          'circle-stroke-width': 1.5,
          'circle-stroke-color': mapColors.halo,
        },
      });

      // Le lieu proposé à la validation, par-dessus tout le reste.
      instance.addLayer({
        id: 'place-highlight',
        type: 'circle',
        source: SOURCE,
        filter: ['==', ['get', 'id'], '__none__'],
        paint: {
          'circle-color': mapColors.todo,
          'circle-radius': 13,
          'circle-stroke-width': 4,
          'circle-stroke-color': mapColors.halo,
        },
      });

      instance.on('click', 'place', (event: MapLayerMouseEvent) => {
        const id = event.features?.[0]?.properties?.id as string | undefined;
        const place = id ? byId.current.get(id) : undefined;
        if (place) onSelect.current(place);
      });

      // Taper un paquet cadre sur ce qu'il contient réellement.
      //
      // Se contenter de zoomer sur le centre du paquet au niveau d'éclatement
      // laissait la moitié des lieux hors du cadre : le centre d'un groupe
      // n'est pas le centre de son emprise, et le zoom d'éclatement ne dit rien
      // de son étendue. On récupère donc les lieux du paquet et on cadre dessus.
      instance.on('click', 'clusters', async (event: MapLayerMouseEvent) => {
        const feature = event.features?.[0];
        const clusterId = feature?.properties?.cluster_id;
        if (clusterId === undefined) return;
        const source = instance.getSource(SOURCE) as GeoJSONSource;

        try {
          const leaves = await source.getClusterLeaves(clusterId as number, 500, 0);
          const bounds = new maplibregl.LngLatBounds();
          for (const leaf of leaves) {
            bounds.extend((leaf.geometry as GeoJSON.Point).coordinates as [number, number]);
          }
          if (!bounds.isEmpty()) {
            instance.fitBounds(bounds, { padding: 60, maxZoom: 13, duration: 600 });
            return;
          }
        } catch {
          // On retombe sur le zoom d'éclatement ci-dessous.
        }

        const zoom = await source.getClusterExpansionZoom(clusterId as number);
        instance.easeTo({
          center: (feature!.geometry as GeoJSON.Point).coordinates as [number, number],
          zoom,
          duration: 500,
        });
      });

      setReady(true);

      for (const layer of ['place', 'clusters']) {
        instance.on('mouseenter', layer, () => {
          instance.getCanvas().style.cursor = 'pointer';
        });
        instance.on('mouseleave', layer, () => {
          instance.getCanvas().style.cursor = '';
        });
      }
    });

    })();

    return () => {
      cancelled = true;
      created?.remove();
      map.current = null;
      setReady(false);
    };
  }, []);

  // Données : rejouées à chaque changement de filtre ou de validation.
  useEffect(() => {
    if (!ready) return;
    const source = map.current?.getSource(SOURCE) as GeoJSONSource | undefined;
    source?.setData(toFeatureCollection(places, visitedIds));
  }, [ready, places, visitedIds]);

  useEffect(() => {
    if (!ready) return;
    map.current?.setFilter('place-highlight', [
      '==',
      ['get', 'id'],
      highlightedId ?? '__none__',
    ]);
  }, [ready, highlightedId]);

  // Position de l'utilisateur : un marqueur distinct, pas un point du catalogue.
  useEffect(() => {
    const instance = map.current;
    if (!ready || !instance) return;
    if (!position) {
      marker.current?.remove();
      marker.current = null;
      return;
    }
    const dot = marker.current ?? new maplibregl.Marker({ color: '#2563EB' });
    dot.setLngLat([position.longitude, position.latitude]).addTo(instance);
    marker.current = dot;
  }, [ready, position]);

  if (failed) {
    return (
      <View style={styles.fallback}>
        <Text style={type.subheading}>Carte impossible à afficher ici</Text>
        <Text style={[type.small, styles.fallbackBody]}>
          Ce navigateur ne fournit pas WebGL 2. La liste des lieux, la validation et la
          progression restent utilisables.
        </Text>
      </View>
    );
  }

  return (
    <View style={styles.canvas}>
      <div ref={container} style={{ position: 'absolute', inset: 0 }} />
      {degraded ? (
        <View style={styles.notice} pointerEvents="none">
          <Text style={styles.noticeText}>
            Fond de carte indisponible — les lieux restent affichés
          </Text>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  canvas: { flex: 1, backgroundColor: colors.surfaceAlt, overflow: 'hidden' },
  fallback: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: spacing.xl,
    backgroundColor: colors.surfaceAlt,
  },
  fallbackBody: { textAlign: 'center', marginTop: spacing.sm },
  notice: {
    position: 'absolute',
    top: 8,
    left: 8,
    right: 56,
    backgroundColor: colors.surface,
    borderRadius: 8,
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  noticeText: { fontSize: 12, color: colors.muted },
});
