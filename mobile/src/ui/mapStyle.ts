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
  /**
   * Les routes.
   *
   * Le parti pris d'origine — « une texture, pas un réseau » — était juste sur
   * le principe et faux sur les valeurs : au sable de la bordure, sur du sable,
   * elles ne se voyaient pas du tout. Une région ouverte devenait alors un
   * aplat vide où l'on ne pouvait pas se situer, et c'est raté pour un guide :
   * on y cherche « quoi faire par ici », donc il faut d'abord savoir où est ici.
   *
   * Deux crans plus foncées, elles se lisent sans devenir une carte routière —
   * les grands axes portent la structure, les secondaires restent une trame.
   */
  road: '#C4B49A',
  roadMinor: '#DCD3C4',
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
/**
 * Le zoom à partir duquel une région s'ouvre.
 *
 * `regionOuverte` est dérivé du zoom autant que du clic : la région ouverte est
 * celle qui REMPLIT l'écran. Le clic n'est qu'un raccourci vers cet état, et
 * dézoomer referme — c'est le geste que tout le monde tente en premier.
 *
 * Sept virgule deux, et pas huit : c'est le zoom auquel une région moyenne
 * cesse d'entrer entière dans le cadre, donc celui où l'on a cessé de regarder
 * la France pour regarder un endroit.
 */
/**
 * Le voile de la région OUVERTE.
 *
 * « En ouvrant une région, ce même voile tombe à 0,14 : la vraie carte apparaît,
 * avec ses routes et ses villes, au moment exact où on en a besoin. » Ce n'est
 * donc pas le zoom seul qui le fait tomber — une grande région cadrée sur un
 * téléphone s'arrête vers 6,6, et son aplat serait encore à demi opaque.
 */
export const OPACITE_REGION_OUVERTE = 0.14;

/**
 * Ce qu'il reste des autres régions quand une région est ouverte.
 *
 * Pas zéro : elles disent encore où l'on est dans le pays, et la frontière de
 * la région ouverte n'a de sens que s'il y a quelque chose de l'autre côté.
 */
export const ATTENUATION_AUTRES = 0.55;

/**
 * Le zoom en dessous duquel aucune région ne s'ouvre.
 *
 * L'ouverture se décide sur la place que la région prend à l'écran, pas sur un
 * palier de zoom : voir `remplitLEcran`. Ce plancher n'est là que pour empêcher
 * une région d'occuper « la moitié du cadre » à l'échelle du globe.
 */
export const SEUIL_REGION = 4.5;

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
    // Les bâtiments en relief appartiennent à une carte qu'on parcourt en
    // ville, pas à un fond de guide. Et on ne saurait pas les repeindre : leurs
    // propriétés n'ont rien à voir avec celles d'un aplat.
    if (layer.type === 'fill-extrusion') continue;

    layer.paint = layer.paint ?? {};

    // On distingue le TYPE avant la couche de données.
    //
    // Poser `line-color` sur une couche de symboles, ou `fill-color` sur une
    // couche de lignes, produit un style que MapLibre REFUSE EN ENTIER : il
    // signale l'erreur par un événement et n'émet jamais `load`. Aucune de nos
    // couches n'est alors posée, et la carte reste un rectangle vide.
    //
    // Un style tiers mélange les types sur une même couche de données —
    // `transportation` porte les tracés ET les flèches de sens unique. Ne
    // filtrer que par `source-layer` suffisait donc à tout effacer.
    switch (layer.type) {
      case 'background':
        layer.paint['background-color'] = mapColors.earth;
        break;

      case 'fill':
        if (src === 'water' || src === 'waterway') {
          layer.paint['fill-color'] = mapColors.water;
          layer.paint['fill-outline-color'] = mapColors.waterDeep;
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
        }
        break;

      case 'line':
        if (src === 'water' || src === 'waterway') {
          layer.paint['line-color'] = mapColors.waterDeep;
          layer.paint['line-width'] = ['interpolate', ['linear'], ['zoom'], 8, 0.4, 14, 1.6];
        } else if (src === 'transportation') {
          const grande = /motorway|trunk|primary/.test(id);
          layer.paint['line-color'] = grande ? mapColors.road : mapColors.roadMinor;
          // Les routes sont une TEXTURE, pas un réseau : on ne se sert pas de
          // Roam pour conduire. Assez fines pour se lire comme une trame.
          // Visibles dès le zoom d'arrivée d'une région, vers 6,5 : c'est là
          // qu'on regarde, et c'est là qu'elles étaient absentes.
          layer.paint['line-width'] = grande
            ? ['interpolate', ['linear'], ['zoom'], 6, 0.8, 9, 1.8, 12, 3.4, 16, 8]
            : ['interpolate', ['linear'], ['zoom'], 8, 0.5, 12, 1.4, 16, 4.5];
        } else if (src === 'building') {
          layer.paint['line-color'] = mapColors.built;
        }
        break;

      case 'symbol':
        // Seuls les lieux habités gardent la parole, et en brun.
        if (src !== 'place') continue;
        layer.paint['text-color'] = mapColors.labelInk;
        layer.paint['text-halo-color'] = mapColors.labelHalo;
        layer.paint['text-halo-width'] = 1.6;
        // La police n'est PAS imposée : un nom de fonte absent du jeu de
        // glyphes du style ferait disparaître les étiquettes qu'on vient de
        // colorer. Celle du style d'origine est forcément servie.
        break;

      default:
        // Type inconnu : on garde la couche telle quelle plutôt que de la
        // faire disparaître. Le style d'un tiers peut en introduire.
        break;
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
  depouille = false,
): Promise<{ style: unknown; degraded: boolean }> {
  for (const url of BASEMAP_STYLES) {
    try {
      const response = await fetch(url, { signal: AbortSignal.timeout(timeoutMs) });
      if (!response.ok) continue;
      const repeint = repeindre(await response.json());
      return { style: depouille ? depouiller(repeint) : repeint, degraded: false };
    } catch {
      // Fond suivant.
    }
  }
  return { style: FALLBACK_STYLE, degraded: true };
}

/**
 * Le fond réduit à la terre et à l'eau.
 *
 * La carte de conquête n'est pas une carte où l'on va : c'est un tableau de
 * progression, où chaque territoire est un aplat qu'on colorie. Les routes vues
 * à travers un aplat à quarante-cinq pour cent deviennent des traits qui ne
 * disent rien — ni une ville, ni une frontière, ni un chemin : du bruit.
 *
 * Restent le sol et l'eau : ils donnent une côte et une mer, donc de quoi
 * reconnaître la France. Tout le reste, y compris les noms de lieux, appartient
 * à la carte où l'on cherche quoi faire.
 */
export function depouiller(style: any) {
  const s = JSON.parse(JSON.stringify(style));
  s.layers = (s.layers ?? []).filter((layer: any) => {
    if (layer.type === 'background') return true;
    const src = layer['source-layer'];
    return (src === 'water' || src === 'waterway') && layer.type !== 'symbol';
  });
  return s;
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
  lieux: {
    delai: 520,
    cascade: 12,
    apparition: 220,
    depuis: 'centre' as const,
    /**
     * Durée totale maximale de la cascade, en millisecondes.
     *
     * Douze millisecondes par pastille ne se comptent pas — sur huit lieux à
     * Mayotte. Sur les deux cent soixante-douze de l'Occitanie, elles font
     * trois secondes et quart : ce n'est plus un remplissage, c'est une
     * attente. Le pas se resserre donc quand il y a foule, et l'effet reste le
     * même : un balayage depuis le centre.
     */
    etalement: 600,
  },
  retour: { zoom: 700, lieux: 160 },
  /** Marge autour de la région à l'arrivée, en points. */
  padding: 28,
};

/**
 * La couleur d'une pastille, selon sa note.
 *
 * Trois tons de la même famille, du plus foncé au plus effacé. La FORME dit
 * déjà la catégorie — le symbole du thème est posé dessus — donc la couleur n'a
 * qu'une chose à dire, et elle la dit seule.
 */
export const ETOILE_COULEURS = {
  3: colors.primary,
  2: colors.primaryLight,
  1: '#A2907A',
} as const;

/**
 * Le rayon d'une pastille.
 *
 * Les deux premières notes portent le symbole de leur thème : il leur faut un
 * disque assez large pour l'accueillir. La troisième reste un point — mille
 * deux cent soixante-neuf lieux à une étoile, tous porteurs d'un symbole,
 * feraient une carte illisible là où on cherche justement à voir clair.
 */
export function rayonDesPastilles(): unknown[] {
  const parNote = (petit: number, moyen: number, grand: number) => [
    'match',
    ['get', 'tier'],
    1,
    grand,
    2,
    moyen,
    petit,
  ];
  return [
    'interpolate',
    ['linear'],
    ['zoom'],
    6,
    parNote(3, 5.5, 9),
    9,
    parNote(3.6, 6.5, 11.5),
    13,
    parNote(4.5, 7.5, 13.5),
  ];
}

/**
 * La taille du symbole posé sur la pastille.
 *
 * Seule la première note en porte un. Ce n'est pas une économie de place :
 * le symbole devient alors une DISTINCTION — il ne dit pas seulement de quoi
 * il s'agit, il dit que ce lieu-là vaut le voyage. Cent deux symboles dans une
 * région en faisaient un fond d'écran.
 */
export function tailleDesGlyphes(): unknown[] {
  return ['interpolate', ['linear'], ['zoom'], 6, 0.55, 9, 0.68, 13, 0.78];
}

/**
 * L'effacement des tracés administratifs quand on approche.
 *
 * Nos contours sont simplifiés — il le faut, les tracés bruts de l'IGN pèsent
 * plusieurs mégaoctets. À l'échelle d'une région, la simplification ne se voit
 * pas. À l'échelle d'une île, si : notre trait passe à côté de la vraie côte
 * que les tuiles dessinent juste en dessous, et les deux se contredisent à
 * l'écran.
 *
 * Plutôt que d'alourdir le fichier pour un détail qu'on ne regarde qu'une fois
 * zoomé, on retire le trait au moment où il devient faux. Il n'a d'ailleurs
 * plus rien à dire là : une fois dans une région, sa frontière n'est plus une
 * information, c'est un souvenir.
 */
export function opaciteDesTraits(maximum = 1): unknown[] {
  return ['interpolate', ['linear'], ['zoom'], 8.2, maximum, 10.5, 0];
}

/** L'expression qui donne son sable à chaque région. Un coloriage, pas un hachage. */
export function tonsDesRegions(): unknown[] {
  const cas: unknown[] = ['match', ['get', 'code']];
  for (const [code, ton] of Object.entries(REGION_TONE_BY_CODE)) {
    cas.push(code, REGION_TONES[ton]);
  }
  cas.push(REGION_TONES.lin);
  return cas;
}

/**
 * L'opacité des aplats, survol compris.
 *
 * `["zoom"]` n'a le droit d'apparaître qu'en ENTRÉE d'un `interpolate` ou d'un
 * `step` de premier niveau. Glisser l'interpolation dans une branche de `case`
 * — pour traiter le survol — produit une couche que MapLibre refuse, et il la
 * refuse par un événement `error`, pas par une exception : la couche manque, et
 * rien ne le dit. Les aplats étaient absents, donc invisibles et inclicables.
 *
 * On inverse donc l'imbrication : l'interpolation reste au sommet, et c'est
 * chacune de ses sorties qui porte le cas du survol.
 */
export function opaciteDesAplats(attenuation = 1): unknown[] {
  const survol = (valeur: number) => [
    'case',
    // La région ouverte d'abord : son voile tombe quel que soit le zoom.
    ['boolean', ['feature-state', 'ouverte'], false],
    OPACITE_REGION_OUVERTE,
    ['boolean', ['feature-state', 'hover'], false],
    0.85,
    // Les AUTRES régions, celles qu'on quitte : elles s'effacent pendant le
    // vol. Les faire pâlir à l'arrêt donnerait un clignotement, et après
    // l'atterrissage un deuxième temps mort.
    valeur * attenuation,
  ];
  const stops = REGION_FILL_OPACITY.slice(3) as number[];
  const sortie: unknown[] = ['interpolate', ['linear'], ['zoom']];
  for (let i = 0; i < stops.length; i += 2) {
    sortie.push(stops[i], survol(stops[i + 1]));
  }
  return sortie;
}

/** L'opacité d'une pastille au repos : le niveau 3 s'efface un peu. */
export const OPACITE_PLEINE = ['match', ['get', 'tier'], 3, 0.8, 1];

/**
 * Le pas de la cascade, resserré quand il y a foule.
 *
 * Douze millisecondes par pastille ne se comptent pas — sur les huit lieux de
 * Mayotte. Sur les deux cent soixante-douze de l'Occitanie, elles feraient
 * trois secondes et quart : ce n'est plus un remplissage, c'est une attente.
 */
export function pasDeCascade(combien: number): number {
  const { cascade, etalement } = TRANSITION.lieux;
  if (combien <= 1) return 0;
  return Math.min(cascade, etalement / (combien - 1));
}

/**
 * L'opacité des pastilles à un instant de la cascade.
 *
 * `front` est le temps écoulé depuis la première pastille. Chaque point a son
 * propre départ — son rang multiplié par le pas — et fond en `apparition`
 * millisecondes. Une seule propriété de peinture à réécrire par image, quel
 * que soit le nombre de lieux.
 */
export function opaciteEnCascade(front: number, pas: number): unknown {
  return [
    '*',
    OPACITE_PLEINE,
    [
      'min',
      1,
      [
        'max',
        0,
        [
          '/',
          ['-', front, ['*', ['get', 'rang'], pas]],
          TRANSITION.lieux.apparition,
        ],
      ],
    ],
  ];
}
