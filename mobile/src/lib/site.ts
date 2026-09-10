/**
 * Où le site est servi, et comment y trouver ses fichiers voisins.
 *
 * L'application est exportée en un site statique qui peut vivre à la racine
 * d'un domaine — l'aperçu local — ou dans un sous-chemin, comme
 * `https://compte.github.io/roam/`. Un chemin absolu écrit en dur vaut la
 * racine du DOMAINE, jamais celle du site : le worker de MapLibre était donc
 * cherché un cran trop haut, et la carte restait muette sans une erreur pour
 * le dire.
 */

/** Le fichier que MapLibre charge dans son worker. */
export const CHEMIN_DU_WORKER = 'maplibre/maplibre-gl-worker.mjs';

/**
 * La racine du site, déduite de l'adresse du BUNDLE.
 *
 * L'adresse de la PAGE ne suffit pas : ouverte sur une route profonde —
 * `/roam/place/Q243`, ce que rend le repli d'un hébergeur statique — elle
 * ferait chercher les voisins dans `/roam/place/`. Le bundle, lui, est
 * toujours à `<racine>/_expo/static/js/web/…` : ce qui précède `_expo/` EST la
 * racine, quelle que soit la page où l'on se trouve.
 */
export function racineDuSite(sources: readonly string[], repli: string): string {
  const bundle = sources.find((src) => src.includes('/_expo/static/js/'));
  if (!bundle) return repli;
  return bundle.slice(0, bundle.indexOf('/_expo/') + 1);
}

/** L'adresse d'un fichier voisin, à partir des scripts chargés. */
export function voisinDuSite(
  chemin: string,
  sources: readonly string[],
  repli: string,
): string {
  try {
    return new URL(chemin, racineDuSite(sources, repli)).toString();
  } catch {
    return `/${chemin}`;
  }
}
