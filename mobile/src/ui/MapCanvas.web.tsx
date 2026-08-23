// La feuille de style de MapLibre porte les contrôles et la mention
// d'attribution d'OpenStreetMap, qui est une obligation de la licence ODbL.
import 'maplibre-gl/dist/maplibre-gl.css';
import * as maplibregl from 'maplibre-gl';
import type { GeoJSONSource, MapLayerMouseEvent, Map as MapLibreMap } from 'maplibre-gl';
import React, { useEffect, useRef } from 'react';
import { StyleSheet, View } from 'react-native';

import { colors } from '../theme';
import type { Place } from '../types';
import type { MapCanvasProps } from './MapCanvas';
import { BASEMAP_STYLE, CLUSTER_MAX_ZOOM, FRANCE_VIEW, mapColors } from './mapStyle';

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

  useEffect(() => {
    if (!container.current || map.current) return;

    const instance = new maplibregl.Map({
      container: container.current,
      style: BASEMAP_STYLE,
      center: [FRANCE_VIEW.longitude, FRANCE_VIEW.latitude],
      zoom: FRANCE_VIEW.zoom,
      attributionControl: { compact: true },
    });
    map.current = instance;
    instance.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');

    instance.on('load', () => {
      instance.addSource(SOURCE, {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] },
        cluster: true,
        clusterRadius: 46,
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
          'circle-radius': ['step', ['get', 'point_count'], 15, 10, 20, 50, 26],
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

      // Taper un paquet le déplie plutôt que de ne rien faire.
      instance.on('click', 'clusters', async (event: MapLayerMouseEvent) => {
        const feature = event.features?.[0];
        const clusterId = feature?.properties?.cluster_id;
        if (clusterId === undefined) return;
        const source = instance.getSource(SOURCE) as GeoJSONSource;
        const zoom = await source.getClusterExpansionZoom(clusterId as number);
        instance.easeTo({
          center: (feature!.geometry as GeoJSON.Point).coordinates as [number, number],
          zoom,
          duration: 500,
        });
      });

      for (const layer of ['place', 'clusters']) {
        instance.on('mouseenter', layer, () => {
          instance.getCanvas().style.cursor = 'pointer';
        });
        instance.on('mouseleave', layer, () => {
          instance.getCanvas().style.cursor = '';
        });
      }
    });

    return () => {
      instance.remove();
      map.current = null;
    };
  }, []);

  // Données : rejouées à chaque changement de filtre ou de validation.
  useEffect(() => {
    const instance = map.current;
    if (!instance) return;

    const push = () => {
      const source = instance.getSource(SOURCE) as GeoJSONSource | undefined;
      source?.setData(toFeatureCollection(places, visitedIds));
    };
    if (instance.isStyleLoaded()) push();
    else instance.once('load', push);
  }, [places, visitedIds]);

  useEffect(() => {
    const instance = map.current;
    if (!instance) return;
    const apply = () => {
      if (instance.getLayer('place-highlight')) {
        instance.setFilter('place-highlight', ['==', ['get', 'id'], highlightedId ?? '__none__']);
      }
    };
    if (instance.isStyleLoaded()) apply();
    else instance.once('load', apply);
  }, [highlightedId]);

  // Position de l'utilisateur : un marqueur distinct, pas un point du catalogue.
  useEffect(() => {
    const instance = map.current;
    if (!instance) return;
    if (!position) {
      marker.current?.remove();
      marker.current = null;
      return;
    }
    const dot = marker.current ?? new maplibregl.Marker({ color: '#2563EB' });
    dot.setLngLat([position.longitude, position.latitude]).addTo(instance);
    marker.current = dot;
  }, [position]);

  return (
    <View style={styles.canvas}>
      <div ref={container} style={{ position: 'absolute', inset: 0 }} />
    </View>
  );
}

const styles = StyleSheet.create({
  canvas: { flex: 1, backgroundColor: colors.surfaceAlt, overflow: 'hidden' },
});
