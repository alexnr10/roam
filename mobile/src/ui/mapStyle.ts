import { colors } from '../theme';

/**
 * Fond de carte.
 *
 * OpenFreeMap sert des tuiles vectorielles complètes de la planète, sans clé ni
 * compte — c'est ce qui permet à Roam d'avoir une vraie carte sans compte Google
 * ni carte bancaire, sur le web comme sur téléphone.
 *
 * Le style « positron » est délibérément pâle et sans bavardage : pas de
 * couleurs vives, peu d'étiquettes. C'est ce qu'on veut ici — la carte est un
 * fond, les lieux sont le sujet. Un fond de carte expressif entrerait en
 * concurrence avec les pastilles au lieu de les mettre en valeur.
 */
export const BASEMAP_STYLES = [
  'https://tiles.openfreemap.org/styles/positron',
  'https://tiles.openfreemap.org/styles/liberty',
  // Dernier recours : les tuiles de démonstration de MapLibre. Rudimentaires,
  // mais elles ne dépendent d'aucun tiers.
  'https://demotiles.maplibre.org/style.json',
];

/**
 * Emprise de la France métropolitaine.
 *
 * La vue initiale s'y cale plutôt que sur un niveau de zoom fixe : le cadrage
 * s'adapte alors à la taille du cadre, d'un téléphone étroit à un écran large,
 * là où un zoom en dur laissait déborder la Bretagne et la Corse.
 */
export const FRANCE_BOUNDS: [[number, number], [number, number]] = [
  [-5.2, 41.3],
  [9.6, 51.2],
];

/** Au-delà, on montre les lieux un par un plutôt que des paquets. */
export const CLUSTER_MAX_ZOOM = 10;

export const mapColors = {
  visited: colors.verified,
  todo: colors.primary,
  cluster: '#8A7B5C',
  clusterText: '#FFFFFF',
  halo: '#FFFFFF',
  water: '#DDE6EC',
  ground: colors.surfaceAlt,
};


/**
 * Style de repli, sans réseau.
 *
 * Les lieux sont les données de Roam ; le fond de carte appartient à un tiers.
 * Une panne du second ne doit jamais faire disparaître les premières — d'où ce
 * style minimal, qui donne au moins un sol sur lequel poser les pastilles.
 */
export const FALLBACK_STYLE = {
  version: 8 as const,
  sources: {},
  layers: [
    {
      id: 'ground',
      type: 'background' as const,
      paint: { 'background-color': mapColors.ground },
    },
  ],
};
