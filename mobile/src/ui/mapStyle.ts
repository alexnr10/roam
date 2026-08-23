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
export const BASEMAP_STYLE = 'https://tiles.openfreemap.org/styles/positron';

/** Vue initiale : la France entière. */
export const FRANCE_VIEW = { longitude: 2.4, latitude: 46.6, zoom: 4.6 };

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
