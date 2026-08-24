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

export const type = {
  title: { fontSize: 28, fontWeight: '700' as const, color: colors.text },
  heading: { fontSize: 20, fontWeight: '700' as const, color: colors.text },
  subheading: { fontSize: 16, fontWeight: '600' as const, color: colors.text },
  body: { fontSize: 15, color: colors.text },
  small: { fontSize: 13, color: colors.muted },
  tiny: { fontSize: 11, color: colors.muted, letterSpacing: 0.4 },
};

/** Emoji par thème — provisoire, à remplacer par un jeu d'icônes dessiné. */
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
};
