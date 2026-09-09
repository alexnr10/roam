import type { MapRef, StyleSpecification } from '@maplibre/maplibre-react-native';
import { useEffect, useMemo, useRef, useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { attributionDesContours, outlinesFor } from '../data/outlines';
import type { ZoneConquest } from '../lib/conquest';
import { useCatalogue } from '../lib/useCatalogue';
import { colors, radius, spacing, type } from '../theme';
import type { AreaLevel } from '../types';
import {
  aPeindre,
  couleurDesTerritoiresNative,
  opaciteDesTerritoiresNative,
} from './conquete';
import { FRANCE_BOUNDS, resolveBasemap } from './mapStyle';

/**
 * La carte de conquête, coloriée — version native.
 *
 * Elle a longtemps affiché « indisponible ici », et le motif écrit dans ce
 * fichier était juste : `react-native-maps` dessine des polygones, mais
 * recolorier cent un départements lui coûtait un redessin complet. MapLibre le
 * fait par une expression, et il est maintenant des deux côtés.
 *
 * La seule différence avec le web tient à `feature-state`, qui n'existe pas
 * hors du navigateur : la nuance d'un territoire s'y lit dans une table
 * indexée par son code — voir `conquete.ts`, où les deux versions se lisent
 * côte à côte.
 *
 * Comme les contours sont NOS données, la carte se dessine même quand le
 * serveur de tuiles est injoignable : la France coloriée sur fond uni, ce qui
 * est exactement le sujet.
 */

let MapLibre: typeof import('@maplibre/maplibre-react-native') | null = null;
try {
  MapLibre = require('@maplibre/maplibre-react-native');
} catch {
  MapLibre = null;
}

export const conquestMapAvailable = MapLibre !== null;

/**
 * L'échelle a-t-elle des contours à colorier ?
 *
 * CALCULÉE, jamais figée : les contours changent avec le pays, et une constante
 * lue au démarrage aurait proposé de colorier des départements qui n'existent
 * pas de l'autre côté de la frontière.
 */
export const conquestOutlinesExist = (level: AreaLevel): boolean =>
  outlinesFor(level) !== null;

const SOURCE = 'territoires';

/** L'emprise de départ, dans l'ordre plat que veut le SDK natif. */
const DEPART: [number, number, number, number] = [
  FRANCE_BOUNDS[0][0],
  FRANCE_BOUNDS[0][1],
  FRANCE_BOUNDS[1][0],
  FRANCE_BOUNDS[1][1],
];

export type ConquestMapProps = {
  zones: ZoneConquest[];
  level: AreaLevel;
  selectedCode: string | null;
  onSelectZone: (code: string | null) => void;
};

export function ConquestMap(props: ConquestMapProps) {
  if (!MapLibre) {
    return (
      <View style={styles.fallback}>
        <Text style={type.subheading}>Carte indisponible ici</Text>
        <Text style={[type.small, styles.body]}>
          Le moteur de carte est un module natif : il demande une application
          compilée. La liste ci-dessous dit exactement la même chose que les
          couleurs.
        </Text>
      </View>
    );
  }
  return <CarteDeConquete {...props} modules={MapLibre} />;
}

function CarteDeConquete({
  zones,
  level,
  selectedCode,
  onSelectZone,
  modules,
}: ConquestMapProps & {
  modules: typeof import('@maplibre/maplibre-react-native');
}) {
  const { Camera, GeoJSONSource, Layer, Map: CarteMapLibre } = modules;
  const carte = useRef<MapRef>(null);
  const [style, setStyle] = useState<StyleSpecification | null>(null);
  const [degrade, setDegrade] = useState(false);

  const surChoix = useRef(onSelectZone);
  surChoix.current = onSelectZone;

  // Le fond DÉPOUILLÉ : la conquête est un tableau de progression, pas une
  // carte où l'on va. Les routes vues à travers un aplat de couleur ne disent
  // rien — ni ville, ni frontière, ni chemin.
  useEffect(() => {
    let annule = false;
    (async () => {
      const { style: fond, degraded } = await resolveBasemap(5000, true);
      if (annule) return;
      setStyle(fond as StyleSpecification);
      setDegrade(degraded);
    })();
    return () => {
      annule = true;
    };
  }, []);

  const version = useCatalogue();
  const contours = useMemo(() => outlinesFor(level), [level, version]);
  const peints = useMemo(() => aPeindre(zones), [zones]);
  const couleur = useMemo(() => couleurDesTerritoiresNative(peints), [peints]);
  const opacite = useMemo(() => opaciteDesTerritoiresNative(peints), [peints]);

  if (!contours) {
    return (
      <View style={styles.fallback}>
        <Text style={type.subheading}>Pas encore de contours à cette échelle</Text>
        <Text style={[type.small, styles.body]}>
          Les régions et les départements se colorient ; les communes viendront
          ensuite. La liste ci-dessous couvre les quatre échelles.
        </Text>
      </View>
    );
  }

  if (!style) {
    return (
      <View style={styles.fallback}>
        <Text style={[type.small, styles.body]}>Chargement de la carte…</Text>
      </View>
    );
  }

  return (
    <View style={styles.canvas}>
      <CarteMapLibre
        ref={carte}
        style={StyleSheet.absoluteFill}
        mapStyle={style}
        attribution
        attributionPosition={{ bottom: 6, right: 6 }}
        logo={false}
        // Un tableau de progression ne se fait ni pivoter ni incliner.
        touchRotate={false}
        touchPitch={false}
        onPress={(event) => {
          const [x, y] = event.nativeEvent.point;
          void (async () => {
            const touches = await carte.current?.queryRenderedFeatures([x, y], {
              layers: ['territoire'],
            });
            const code = touches?.[0]?.properties?.code as string | undefined;
            // Taper hors de tout territoire déselectionne — sinon on reste
            // enfermé dans un département sans savoir comment en sortir.
            surChoix.current(code ?? null);
          })();
        }}
      >
        <Camera
          initialViewState={{
            bounds: DEPART,
            padding: { top: 8, right: 8, bottom: 8, left: 8 },
          }}
        />

        <GeoJSONSource id={SOURCE} data={contours}>
          <Layer
            id="territoire"
            type="fill"
            paint={{
              'fill-color': couleur as never,
              'fill-opacity': opacite as never,
            }}
          />
          <Layer
            id="territoire-bord"
            type="line"
            paint={{ 'line-color': colors.locked, 'line-width': 0.8 }}
          />
          {/* Le territoire choisi : un liseré, jamais un aplat. La couleur dit
              la conquête, elle ne doit pas dire aussi la sélection. */}
          <Layer
            id="territoire-choisi"
            type="line"
            filter={['==', ['get', 'code'], selectedCode ?? '__none__']}
            paint={{ 'line-color': colors.text, 'line-width': 2.2 }}
          />
        </GeoJSONSource>
      </CarteMapLibre>

      {/* La mention de source des contours. Le SDK natif ne sait pas la
          porter comme le web, où elle voyage avec la source et paraît dans le
          contrôle d'attribution ; la Licence ouverte l'exige quand même, alors
          on l'écrit. */}
      {attributionDesContours() ? (
        <View style={styles.source} pointerEvents="none">
          <Text style={styles.sourceTexte}>{attributionDesContours()}</Text>
        </View>
      ) : null}

      {degrade ? (
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
  source: {
    position: 'absolute',
    bottom: 4,
    left: 6,
    backgroundColor: colors.surface,
    borderRadius: 4,
    paddingHorizontal: 5,
    paddingVertical: 2,
  },
  sourceTexte: { fontSize: 9, color: colors.muted },
});
