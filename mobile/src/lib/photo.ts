/**
 * L'adresse d'une photo Commons, à la taille qu'on affiche.
 *
 * Le catalogue embarque l'adresse NUE du fichier : `Special:FilePath` accepte
 * un paramètre `width`, et c'est à l'affichage de le choisir. Un catalogue qui
 * n'embarque qu'une seule taille fait télécharger deux mille images de huit
 * cents pixels pour en montrer des carrés de cinquante-six — sur un forfait
 * mobile, dans une gorge de l'Ardèche.
 *
 * Deux précautions, chacune tirée d'un vrai défaut :
 *
 * 1. **HTTPS.** Wikidata donne l'adresse en `http://`. Servie depuis une page
 *    en HTTPS — la prévisualisation publiée l'est — c'est du contenu mixte :
 *    le navigateur la remonte parfois, la refuse parfois, et l'image manque
 *    sans rien dire. On force le schéma ici aussi, pour qu'un catalogue plus
 *    ancien reste affichable.
 * 2. **Des paliers, pas la taille exacte.** Chaque largeur demandée est une
 *    image que Commons doit fabriquer et garder. Trois paliers partagés par
 *    tous les appareils valent mieux que deux cents tailles calculées sur la
 *    densité de chaque écran : la vignette est déjà en cache quand elle
 *    arrive.
 */

/** Les seules largeurs que l'application demande. */
export const PALIERS = [200, 400, 800, 1200] as const;

/** Le plus petit palier qui couvre cette largeur. Au-delà, le plus grand. */
export function palier(largeur: number): number {
  return PALIERS.find((p) => p >= largeur) ?? PALIERS[PALIERS.length - 1];
}

/**
 * La DENSITÉ au-delà de laquelle on ne demande plus mieux.
 *
 * Un téléphone récent affiche entre deux et quatre pixels physiques par point.
 * Demander une image à la taille en POINTS la fait donc agrandir d'autant à
 * l'affichage, et une photo de quatre cents pixels étirée sur mille est floue —
 * exactement ce qu'on ne peut pas se permettre dans une application qui vend
 * des images.
 *
 * Deux suffisent : au-delà, l'œil ne distingue plus grand-chose et chaque
 * palier double le poids téléchargé, sur un forfait mobile, au bord d'une
 * route.
 */
export const DENSITE_MAX = 2;

export function photoUrl(
  imageUrl: string | null | undefined,
  largeur: number,
  densite = 1,
): string | null {
  if (!imageUrl) return null;
  const sur = imageUrl.replace(/^http:\/\//, 'https://');
  const separateur = sur.includes('?') ? '&' : '?';
  const pixels = largeur * Math.min(Math.max(densite, 1), DENSITE_MAX);
  return `${sur}${separateur}width=${palier(pixels)}`;
}
