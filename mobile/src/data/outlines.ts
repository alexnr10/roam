import raw from './outlines.json';

/**
 * Contours administratifs, pour colorier la carte de conquête.
 *
 * Produits par `roam_pipeline export-outlines` et versionnés : l'application
 * n'a rien à télécharger, et la carte fonctionne hors réseau — y compris quand
 * le serveur de tuiles est injoignable, puisque ces polygones sont nos données
 * et non celles d'un tiers.
 *
 * Les frontières sont **jointives** : deux départements voisins partagent
 * exactement le même tracé. C'est ce qui évite le liseré de fond entre deux
 * aplats de couleur, et c'est verrouillé par un test du pipeline.
 */

export type OutlineCollection = GeoJSON.FeatureCollection<
  GeoJSON.Polygon | GeoJSON.MultiPolygon,
  { code: string; nom: string }
>;

type Outlines = {
  attribution: string;
  region?: OutlineCollection;
  departement?: OutlineCollection;
};

const outlines = raw as unknown as Outlines;

/** Mention de source : la Licence ouverte l'exige, la carte doit la porter. */
export const OUTLINE_ATTRIBUTION = outlines.attribution;

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

export const OUTLINE_LEVELS = (['region', 'departement'] as const).filter(
  (level) => outlinesFor(level) !== null,
);

export { EMPTY as EMPTY_OUTLINES };
