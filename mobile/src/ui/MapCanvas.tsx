import type {
  CameraRef,
  MapRef,
  StyleSpecification,
} from '@maplibre/maplibre-react-native';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { StyleSheet, Text, View, type LayoutChangeEvent } from 'react-native';

import { outlinesFor } from '../data/outlines';
import { etoilesDe } from '../lib/etoiles';
import { useCatalogue } from '../lib/useCatalogue';
import type { Emprise } from '../lib/regions';
import {
  REGIONS,
  emprise,
  prochaineOuverture,
  regionDuCadre,
  regionDuDepartement,
  voile,
} from '../lib/regions';
import { colors, spacing, type } from '../theme';
import type { Coordinates, Place } from '../types';
import {
  SOURCE_DEPTS,
  SOURCE_LIEUX,
  SOURCE_REGIONS,
  SOURCE_VOILE,
  couchesDeLaCarte,
} from './couches';
import { GLYPHES } from './glyphesNatifs';
import { nomDuGlyphe } from './glyphes';
import {
  ATTENUATION_AUTRES,
  FRANCE_BOUNDS,
  margeDeCamera,
  SEUIL_REGION,
  TRANSITION,
  resolveBasemap,
} from './mapStyle';

/**
 * Carte native, sur MapLibre.
 *
 * La même carte que sur le web, et pas seulement à l'œil : les couches
 * viennent de la même table (`couches.ts`) et les expressions du même fichier
 * de style (`mapStyle.ts`). Une expression MapLibre ne sait pas sur quelle
 * plateforme elle tourne — les aplats de régions, les pastilles graduées par
 * niveau, les symboles de thèmes, le voile hors-France et l'échelle d'opacité
 * qui fait tomber ce voile en ouvrant une région sont donc les mêmes objets.
 *
 * Ce qui a dû changer tient en trois points, et chacun est une limite du SDK
 * natif, jamais un choix :
 *
 * 1. **`feature-state` n'existe pas** hors de la version web. La question qu'il
 *    posait — « est-ce la région ouverte ? » — se pose maintenant dans
 *    l'expression elle-même : voir `opaciteDesAplatsNative`.
 * 2. **Pas de réécriture de peinture image par image.** Le web anime l'opacité
 *    à soixante images par seconde en écrivant une propriété ; ici chaque
 *    écriture traverse le pont. On emploie donc les TRANSITIONS du format de
 *    style, que le SDK interpole lui-même — un fondu au lieu d'une cascade
 *    depuis le centre de la région. C'est la seule chose que la carte native
 *    ne sait pas encore faire comme le web.
 * 3. **Pas de courbe de Bézier sur la caméra** : `easing` n'accepte que trois
 *    noms. On prend `ease`, le plus proche de la courbe de la maquette.
 *
 * Le survol, lui, n'a pas été porté et ne le sera pas : sur un écran tactile,
 * un doigt qui ne touche pas n'est nulle part.
 */

/**
 * Le moteur de carte, chargé sans garantie.
 *
 * MapLibre est un module NATIF : il n'existe que dans une application compilée,
 * jamais dans Expo Go, où il lève dès l'importation. Plutôt que de faire tomber
 * l'application au démarrage, on le charge défensivement et on retombe sur un
 * message clair — le reste continue de fonctionner : listes, recherche,
 * validation, progression.
 *
 * `require` et non `import` : un import statique est résolu avant que la
 * moindre ligne ne s'exécute, et il n'y a alors rien à intercepter.
 */
let MapLibre: typeof import('@maplibre/maplibre-react-native') | null = null;
try {
  MapLibre = require('@maplibre/maplibre-react-native');
} catch {
  MapLibre = null;
}

export const mapAvailable = MapLibre !== null;

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
 * La tolérance du doigt, en points.
 *
 * Une pastille de niveau 3 fait trois points de rayon : visée au doigt, on la
 * rate une fois sur deux, et c'est le geste le plus fréquent de l'application.
 * On interroge donc une BOÎTE autour du contact plutôt que le point exact —
 * même tolérance que sur le web, sans rien dessiner de plus.
 */
const TOLERANCE_PX = 18;

/** L'emprise de départ, dans l'ordre plat que veut le SDK natif. */
const DEPART: [number, number, number, number] = [
  FRANCE_BOUNDS[0][0],
  FRANCE_BOUNDS[0][1],
  FRANCE_BOUNDS[1][0],
  FRANCE_BOUNDS[1][1],
];

/** Le cadrage de la vue de départ : la France entière, à douze points du bord. */
const CADRAGE_DEPART = { top: 12, right: 12, bottom: 12, left: 12 };


function toFeatureCollection(
  places: Place[],
  visitedIds: ReadonlySet<string>,
): GeoJSON.FeatureCollection<GeoJSON.Point> {
  return {
    type: 'FeatureCollection',
    features: places.map((place) => ({
      type: 'Feature',
      id: place.id,
      geometry: { type: 'Point', coordinates: [place.lon, place.lat] },
      properties: {
        id: place.id,
        name: place.name,
        visited: visitedIds.has(place.id) ? 1 : 0,
        // La taille d'une pastille dit la note NATIONALE, dans sa catégorie :
        // trois étoiles font le gros point. Un classement relatif à la région
        // ouverte changeait de sens d'un vol à l'autre — le même château
        // grossissait en passant la frontière, ce qu'aucune carte ne devrait
        // faire.
        tier: 4 - etoilesDe(place.id),
        themeId: place.themeId,
      },
    })),
  };
}

export function MapCanvas(props: MapCanvasProps) {
  if (!MapLibre) {
    return (
      <View style={styles.fallback}>
        <Text style={type.subheading}>Carte indisponible ici</Text>
        <Text style={[type.small, styles.fallbackBody]}>
          Le moteur de carte est un module natif : il demande une application
          compilée, et n'existe pas dans Expo Go. La liste des lieux, la
          recherche, la validation et la progression restent utilisables.
        </Text>
      </View>
    );
  }
  return <CarteNative {...props} modules={MapLibre} />;
}

/**
 * La carte, une fois le moteur chargé.
 *
 * Séparée parce qu'elle tient un état, et qu'un composant ne peut pas appeler
 * `useState` après un `return` conditionnel.
 */
function CarteNative({
  modules,
  places,
  visitedIds,
  position,
  onSelectPlace,
  highlightedId,
  focus,
  onDeselect,
  onRegionChange,
  onCentre,
  retour,
  ouvrir: demande,
}: MapCanvasProps & { modules: typeof import('@maplibre/maplibre-react-native') }) {
  const {
    Camera,
    GeoJSONSource,
    Images,
    Layer,
    Map: CarteMapLibre,
    UserLocation,
  } = modules;
  const carte = useRef<MapRef>(null);
  const camera = useRef<CameraRef>(null);

  const [style, setStyle] = useState<StyleSpecification | null>(null);
  const [degrade, setDegrade] = useState(false);
  const [ouverte, setOuverte] = useState<string | null>(null);
  const [cadre, setCadre] = useState({ largeur: 0, hauteur: 0 });

  /**
   * La version du catalogue, pour les contours.
   *
   * Les contours changent avec le pays, et un `useMemo` sans dépendance les
   * aurait figés sur celui du démarrage : en passant la frontière, la carte
   * aurait gardé les aplats français par-dessus l'Italie.
   */
  const versionDuCatalogue = useCatalogue();

  // Les gestionnaires vivent dans des références : ils sont posés une fois et
  // doivent toujours voir l'état courant, pas celui du rendu qui les a créés.
  // La table des lieux, elle, est recalculée quand la LISTE change et pas à
  // chaque rendu : deux mille insertions pour ouvrir une région, ce serait
  // deux mille insertions pour rien.
  const parId = useRef(new Map<string, Place>());
  parId.current = useMemo(
    () => new Map(places.map((place) => [place.id, place])),
    [places],
  );
  const surChoix = useRef(onSelectPlace);
  surChoix.current = onSelectPlace;
  const surVide = useRef(onDeselect);
  surVide.current = onDeselect;
  const surRegion = useRef(onRegionChange);
  surRegion.current = onRegionChange;
  const surCentre = useRef(onCentre);
  surCentre.current = onCentre;

  const ouverteRef = useRef<string | null>(null);
  /**
   * Le zoom auquel la région s'est ouverte.
   *
   * Sans cette ancre, la règle « remplit-elle l'écran ? » est réévaluée à
   * chaque fin de mouvement, y compris juste après le vol qu'on vient de
   * déclencher : la carte peut alors défaire le geste de l'utilisateur, sur un
   * calcul qu'il n'a pas demandé. Le toucher fait donc autorité, et seul un
   * DÉZOOM franc referme.
   */
  const zoomOuverture = useRef<number | null>(null);
  const margeRef = useRef(margeDeCamera(0, 0));
  margeRef.current = margeDeCamera(cadre.largeur, cadre.hauteur);

  // Le fond de carte, repeint aux couleurs de l'app. `resolveBasemap` essaie
  // les fonds dans l'ordre et retombe sur un style minimal : hors réseau, les
  // régions restent dessinées et l'application reste utilisable.
  useEffect(() => {
    let annule = false;
    (async () => {
      const { style: fond, degraded } = await resolveBasemap();
      if (annule) return;
      setStyle(fond as StyleSpecification);
      setDegrade(degraded);
    })();
    return () => {
      annule = true;
    };
  }, []);

  const contoursRegions = useMemo(
    () => outlinesFor('region'),
    [versionDuCatalogue],
  );
  const contoursDepts = useMemo(
    () => outlinesFor('departement'),
    [versionDuCatalogue],
  );
  const leVoile = useMemo(() => voile(), [versionDuCatalogue]);

  /**
   * Les lieux de la région ouverte, et eux seuls.
   *
   * À l'échelle du pays, aucun : c'est le fondement de la carte. Deux mille
   * points sur la France ne se lisent pas, et une bulle « 272 » ne dit rien de
   * ce qu'il y a dessous.
   */
  const dedans = useMemo(
    () => (ouverte ? places.filter((place) => place.regionCode === ouverte) : []),
    [places, ouverte],
  );
  const donnees = useMemo(
    () => toFeatureCollection(dedans, visitedIds),
    [dedans, visitedIds],
  );

  /** Les départements de la région ouverte : un repère DANS la région, pas un étage. */
  const departements = useMemo(
    () =>
      ouverte
        ? (contoursDepts?.features ?? [])
            .map((feature) => feature.properties.code)
            .filter((code) => regionDuDepartement(code) === ouverte)
        : [],
    [contoursDepts, ouverte],
  );

  /**
   * Le vol vers une région.
   *
   * Le zoom d'arrivée n'est jamais fixe : la caméra se cale sur l'EMPRISE de la
   * région. Mayotte arrive donc beaucoup plus près que l'Occitanie — un zoom en
   * dur donnerait huit taches perdues dans un aplat vide d'un côté, et deux
   * cent soixante-douze points débordant du cadre de l'autre.
   */
  const voler = useCallback((code: string) => {
    const feature = REGIONS.get(code);
    if (!feature) return;
    const [[ouest, sud], [est, nord]] = emprise(feature.geometry);
    camera.current?.fitBounds([ouest, sud, est, nord], {
      padding: margeRef.current,
      duration: TRANSITION.zoom,
      easing: 'ease',
    });
  }, []);

  const ouvrirRegion = useCallback(
    (code: string | null) => {
      ouverteRef.current = code;
      // L'ancre se posera à l'arrivée du vol : d'ici là, rien ne referme.
      zoomOuverture.current = null;
      setOuverte(code);
      surRegion.current?.(code);
      if (code) voler(code);
    },
    [voler],
  );

  /**
   * La bande réellement libre, en coordonnées géographiques.
   *
   * L'écran entier n'est pas ce qu'on voit : c'est dans cette bande-là que la
   * caméra cadre une région, donc c'est elle — et non la vue entière — qui doit
   * dire si la région remplit l'écran. Comparer à la vue entière faisait qu'une
   * région tout juste cadrée n'en occupait qu'à peine la moitié : elle se
   * refermait sur place, et ses lieux disparaissaient une fraction de seconde
   * après être apparus.
   */
  const cadreLibre = useCallback(async (): Promise<Emprise | null> => {
    const instance = carte.current;
    if (!instance || cadre.largeur === 0 || cadre.hauteur === 0) return null;
    const marge = margeRef.current;
    const [hautGauche, basDroite] = await Promise.all([
      instance.unproject([marge.left, marge.top]),
      instance.unproject([
        cadre.largeur - marge.right,
        cadre.hauteur - marge.bottom,
      ]),
    ]);
    return [
      [Math.min(hautGauche[0], basDroite[0]), Math.min(hautGauche[1], basDroite[1])],
      [Math.max(hautGauche[0], basDroite[0]), Math.max(hautGauche[1], basDroite[1])],
    ];
  }, [cadre.largeur, cadre.hauteur]);

  /**
   * Fin de mouvement : où regarde-t-on, et qu'est-ce qui est ouvert ?
   *
   * La région ouverte est celle qui REMPLIT l'écran. Dézoomer referme — c'est
   * le geste que tout le monde tente en premier, et il n'y a rien à apprendre.
   */
  const surMouvement = useCallback(
    async (etat: { center: [number, number]; zoom: number }) => {
      // Avant tout le reste : où regarde-t-on ? C'est de cette seule question
      // que dépend le pays, et elle ne coûte rien.
      surCentre.current?.(etat.center[0], etat.center[1]);
      // Le cadre n'est pas encore mesuré : on ne sait pas ce que « remplir
      // l'écran » veut dire, et répondre sur un rectangle vide reviendrait à
      // refermer une région que l'utilisateur vient d'ouvrir.
      const bande = await cadreLibre();
      if (!bande) return;
      const vu = etat.zoom < SEUIL_REGION ? null : regionDuCadre(bande);
      const suite = prochaineOuverture(
        { region: ouverteRef.current, ancre: zoomOuverture.current },
        vu,
        etat.zoom,
      );
      zoomOuverture.current = suite.ancre;
      if (suite.region === ouverteRef.current) return;
      ouverteRef.current = suite.region;
      setOuverte(suite.region);
      surRegion.current?.(suite.region);
    },
    [cadreLibre],
  );

  /**
   * Le doigt sur la carte : un lieu, une région, ou le fond.
   *
   * Dans cet ordre, et l'ordre compte : un lieu est posé SUR un aplat de
   * région, et interroger la région d'abord rendrait tout point de la carte
   * inatteignable.
   */
  const surToucher = useCallback(async (
    [x, y]: [number, number],
    [lon, lat]: [number, number],
  ) => {
    const instance = carte.current;
    if (!instance) return;

    const boite: [[number, number], [number, number]] = [
      [x - TOLERANCE_PX, y - TOLERANCE_PX],
      [x + TOLERANCE_PX, y + TOLERANCE_PX],
    ];
    const lieux = await instance.queryRenderedFeatures(boite, { layers: ['place'] });
    if (lieux.length > 0) {
      // Le plus proche du doigt, pas le premier venu : deux pastilles voisines
      // rendraient le choix arbitraire.
      //
      // Mesuré en coordonnées plutôt qu'en pixels : reprojeter chaque candidat
      // coûterait un aller-retour vers le natif par pastille, et sur une boîte
      // de trente-six points de côté les deux classements sont les mêmes.
      const cos = Math.max(Math.cos((lat * Math.PI) / 180), 0.01);
      let meilleur = lieux[0];
      let distance = Infinity;
      for (const feature of lieux) {
        const [flon, flat] = (feature.geometry as GeoJSON.Point).coordinates;
        const ecart = ((flon - lon) * cos) ** 2 + (flat - lat) ** 2;
        if (ecart < distance) {
          distance = ecart;
          meilleur = feature;
        }
      }
      const id = meilleur.properties?.id as string | undefined;
      const place = id ? parId.current.get(id) : undefined;
      if (place) {
        surChoix.current(place);
        return;
      }
    }

    const aplats = await instance.queryRenderedFeatures([x, y], {
      layers: ['region-aplat'],
    });
    const code = aplats[0]?.properties?.code as string | undefined;
    // Toucher la région déjà ouverte, c'est toucher le fond : cela referme la
    // fiche. Toucher la VOISINE, en revanche, doit y aller — passer d'une
    // région à sa voisine est le geste même d'un guide qu'on feuillette.
    if (code && code !== ouverteRef.current) {
      ouvrirRegion(code);
      return;
    }
    surVide.current?.();
  }, [ouvrirRegion]);

  /**
   * Une région demandée depuis un autre écran.
   *
   * C'est la porte d'entrée de l'outre-mer : cadrée sur la métropole, la
   * Guadeloupe est à six mille kilomètres hors de l'écran, et personne ne l'y
   * trouve en faisant glisser au hasard. La liste d'Explorer y mène, et la
   * carte fait le même vol que sur un toucher.
   */
  useEffect(() => {
    if (!demande) return;
    const code = demande.split('#')[0];
    if (!REGIONS.has(code)) return;
    ouvrirRegion(code);
  }, [demande, ouvrirRegion]);

  /**
   * Le retour à la France, par la pastille.
   *
   * Les lieux s'effacent AVANT que la caméra ne bouge — la région se referme
   * tout de suite, le vol part quand leur fondu est fini — pour qu'on ne les
   * voie pas glisser pendant le recul.
   */
  useEffect(() => {
    if (!retour) return;
    ouverteRef.current = null;
    zoomOuverture.current = null;
    setOuverte(null);
    surRegion.current?.(null);
    const depart = setTimeout(() => {
      camera.current?.fitBounds(DEPART, {
        padding: CADRAGE_DEPART,
        duration: TRANSITION.retour.zoom,
        easing: 'ease',
      });
    }, TRANSITION.retour.lieux);
    return () => clearTimeout(depart);
  }, [retour]);

  // Recentrage sur un lieu choisi ailleurs — dans le bandeau, dans la
  // recherche. Les dépendances sont les COORDONNÉES, pas l'objet : `focus` est
  // reconstruit à chaque rendu, et s'y fier recentrerait la carte à la moindre
  // frappe dans la recherche.
  const focusLat = focus?.lat ?? null;
  const focusLon = focus?.lon ?? null;
  useEffect(() => {
    if (focusLat === null || focusLon === null) return;
    let annule = false;
    (async () => {
      const zoom = (await carte.current?.getZoom()) ?? 0;
      if (annule) return;
      camera.current?.easeTo({
        center: [focusLon, focusLat],
        zoom: Math.max(zoom, 11),
        duration: 600,
      });
    })();
    return () => {
      annule = true;
    };
  }, [focusLat, focusLon]);

  const couches = useMemo(
    () =>
      couchesDeLaCarte({
        natif: true,
        ouverte,
        misEnAvant: highlightedId ?? null,
        departements,
        avecPolices: Boolean(style?.glyphs),
        // Les autres régions s'effacent PENDANT le vol, pas avant : les faire
        // pâlir à l'arrêt donne un clignotement, et après l'atterrissage un
        // deuxième temps mort. C'est la transition du style qui les emmène.
        attenuation: ouverte ? ATTENUATION_AUTRES : 1,
      }),
    [ouverte, highlightedId, departements, style],
  );

  /**
   * Les couches d'une source, en composants.
   *
   * `Layer` reçoit `paint` et `layout` au format du style : ce sont exactement
   * les objets de la table, sans traduction. Le `source` lui vient de la source
   * qui l'enveloppe.
   */
  const poser = (source: string) =>
    couches
      .filter((couche) => couche.source === source)
      .map((couche) => (
      <Layer
        key={couche.id}
        id={couche.id}
        type={couche.type as 'fill'}
        filter={couche.filter as never}
        layout={couche.layout as never}
        paint={couche.paint as never}
      />
    ));

  if (!style) {
    return (
      <View style={styles.fallback}>
        <Text style={[type.small, styles.fallbackBody]}>Chargement de la carte…</Text>
      </View>
    );
  }

  return (
    <View
      style={styles.canvas}
      onLayout={(event: LayoutChangeEvent) => {
        const { width, height } = event.nativeEvent.layout;
        setCadre({ largeur: width, hauteur: height });
      }}
    >
      <CarteMapLibre
        ref={carte}
        style={StyleSheet.absoluteFill}
        mapStyle={style}
        // La carte reste une vraie carte du monde, librement navigable : c'est
        // ainsi qu'on atteint les cinq régions d'outre-mer, sans encart dans un
        // coin. L'emprise de la France n'est qu'une vue de DÉPART.
        attribution
        attributionPosition={{ bottom: 8, right: 8 }}
        logo={false}
        // La rotation et l'inclinaison n'apportent rien à un guide, et se
        // déclenchent sans qu'on l'ait voulu en zoomant à deux doigts : la
        // carte partait de travers, et rien ne disait comment la redresser.
        touchRotate={false}
        touchPitch={false}
        onPress={(event) => {
          const { point, lngLat } = event.nativeEvent;
          void surToucher(point, lngLat);
        }}
        onRegionDidChange={(event) => {
          void surMouvement(event.nativeEvent);
        }}
      >
        <Camera
          ref={camera}
          initialViewState={{ bounds: DEPART, padding: CADRAGE_DEPART }}
        />

        <Images images={imagesDesGlyphes} />

        {/* Les couches viennent d'une table partagée avec la carte web :
            voir `couches.ts`. Deux jeux de couches écrits séparément avaient
            déjà divergé en silence, et l'anneau du lieu touché n'existait sur
            aucune des deux. */}
        <GeoJSONSource id={SOURCE_VOILE} data={leVoile}>
          {poser(SOURCE_VOILE)}
        </GeoJSONSource>

        {contoursRegions ? (
          <GeoJSONSource id={SOURCE_REGIONS} data={contoursRegions}>
            {poser(SOURCE_REGIONS)}
          </GeoJSONSource>
        ) : null}

        {contoursDepts ? (
          <GeoJSONSource id={SOURCE_DEPTS} data={contoursDepts}>
            {poser(SOURCE_DEPTS)}
          </GeoJSONSource>
        ) : null}

        <GeoJSONSource id={SOURCE_LIEUX} data={donnees}>
          {poser(SOURCE_LIEUX)}
        </GeoJSONSource>

        {/* La position, par le repère du système : il porte le cercle de
            précision et le cap, que rien dans nos données ne saurait dire. */}
        {position ? <UserLocation accuracy /> : null}
      </CarteMapLibre>

      {degrade ? (
        <View style={styles.notice} pointerEvents="none">
          <Text style={styles.noticeText}>
            Fond de carte indisponible — les régions restent dessinées
          </Text>
        </View>
      ) : null}
    </View>
  );
}

/** Les vingt-trois glyphes, sous le nom que la couche de symboles leur donne. */
const imagesDesGlyphes = Object.fromEntries(
  Object.entries(GLYPHES).map(([themeId, image]) => [nomDuGlyphe(themeId), image]),
);

const styles = StyleSheet.create({
  canvas: { flex: 1, backgroundColor: colors.bg, overflow: 'hidden' },
  fallback: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: spacing.xl,
    backgroundColor: colors.bg,
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
