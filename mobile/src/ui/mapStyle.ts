import { colors } from '../theme';

/**
 * Fond de carte, et l'identité qu'on lui applique.
 *
 * OpenFreeMap sert des tuiles vectorielles complètes de la planète, sans clé ni
 * compte. On garde `positron` comme base : c'est le style le plus pauvre en
 * couleurs, donc le plus facile à repeindre entièrement. `liberty` a déjà un
 * avis sur tout (forêts vertes, routes jaunes, bâtiments beiges) qu'il faudrait
 * défaire couche par couche.
 *
 * La base n'est PAS ce qu'on voit : `repeindre()` réécrit la peinture de chaque
 * couche avant de donner le style à MapLibre. Le fond OpenStreetMap brut ne
 * s'affiche jamais.
 */
export const BASEMAP_STYLES = [
  'https://tiles.openfreemap.org/styles/positron',
  'https://tiles.openfreemap.org/styles/liberty',
  // Dernier recours : les tuiles de démonstration de MapLibre.
  'https://demotiles.maplibre.org/style.json',
];

/**
 * Emprise de la France métropolitaine. Vue de DÉPART, pas une limite.
 *
 * La carte reste une vraie carte du monde, librement navigable : aucun
 * `maxBounds`, aucun `maxZoom` restreint. On se cadre ici au premier affichage,
 * et c'est tout.
 */
export const FRANCE_BOUNDS: [[number, number], [number, number]] = [
  [-5.2, 41.3],
  [9.6, 51.2],
];

/**
 * Plus de paquets chiffrés.
 *
 * Le regroupement en bulles était la réponse à « 2029 points sur la France ».
 * La réponse est maintenant en amont : à l'échelle du pays on ne montre AUCUN
 * lieu, seulement les régions en aplats. Un lieu n'apparaît que dans une région
 * ouverte, où il y en a au pire 272 — et 272 pastilles graduées par niveau se
 * lisent, là où une bulle « 272 » ne dit rien.
 *
 * On garde la constante à 0 pour que le code de la source GeoJSON reste en
 * place : passer `cluster: false` est un booléen à changer, pas une refonte.
 */
export const CLUSTER_MAX_ZOOM = 0;
export const CLUSTER_RADIUS = 38;

/**
 * Les couleurs de la carte.
 *
 * Toutes viennent des jetons de l'app, sauf deux : l'eau et l'eau profonde. Une
 * carte a besoin d'une teinte qui n'est ni sable ni sauge, sinon la mer devient
 * de la terre. Ces deux-là sont donc dérivées à la main en OKLCH sur la même
 * échelle de clarté que le reste — froides, mais désaturées au point de rester
 * dans la famille.
 *
 *   water     = oklch(85% 0.028 215)
 *   waterDeep = oklch(77% 0.036 215)
 */
export const mapColors = {
  /** La terre, hors régions. Le sable de l'app : la carte et l'app sont une seule surface. */
  earth: colors.bg,
  water: '#C3D6DA',
  waterDeep: '#A6BFC6',
  /** Forêts, parcs, prés. La sauge du système, très diluée. */
  green: '#E1EECC',
  built: colors.surfaceAlt,
  road: colors.border,
  roadMinor: colors.surfaceAlt,
  labelInk: '#474238',
  labelHalo: colors.bg,

  /** Pastilles de lieux. */
  todo: colors.primaryLight,
  visited: colors.verified,
  halo: colors.surface,
  /** Conservé : du code s'y réfère encore. Plus aucune couche ne l'emploie. */
  cluster: '#82796A',
  clusterText: '#FFFFFF',
  ground: colors.surfaceAlt,
};

/**
 * Les quatre sables des régions.
 *
 * Dix-huit aplats de la même couleur donnent une tache ; dix-huit couleurs
 * différentes donnent un patchwork de garderie. Quatre teintes de la même
 * famille — lin, sable, sauge pâle, terre pâle — suffisent : c'est un
 * quadrillage de marqueterie, et il ne prétend rien mesurer.
 *
 * L'affectation est un coloriage à la main, pas un hachage : deux régions
 * voisines n'ont jamais la même teinte. Un hachage, si.
 */
export const REGION_TONES = {
  lin: colors.surfaceAlt, // #EEE7DB
  sable: '#DCD3C4',
  sauge: '#E1EECC',
  terre: colors.primarySoft, // #FFE1D0
} as const;

export const REGION_TONE_BY_CODE: Record<string, keyof typeof REGION_TONES> = {
  '32': 'sauge', // Hauts-de-France
  '11': 'lin', // Île-de-France
  '28': 'sable', // Normandie
  '44': 'sable', // Grand Est
  '27': 'sauge', // Bourgogne-Franche-Comté
  '24': 'terre', // Centre-Val de Loire
  '52': 'sauge', // Pays de la Loire
  '53': 'lin', // Bretagne
  '75': 'sable', // Nouvelle-Aquitaine
  '76': 'sauge', // Occitanie
  '84': 'lin', // Auvergne-Rhône-Alpes
  '93': 'sable', // Provence-Alpes-Côte d'Azur
  '94': 'terre', // Corse
  '01': 'lin', // Guadeloupe
  '02': 'sauge', // Martinique
  '03': 'sable', // Guyane
  '04': 'terre', // La Réunion
  '06': 'sauge', // Mayotte
};

/** Le liseré entre deux aplats jointifs, et l'ombre qui les décolle. */
export const REGION_LINES = {
  seam: colors.surface,
  seamWidth: 1.2,
  /**
   * MapLibre ne sait pas faire d'ombre portée sur un polygone : pas de filtre,
   * pas de mode de fusion. Celle-ci est une SECONDE couche de contour, large,
   * translucide et décalée — c'est le seul moyen, et il suffit.
   */
  shadow: '#B49A76',
  shadowWidth: 6,
  shadowOpacity: 0.35,
  shadowOffset: [1.5, 2.5] as [number, number],
  hover: colors.primaryLight,
  chosen: colors.primary,
  chosenWidth: 2.4,
};

/**
 * L'opacité des aplats selon le zoom : c'est là que tient toute l'identité.
 *
 * Les aplats de régions ne sont pas un décor posé sur la carte, ils sont le
 * VOILE qui la couvre. À l'échelle du pays ils sont presque opaques : on voit
 * la France peinte, pas OpenStreetMap. À l'échelle d'une région ils s'effacent
 * presque : la vraie carte apparaît, avec ses routes et ses villes, au moment
 * précis où on en a besoin.
 *
 * Un seul mécanisme règle donc les deux reproches : « c'est laid quand on
 * dézoome » et « ça ressemble à de l'OSM brut ».
 */
export const REGION_FILL_OPACITY = [
  'interpolate',
  ['linear'],
  ['zoom'],
  4,
  0.96,
  6,
  0.92,
  7.2,
  0.55,
  8.6,
  0.14,
  10,
  0.06,
] as const;

/**
 * Le voile hors de France.
 *
 * Le guide s'arrête à la France, la carte non. Plutôt que de brider la
 * navigation, on décolore ce qui est hors périmètre : un aplat de sable à 72 %
 * couvrant le monde, PERCÉ des contours de la France (métropole + les cinq
 * régions d'outre-mer). C'est un polygone à trous, ce que MapLibre sait faire
 * nativement — l'anneau extérieur est le monde, chaque anneau intérieur une
 * région.
 *
 * Effet de bord voulu : en se déplaçant vers l'Atlantique ou l'océan Indien, on
 * voit apparaître des trous nets dans le voile. C'est ainsi qu'on découvre que
 * la Guadeloupe et Mayotte sont au catalogue sans qu'aucun encart ne le dise.
 */
export const OUT_OF_SCOPE_VEIL = { color: colors.bg, opacity: 0.72 };

export function worldRing(): [number, number][] {
  return [
    [-180, -85],
    [180, -85],
    [180, 85],
    [-180, 85],
    [-180, -85],
  ];
}

/**
 * Repeint un style OpenFreeMap aux couleurs de Roam.
 *
 * On filtre par `source-layer` et par type, jamais par identifiant de couche :
 * les identifiants d'un style tiers changent sans préavis, la liste des
 * `source-layer` d'OpenMapTiles est un schéma stable. Une couche inconnue
 * garde sa peinture d'origine plutôt que de disparaître.
 */
export function repeindre(style: any) {
  const s = JSON.parse(JSON.stringify(style));
  const garde: any[] = [];

  for (const layer of s.layers ?? []) {
    const src = layer['source-layer'] as string | undefined;
    const id = String(layer.id ?? '');

    // Le bavardage : points d'intérêt, écussons de routes, frontières
    // nationales. La carte est un fond ; les lieux de Roam sont le sujet.
    if (src === 'poi' || id.startsWith('poi') || id.includes('shield')) continue;
    if (src === 'boundary' && layer.type === 'line') continue;
    if (src === 'aeroway') continue;

    layer.paint = layer.paint ?? {};

    if (layer.type === 'background') {
      layer.paint['background-color'] = mapColors.earth;
    } else if (src === 'water' || src === 'waterway') {
      if (layer.type === 'fill') {
        layer.paint['fill-color'] = mapColors.water;
        layer.paint['fill-outline-color'] = mapColors.waterDeep;
      } else if (layer.type === 'line') {
        layer.paint['line-color'] = mapColors.waterDeep;
        layer.paint['line-width'] = ['interpolate', ['linear'], ['zoom'], 8, 0.4, 14, 1.6];
      }
    } else if (src === 'landcover' || src === 'park') {
      layer.paint['fill-color'] = mapColors.green;
      layer.paint['fill-opacity'] = 0.55;
    } else if (src === 'landuse') {
      layer.paint['fill-color'] = mapColors.built;
      layer.paint['fill-opacity'] = 0.6;
    } else if (src === 'building') {
      layer.paint['fill-color'] = mapColors.built;
      layer.paint['fill-opacity'] = 0.75;
      delete layer.paint['fill-outline-color'];
    } else if (src === 'transportation') {
      const grande = /motorway|trunk|primary/.test(id);
      layer.paint['line-color'] = grande ? mapColors.road : mapColors.roadMinor;
      // Les routes sont une TEXTURE, pas un réseau : on ne se sert pas de Roam
      // pour conduire. Assez fines pour se lire de loin comme une trame.
      layer.paint['line-width'] = grande
        ? ['interpolate', ['linear'], ['zoom'], 7, 0.5, 12, 2.2, 16, 6]
        : ['interpolate', ['linear'], ['zoom'], 11, 0.4, 16, 3];
    } else if (layer.type === 'symbol') {
      // Étiquettes : seulement les lieux habités, et en brun.
      if (src !== 'place') continue;
      layer.paint['text-color'] = mapColors.labelInk;
      layer.paint['text-halo-color'] = mapColors.labelHalo;
      layer.paint['text-halo-width'] = 1.6;
      layer.layout = { ...(layer.layout ?? {}), 'text-font': ['Noto Sans Regular'] };
    }

    garde.push(layer);
  }

  s.layers = garde;
  return s;
}

/**
 * Style de repli, sans réseau.
 *
 * Les lieux sont les données de Roam ; le fond de carte appartient à un tiers.
 * Repeint aux mêmes couleurs : sans tuiles, la France se dessine quand même —
 * les aplats de régions sont NOS données, et ils ont l'air voulus, pas dégradés.
 */
export const FALLBACK_STYLE = {
  version: 8 as const,
  sources: {},
  layers: [
    {
      id: 'ground',
      type: 'background' as const,
      paint: { 'background-color': mapColors.earth },
    },
  ],
};

/**
 * Résout le premier fond de carte disponible, et le repeint.
 *
 * Le style est chargé ici plutôt que confié à MapLibre : quand MapLibre échoue
 * à le charger, il n'émet jamais `load`, et les couches posées à ce moment-là
 * ne le sont donc jamais.
 */
export async function resolveBasemap(
  timeoutMs = 5000,
): Promise<{ style: unknown; degraded: boolean }> {
  for (const url of BASEMAP_STYLES) {
    try {
      const response = await fetch(url, { signal: AbortSignal.timeout(timeoutMs) });
      if (!response.ok) continue;
      return { style: repeindre(await response.json()), degraded: false };
    } catch {
      // Fond suivant.
    }
  }
  return { style: FALLBACK_STYLE, degraded: true };
}

/**
 * La séquence France → région → retour, en millisecondes.
 *
 * Réglée sur l'artboard, pas devinée. Trois choix qui ne se voient pas mais se
 * sentent :
 *
 * - les autres régions s'effacent PENDANT le vol, pas avant : les faire pâlir
 *   à l'arrêt donne un clignotement, et après l'atterrissage donne un
 *   deuxième temps mort ;
 * - les lieux commencent à apparaître AVANT la fin du zoom (à 520 ms sur 900) :
 *   on atterrit sur une région déjà peuplée, au lieu d'attendre devant un
 *   aplat vide ;
 * - ils arrivent en cascade de 12 ms depuis le centre de la région. Douze
 *   millisecondes ne se comptent pas, mais 272 pastilles apparaissant d'un
 *   coup font un clignotement, et la cascade se lit comme un remplissage.
 */
export const TRANSITION = {
  zoom: 900,
  courbe: [0.22, 0.61, 0.36, 1] as [number, number, number, number],
  autresRegions: { quand: 'pendant' as const, duree: 260 },
  lieux: { delai: 520, cascade: 12, apparition: 220, depuis: 'centre' as const },
  retour: { zoom: 700, lieux: 160 },
  /** Marge autour de la région à l'arrivée, en points. */
  padding: 28,
};
