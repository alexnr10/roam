import 'maplibre-gl/dist/maplibre-gl.css';
import * as maplibregl from 'maplibre-gl';
import type { MapLayerMouseEvent, Map as MapLibreMap } from 'maplibre-gl';
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { OUTLINE_ATTRIBUTION, outlinesFor } from '../data/outlines';
import { shadeOf } from '../lib/conquest';
import type { ZoneConquest } from '../lib/conquest';
import { colors, conquest, radius, spacing, type } from '../theme';
import type { AreaLevel } from '../types';
import type { ConquestMapProps } from './ConquestMap';
import { FRANCE_BOUNDS, resolveBasemap } from './mapStyle';
import { prepareMapLibre } from './maplibreSetup';

/**
 * La carte de conquête, coloriée.
 *
 * Une collection cochée est une liste ; un département colorié est un
 * territoire. Tout l'écart entre les deux tient dans cet écran.
 *
 * Deux choses le rendent possible. Les **contours jointifs** produits par le
 * pipeline (sans quoi un liseré de fond se glisserait entre chaque aplat), et
 * le `feature-state` de MapLibre : la couleur d'un département change sans
 * qu'aucune géométrie ne soit renvoyée au moteur. Valider un lieu recolorie la
 * carte en une poignée d'appels, pas en un redessin.
 *
 * Et comme les contours sont NOS données, la carte se dessine même quand le
 * serveur de tuiles est injoignable : la France coloriée sur fond uni, ce qui
 * est exactement le sujet.
 */

export const conquestMapAvailable = true;

/**
 * L'échelle a-t-elle des contours à colorier ?
 *
 * Posée ici plutôt que dans l'écran : c'est ce qui évite au build natif
 * d'embarquer un demi-mégaoctet de polygones qu'il ne sait pas dessiner.
 */
export const conquestOutlinesExist = (level: AreaLevel): boolean =>
  outlinesFor(level) !== null;

const SOURCE = 'territoires';

/** Opacité maximale d'un territoire entamé, avant d'avoir fini quoi que ce soit. */
const STARTED_MAX_OPACITY = 0.55;

type Painted = { code: string; shade: string; pct: number };

function paintOf(zones: ZoneConquest[]): Painted[] {
  return zones.map((zone) => ({
    code: zone.area.code,
    shade: shadeOf(zone).kind,
    pct: zone.overall.pct,
  }));
}

export function ConquestMap({ zones, level, selectedCode, onSelectZone }: ConquestMapProps) {
  const container = useRef<HTMLDivElement | null>(null);
  const map = useRef<MapLibreMap | null>(null);
  // Codes actuellement peints : à retirer avant de peindre les suivants, sinon
  // un département changeant d'échelle garderait sa couleur précédente.
  const painted = useRef<string[]>([]);
  // Le gestionnaire de clic n'est posé qu'une fois et doit voir l'état courant.
  const onSelect = useRef(onSelectZone);
  onSelect.current = onSelectZone;

  const [degraded, setDegraded] = useState(false);
  // WebGL2 manque encore sur quelques WebViews Android et sur les machines
  // sans accélération : MapLibre lève à la construction, et sans ce garde-fou
  // l'écran restait un rectangle gris sans un mot d'explication.
  const [failed, setFailed] = useState(false);
  const [ready, setReady] = useState(false);

  const outlines = useMemo(() => outlinesFor(level), [level]);
  const shades = useMemo(() => paintOf(zones), [zones]);

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
          fitBoundsOptions: { padding: 8 },
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
          // Sans identifiant, `feature-state` n'a rien à quoi s'accrocher et
          // tous les territoires resteraient gris. `promoteId` accepte une
          // chaîne, ce que l'identifiant natif de GeoJSON refuse — et « 2A »
          // n'est pas un nombre.
          promoteId: 'code',
          attribution: OUTLINE_ATTRIBUTION,
        });

        instance.addLayer({
          id: 'territoire',
          type: 'fill',
          source: SOURCE,
          paint: {
            'fill-color': [
              'match',
              ['coalesce', ['feature-state', 'shade'], 'empty'],
              'total',
              conquest.total,
              'theme',
              conquest.theme,
              'started',
              conquest.total,
              conquest.empty,
            ],
            // Un territoire entamé pâlit à proportion de ce qu'il reste : sans
            // ce dégradé la carte serait binaire et ne montrerait aucune
            // progression entre le premier lieu et le dernier.
            'fill-opacity': [
              'case',
              ['==', ['coalesce', ['feature-state', 'shade'], 'empty'], 'started'],
              [
                'interpolate',
                ['linear'],
                ['coalesce', ['feature-state', 'pct'], 0],
                0,
                0.08,
                100,
                STARTED_MAX_OPACITY,
              ],
              ['==', ['coalesce', ['feature-state', 'shade'], 'empty'], 'empty'],
              0.45,
              0.85,
            ],
          },
        });

        instance.addLayer({
          id: 'territoire-bord',
          type: 'line',
          source: SOURCE,
          paint: {
            'line-color': colors.locked,
            'line-width': 0.8,
          },
        });

        // Le territoire choisi : un liseré, jamais un aplat. La couleur dit la
        // conquête, elle ne doit pas dire aussi la sélection.
        instance.addLayer({
          id: 'territoire-choisi',
          type: 'line',
          source: SOURCE,
          filter: ['==', ['get', 'code'], '__none__'],
          paint: { 'line-color': colors.text, 'line-width': 2.2 },
        });

        instance.on('click', 'territoire', (event: MapLayerMouseEvent) => {
          const code = event.features?.[0]?.properties?.code as string | undefined;
          if (code) onSelect.current(code);
        });
        // Taper hors de tout territoire déselectionne — sinon on reste
        // enfermé dans un département sans savoir comment en sortir.
        instance.on('click', (event) => {
          const hits = instance.queryRenderedFeatures(event.point, { layers: ['territoire'] });
          if (hits.length === 0) onSelect.current(null);
        });
        instance.on('mouseenter', 'territoire', () => {
          instance.getCanvas().style.cursor = 'pointer';
        });
        instance.on('mouseleave', 'territoire', () => {
          instance.getCanvas().style.cursor = '';
        });

        setReady(true);
      });
    })();

    return () => {
      cancelled = true;
      created?.remove();
      map.current = null;
      painted.current = [];
      setReady(false);
    };
  }, []);

  // Géométrie : elle ne change qu'au changement d'échelle.
  useEffect(() => {
    if (!ready) return;
    const source = map.current?.getSource(SOURCE) as maplibregl.GeoJSONSource | undefined;
    source?.setData(outlines ?? { type: 'FeatureCollection', features: [] });
    // Les états peints se rapportaient à l'échelle précédente ; ils ne veulent
    // plus rien dire ici.
    painted.current = [];
  }, [ready, outlines]);

  // Couleurs : rejouées à chaque visite validée. Aucune géométrie n'est
  // renvoyée au moteur, seulement cent une paires clé-valeur.
  useEffect(() => {
    const instance = map.current;
    if (!ready || !instance) return;
    for (const code of painted.current) {
      instance.removeFeatureState({ source: SOURCE, id: code });
    }
    for (const { code, shade, pct } of shades) {
      instance.setFeatureState({ source: SOURCE, id: code }, { shade, pct });
    }
    painted.current = shades.map((entry) => entry.code);
  }, [ready, shades, outlines]);

  useEffect(() => {
    if (!ready) return;
    map.current?.setFilter('territoire-choisi', [
      '==',
      ['get', 'code'],
      selectedCode ?? '__none__',
    ]);
  }, [ready, selectedCode]);

  if (failed) {
    return (
      <View style={styles.fallback}>
        <Text style={type.subheading}>Carte impossible à afficher ici</Text>
        <Text style={[type.small, styles.body]}>
          Ce navigateur ne fournit pas WebGL 2. La liste ci-dessous dit exactement la
          même chose que les couleurs.
        </Text>
      </View>
    );
  }

  if (!outlines) {
    return (
      <View style={styles.fallback}>
        <Text style={type.subheading}>Pas encore de contours à cette échelle</Text>
        <Text style={[type.small, styles.body]}>
          Les régions et les départements se colorient ; les communes viendront ensuite.
          La liste ci-dessous couvre les quatre échelles.
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
            Fond de carte indisponible — les territoires restent coloriés
          </Text>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  canvas: {
    flex: 1,
    backgroundColor: colors.surfaceAlt,
    borderRadius: radius.lg,
    overflow: 'hidden',
  },
  fallback: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: spacing.xl,
    backgroundColor: colors.surfaceAlt,
    borderRadius: radius.lg,
  },
  body: { textAlign: 'center', marginTop: spacing.sm },
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
