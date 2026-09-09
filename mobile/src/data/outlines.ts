import embarques from './outlines.json';

/**
 * Contours administratifs, pour colorier la carte de conquête — d'UN pays.
 *
 * Ceux du pays de départ sont produits par `roam_pipeline export-outlines` et
 * VERSIONNÉS avec l'application : elle n'a rien à télécharger, et la carte
 * fonctionne hors réseau — y compris quand le serveur de tuiles est
 * injoignable, puisque ces polygones sont nos données et non celles d'un
 * tiers. Ceux des autres pays arrivent avec leur catalogue.
 *
 * Les frontières sont **jointives** : deux départements voisins partagent
 * exactement le même tracé. C'est ce qui évite le liseré de fond entre deux
 * aplats de couleur, et c'est verrouillé par un test du pipeline.
 *
 * Un pays sans contours n'est pas une erreur : `outlinesFor` rend `null`, et
 * la carte de conquête retombe sur la liste — qui dit la même chose sans
 * dessin. C'est ce qui permet d'ouvrir un pays avant d'avoir ses tracés.
 */

export type OutlineCollection = GeoJSON.FeatureCollection<
  GeoJSON.Polygon | GeoJSON.MultiPolygon,
  { code: string; nom: string }
>;

export type Outlines = {
  attribution: string;
  region?: OutlineCollection;
  departement?: OutlineCollection;
};

let outlines = embarques as unknown as Outlines;

/** Mention de source : la Licence ouverte l'exige, la carte doit la porter. */
export const attributionDesContours = (): string => outlines.attribution ?? '';

/**
 * Remplace les contours courants. Sans argument, revient à ceux du pays
 * embarqué — c'est le cas d'un pays qui n'en fournit pas.
 */
export function chargerContours(source?: unknown): void {
  outlines = (source ?? { attribution: '' }) as Outlines;
}

const EMPTY: OutlineCollection = { type: 'FeatureCollection', features: [] };

/**
 * Contours d'une échelle, ou `null` si elle n'en a pas.
 *
 * Les communes n'en ont pas encore et le pays n'en a pas besoin — la carte
 * retombe alors sur la liste, qui dit la même chose sans dessin.
 */
export function outlinesFor(level: string): OutlineCollection | null {
  const found = level === 'region' ? outlines.region : level === 'departement' ? outlines.departement : null;
  return found && found.features.length > 0 ? found : null;
}

/**
 * Les échelles dessinables, CALCULÉES à chaque appel.
 *
 * C'était une constante, figée au chargement du module : elle serait restée
 * celle du pays de départ après une bascule, et la carte de conquête aurait
 * proposé de colorier des départements qui n'existent pas.
 */
export const niveauxDessinables = (): ('region' | 'departement')[] =>
  (['region', 'departement'] as const).filter((level) => outlinesFor(level) !== null);

export { EMPTY as EMPTY_OUTLINES };
