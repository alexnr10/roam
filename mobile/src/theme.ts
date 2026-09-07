/** Jetons de style. Un seul endroit à toucher pour changer l'identité visuelle. */

export const colors = {
  bg: '#FBFAF7',
  surface: '#FFFFFF',
  surfaceAlt: '#F3F0EA',
  text: '#1A1917',
  muted: '#6F6A62',
  border: '#E7E3DB',
  primary: '#B4532B',
  primarySoft: '#F6E7DE',
  verified: '#2F6F4E',
  locked: '#B8B2A8',
  /** Un niveau, une couleur — reprise partout : carte, listes, badges. */
  tier: ['#B4532B', '#8A7B5C', '#9A958C'] as const,
};

/**
 * Les deux couleurs de la carte de conquête.
 *
 * Or : une collection du territoire est achevée. Terracotta pleine : le
 * territoire l'est entièrement, tous thèmes confondus. La seconde ne s'obtient
 * qu'en passant par la première, et se lit comme un aboutissement.
 */
export const conquest = {
  empty: colors.surfaceAlt,
  started: colors.primarySoft,
  theme: '#C89B3C',
  total: colors.primary,
};

export const spacing = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  xxl: 32,
};

export const radius = { sm: 6, md: 10, lg: 16, pill: 999 };

/**
 * Largeur maximale du contenu, en points.
 *
 * L'application est pensée pour le téléphone, et tout y est dimensionné
 * d'après la largeur de l'écran : la photo d'une fiche fait la largeur moins
 * les marges, une tuile du quadrillage la moitié. Sur un ordinateur, la même
 * règle donnait une photo de dix-huit cents pixels de large — l'écran entier
 * pour une seule image, et six lignes de texte étirées d'un bord à l'autre.
 *
 * Au-delà de cette largeur, le contenu se centre au lieu de s'étirer. Ce n'est
 * pas une version « bureau » : c'est la version téléphone, rendue lisible sur
 * un grand écran.
 *
 * Sept cent vingt et non cinq cent soixante : la borne servait à empêcher une
 * photo de deux mètres, pas à rétrécir le catalogue. À 560, l'écran d'un
 * ordinateur ne montrait que trois vignettes et quatre thèmes — moins qu'un
 * téléphone en paysage, pour un guide dont tout l'objet est d'en montrer
 * beaucoup d'un coup.
 */
export const LARGEUR_MAX = 720;

/** La largeur réellement disponible pour le contenu, marges comprises. */
export function largeurUtile(ecran: number): number {
  return Math.min(ecran, LARGEUR_MAX);
}

/**
 * L'échelle typographique, montée d'un cran.
 *
 * Quinze points de corps et treize de légende passent bien sur un écran
 * d'ordinateur, à cinquante centimètres. Sur un téléphone tenu à bout de bras,
 * dehors, il faut zoomer — et une application de guide se lit debout, à
 * l'arrêt, en cherchant quoi faire.
 *
 * Seize et quatorze sont les tailles que les systèmes eux-mêmes emploient pour
 * une liste. On ne descend en dessous que pour ce qui est vraiment secondaire.
 */
export const type = {
  title: { fontSize: 30, fontWeight: '700' as const, color: colors.text },
  heading: { fontSize: 22, fontWeight: '700' as const, color: colors.text },
  subheading: { fontSize: 17, fontWeight: '600' as const, color: colors.text },
  body: { fontSize: 16, color: colors.text },
  small: { fontSize: 14, color: colors.muted },
  tiny: { fontSize: 12, color: colors.muted, letterSpacing: 0.4 },
};

/**
 * Emoji par thème — provisoire, à remplacer par un jeu d'icônes dessiné.
 *
 * Les vingt-trois thèmes y figurent, et il le faut : l'emoji sert de repli
 * quand un lieu n'a pas de photo ou qu'elle ne charge pas, et dix thèmes sans
 * entrée affichaient un 📍 anonyme — le quadrillage en montrait des grilles
 * entières.
 */
export const themeEmoji: Record<string, string> = {
  chateaux: '🏰',
  abbayes: '⛪',
  cathedrales: '⛪',
  villages: '🏘️',
  sommets: '⛰️',
  cascades: '💧',
  gorges: '🏞️',
  plages: '🌊',
  grottes: '🕳️',
  lacs: '🏔️',
  ponts: '🌉',
  phares: '🗼',
  monuments: '🗿',
  musees: '🖼️',
  maisons: '🏡',
  jardins: '🌷',
  megalithes: '🪨',
  iles: '🏝️',
  volcans: '🌋',
  forets: '🌲',
  cirques: '🗻',
  'dunes-marais': '🏖️',
  rochers: '🧗',
};
