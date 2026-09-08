import { TRACES } from './themeIcons';

/**
 * Les icônes de thèmes, transformées en images pour la carte.
 *
 * MapLibre ne sait pas dessiner un composant React : une couche de symboles
 * réclame des images enregistrées auprès de la carte. On repasse donc les mêmes
 * tracés — ceux des pastilles de filtre — sur un canevas, une fois au
 * chargement, et la carte les pioche par leur nom.
 *
 * Dessinés à la main sur le canevas plutôt que chargés depuis un SVG : un
 * `Path2D` accepte tel quel le `d` d'un chemin SVG, et cela évite d'attendre le
 * chargement de vingt-trois images avant de pouvoir poser une couche.
 */

/** Le nom d'une image dans la carte. */
export const nomDuGlyphe = (themeId: string) => `theme-${themeId}`;

/** Le côté du canevas, en pixels logiques. Le tracé vient d'une grille de 24. */
const COTE = 22;

/**
 * Le glyphe d'un thème, en pixels.
 *
 * Rendu au double de la taille demandée : une icône dessinée à sa taille
 * logique arrive floue sur un écran qui a deux pixels par point, et c'est
 * précisément le défaut qu'on a passé une session à corriger sur les photos.
 */
function dessiner(
  themeId: string,
  couleur: string,
  densite: number,
): { width: number; height: number; data: Uint8ClampedArray } | null {
  const traces = TRACES[themeId];
  if (!traces || typeof document === 'undefined') return null;

  const cote = Math.round(COTE * densite);
  const canevas = document.createElement('canvas');
  canevas.width = cote;
  canevas.height = cote;
  const ctx = canevas.getContext('2d');
  if (!ctx) return null;

  // La grille de 24 des icônes, ramenée au canevas.
  ctx.scale(cote / 24, cote / 24);
  ctx.strokeStyle = couleur;
  ctx.lineWidth = 2.4;
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';
  for (const trace of traces) ctx.stroke(new Path2D(trace));

  return ctx.getImageData(0, 0, cote, cote);
}

/**
 * Enregistre les vingt-trois glyphes auprès de la carte.
 *
 * En clair sur la pastille colorée : c'est le dessin des cartes depuis
 * toujours — un disque qui porte la couleur, un symbole qui porte le sens. Les
 * deux ne se disputent pas la même variable.
 */
export function poserLesGlyphes(
  // Le type de MapLibre, réduit à ce qu'on emploie : le module n'est pas
  // importé ici pour que ce fichier reste testable sans moteur de carte.
  carte: {
    hasImage: (nom: string) => boolean;
    addImage: (nom: string, image: any, options?: any) => unknown;
  },
  couleur: string,
  densite = 2,
): number {
  let poses = 0;
  for (const themeId of Object.keys(TRACES)) {
    const nom = nomDuGlyphe(themeId);
    if (carte.hasImage(nom)) continue;
    const image = dessiner(themeId, couleur, densite);
    if (!image) continue;
    carte.addImage(nom, image, { pixelRatio: densite });
    poses += 1;
  }
  return poses;
}
