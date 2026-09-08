/** Jetons de style. Un seul endroit à toucher pour changer l'identité visuelle. */

/**
 * Une seule identité, claire et chaude.
 *
 * Pas de mode sombre en v1, et ce n'est pas une économie : c'est une décision.
 * Roam se lit debout, dehors, en plein soleil — la condition où un fond sombre
 * perd le plus (reflets, contraste écrasé, luminosité poussée à fond). Et les
 * deux mille photos du catalogue sont des pierres claires, des tuiles, du
 * calcaire, du sable : posées sur du sable, elles se prolongent ; posées sur du
 * noir, elles deviennent vingt-trois vignettes qui brillent dans le vide.
 *
 * Le fond n'est pas blanc pour autant. `bg` est un sable, pas un papier : c'est
 * la même famille que la carte, et c'est ce qui fait qu'une carte claire et une
 * app claire ne se contentent pas de coexister — elles sont la même surface.
 *
 * Un mode sombre reste possible plus tard : il ne demande que de remplacer les
 * onze valeurs de `colors` et les huit de `mapColors`. Rien d'autre du code ne
 * connaît une couleur.
 */
export const colors = {
  /** Sable. Le fond de l'application ET la terre de la carte. */
  bg: '#F5EAD8',
  /** Lin. Cartes, vignettes, barre de recherche — ce qui flotte au-dessus. */
  surface: '#F9F4ED',
  surfaceAlt: '#EEE7DB',
  text: '#201E1D',
  muted: '#645C50',
  border: '#DCD7C4',

  /**
   * Terre cuite profonde. C'est la couleur de l'ENCRE d'accent, pas du dessin.
   *
   * La terre cuite claire (`primaryLight`) ne tient pas 4,5:1 sur le sable :
   * en texte de seize points elle passe à 3:1, et l'app se lit au soleil. Le
   * cran plus foncé donne 5,8:1, et du blanc dessus 6,9:1 — donc bouton plein,
   * libellé, lien, chiffre : toujours celui-ci.
   */
  primary: '#8C491A',
  /**
   * Terre cuite pleine. Pour ce qui n'est pas du texte : pastilles de la carte,
   * aplat de la région ouverte, jauges, tampons.
   */
  primaryLight: '#C67139',
  primarySoft: '#FFE1D0',

  /** Sauge profonde : la seconde voix. Visite vérifiée, nature, confirmation. */
  verified: '#56633F',
  locked: '#C0B6A5',

  /**
   * Un niveau, une couleur — reprise partout : carte, listes, badges.
   *
   * Terre cuite, sauge, neutre : le niveau 1 porte l'accent de la marque, le
   * niveau 3 s'efface. Trois valeurs distinctes en noir et blanc aussi, donc
   * lisibles pour un daltonien.
   */
  tier: ['#8C491A', '#728157', '#82796A'] as const,
};

/**
 * Les deux couleurs de la carte de conquête.
 *
 * Or : une collection du territoire est achevée. Terre cuite pleine : le
 * territoire l'est entièrement, tous thèmes confondus. La seconde ne s'obtient
 * qu'en passant par la première, et se lit comme un aboutissement.
 */
export const conquest = {
  empty: colors.surfaceAlt,
  started: colors.primarySoft,
  theme: '#C89B3C',
  total: colors.primary,
};

/**
 * Les couleurs de la conquête, mais pour l'ENCRE et le trait.
 *
 * `conquest` donne des couleurs d'APLAT : posées sur une carte, sous un liseré,
 * elles disent la progression sans crier. Les reprendre pour un pourcentage et
 * pour une jauge était une erreur de nature — la terre cuite pâle tient 1,04:1
 * sur le sable, c'est-à-dire rien du tout : le chiffre était invisible et la
 * jauge semblait vide même à moitié pleine.
 *
 * Une couleur de remplissage n'est pas une couleur d'écriture. Deux jeux :
 * `conquestInk` pour ce qui se lit (au-dessus de 4,5:1), `conquestTrait` pour
 * ce qui se voit — pastilles et jauges, où le contraste de forme suffit.
 */
export const conquestInk = {
  empty: colors.muted,
  started: colors.primary,
  /** L'or d'un thème achevé, assez foncé pour être lu : 4,99:1 sur le sable. */
  theme: '#7E5F16',
  total: colors.primary,
};

export const conquestTrait = {
  empty: colors.surfaceAlt,
  started: colors.primaryLight,
  theme: conquest.theme,
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

/** Tout est arrondi. `pill` pour ce qui se touche, `lg` pour ce qui contient. */
export const radius = { sm: 8, md: 12, lg: 20, xl: 28, pill: 999 };

/**
 * Les polices.
 *
 * Aucune police externe : l'aperçu web est un seul fichier HTML inliné, et un
 * @font-face distant y ajouterait une dépendance réseau pour un gain
 * d'apparence. Donc les polices du système — mais pas la même pour tout.
 *
 * Un serif pour les titres : c'est ce qui sépare un guide de voyage d'un
 * tableau de bord, et Georgia (ou New York sur iOS, Noto Serif sur Android)
 * est présente partout sans rien télécharger. Le corps reste la police
 * d'interface du système, qui est ce qu'on lit le mieux en petit.
 *
 * Note : la police d'affichage du design system (Caprasimo) est inutilisable
 * ici — elle n'existe sur aucun système et devrait être téléchargée. Le serif
 * système en tient le rôle : même intention, coût réseau nul.
 */
export const fonts = {
  display: 'Georgia, "Iowan Old Style", "Palatino", "Times New Roman", serif',
  body: 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif',
};

/**
 * Largeur maximale du contenu, en points.
 *
 * Au-delà, le contenu se centre au lieu de s'étirer. Ce n'est pas une version
 * « bureau » : c'est la version téléphone, rendue lisible sur un grand écran.
 */
export const LARGEUR_MAX = 720;

/** La largeur réellement disponible pour le contenu, marges comprises. */
export function largeurUtile(ecran: number): number {
  return Math.min(ecran, LARGEUR_MAX);
}

/**
 * L'échelle typographique.
 *
 * Seize et quatorze sont les tailles que les systèmes eux-mêmes emploient pour
 * une liste. On ne descend en dessous que pour ce qui est vraiment secondaire.
 *
 * `title` et `heading` passent au serif : ce sont les deux seuls endroits où la
 * voix de la marque parle. Un sous-titre en serif, et l'écran devient un
 * magazine ; un corps de texte en serif, et il devient illisible en petit.
 */
export const type = {
  title: { fontSize: 30, fontFamily: fonts.display, fontWeight: '400' as const, color: colors.text, letterSpacing: -0.2 },
  heading: { fontSize: 22, fontFamily: fonts.display, fontWeight: '400' as const, color: colors.text },
  subheading: { fontSize: 17, fontFamily: fonts.body, fontWeight: '600' as const, color: colors.text },
  body: { fontSize: 16, fontFamily: fonts.body, color: colors.text },
  small: { fontSize: 14, fontFamily: fonts.body, color: colors.muted },
  tiny: { fontSize: 12, fontFamily: fonts.body, color: colors.muted, letterSpacing: 0.4 },
  /** Sur-titre : petites capitales espacées. Sert de kicker, jamais de corps. */
  kicker: {
    fontSize: 12,
    fontFamily: fonts.body,
    fontWeight: '700' as const,
    letterSpacing: 1.1,
    textTransform: 'uppercase' as const,
    color: colors.primary,
  },
};

/**
 * Les ombres.
 *
 * Ce qui flotte au-dessus de la carte a besoin d'un décollement, mais chaud :
 * une ombre grise sur du sable donne une tache sale. Celle-ci est une terre
 * d'ombre très diluée.
 */
export const elevation = {
  flottant: {
    shadowColor: '#3D2A18',
    shadowOpacity: 0.14,
    shadowRadius: 14,
    shadowOffset: { width: 0, height: 4 },
    elevation: 5,
  },
  pose: {
    shadowColor: '#3D2A18',
    shadowOpacity: 0.07,
    shadowRadius: 6,
    shadowOffset: { width: 0, height: 2 },
    elevation: 2,
  },
};

/**
 * Emoji par thème — repli, plus l'illustration principale.
 *
 * Les icônes dessinées (`themeIcons.tsx`) remplacent l'emoji dans l'interface :
 * pastilles de thème, pastilles de carte, repli d'une photo manquante. L'emoji
 * reste ici comme dernier filet, et parce qu'il ne coûte rien.
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
