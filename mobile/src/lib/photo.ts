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

/**
 * Comment l'application se nomme auprès de Wikimedia.
 *
 * Wikimedia REFUSE — 403, sans un mot d'explication — les clients qui ne se
 * présentent pas. Sa politique d'agent utilisateur demande un nom, une version
 * et un moyen de contact, et elle vaut pour tout ce qui télécharge, images
 * comprises. Un navigateur en a un ; le téléchargeur d'images d'Android
 * n'envoie que celui de sa bibliothèque, et Commons le rejette.
 *
 * D'où des vignettes absentes sur le téléphone alors que le web les montrait,
 * et un repli qui donnait à un lieu photographié l'apparence d'un lieu sans
 * photo. Se nommer n'est pas un contournement : c'est ce que la politique
 * demande, et c'est le prix d'un service qui ne facture rien.
 *
 * @see https://foundation.wikimedia.org/wiki/Policy:User-Agent_policy
 */
export const VERSION = '0.1.0';
export const CONTACT = 'https://github.com/alexnr10/roam';
export const AGENT = `Roam/${VERSION} (${CONTACT})`;

/** Les en-têtes de toute requête vers Commons. */
export const ENTETES: Record<string, string> = { 'User-Agent': AGENT };

/** Ce qu'on passe à `<Image source>` : un objet, ou un tableau d'un seul. */
export type SourcePhoto =
  | { uri: string; headers: Record<string, string> }
  | [{ uri: string; headers: Record<string, string> }];

/**
 * La source d'une photo, dans la forme que la plateforme sait lire.
 *
 * `<Image source={{ uri, headers }} />` PERD les en-têtes sur Android. Dans
 * `Image.android.js` de React Native, ils ne sont extraits que si la source est
 * un TABLEAU : la branche qui traite un objet simple ne garde que `uri`,
 * `width` et `height`, et rien ne signale ce qu'elle laisse tomber. Nos
 * requêtes partaient donc sous l'agent d'OkHttp, que Wikimedia refuse — et
 * `curl` l'a montré : notre agent obtient 200, `okhttp/4.12.0` obtient 403,
 * sur la même adresse.
 *
 * Un tableau d'un seul élément suffit à les faire passer. Mais il ne peut pas
 * être la forme universelle : `react-native-web` ne résout que l'objet — il
 * teste `!Array.isArray(source)` — et un tableau y donnerait une image sans
 * adresse. iOS, lui, lit les en-têtes dans l'objet. C'est donc bien une
 * particularité d'Android, et elle est traitée comme telle.
 */
export function sourceDeLaPhoto(uri: string, android: boolean): SourcePhoto {
  const source = { uri, headers: ENTETES };
  return android ? [source] : source;
}

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
