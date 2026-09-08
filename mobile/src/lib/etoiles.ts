import { collections } from '../data/catalog';

/**
 * Les étoiles : la valeur d'un lieu, dans sa catégorie, à l'échelle du pays.
 *
 * Roam n'avait jusqu'ici que des NIVEAUX, et un niveau est relatif à une
 * collection : le même château est premier de son département et anonyme à
 * l'échelle de la France. C'est juste pour ranger une collection, illisible sur
 * une fiche — « niveau 2 » ne dit rien à qui n'a pas le barème en tête.
 *
 * Trois étoiles disent quelque chose à tout le monde, et le point de comparaison
 * qui a un sens est la catégorie : on compare un château à des châteaux, une
 * cascade à des cascades. Une cascade ne peut pas « perdre » contre Versailles.
 *
 * ## D'où vient le classement
 *
 * De la collection nationale du thème — « Châteaux », « Cascades » — et non du
 * score brut. La différence n'est pas théorique : la Porte d'Aval, à Étretat,
 * est onzième sur quatorze par le score et niveau 1 dans la collection. C'est la
 * relecture à la main qui l'a mise là, et c'est exactement ce qu'une note doit
 * porter. Le score seul lui aurait donné une étoile.
 *
 * Les lieux hors de la collection nationale de leur thème en ont une : cette
 * collection EST le meilleur de France pour ce thème, et en sortir veut dire
 * quelque chose. Sur les deux mille vingt-neuf lieux du catalogue, cela donne
 * 11,8 % à trois étoiles, 25,6 % à deux, 62,5 % à une — la répartition que le
 * pipeline vise déjà quand il attribue ses places.
 *
 * Une étoile n'est donc pas une mauvaise note : tout ce qui est au catalogue a
 * passé la barre. C'est l'échelle de tous les guides depuis un siècle, et les
 * mentions le disent.
 */

export type Etoiles = 1 | 2 | 3;

/** Ce que chaque note veut dire, en toutes lettres. */
export const MENTIONS: Record<Etoiles, string> = {
  3: 'Vaut le voyage',
  2: 'Mérite un détour',
  1: 'À voir en passant',
};

const parLieu = new Map<string, Etoiles>();
for (const collection of collections) {
  // La collection NATIONALE d'un thème : pas de code géographique.
  if (collection.kind !== 'theme' || collection.geoCode) continue;
  for (const membre of collection.places) {
    // Niveau 1 → trois étoiles, niveau 3 → une.
    const note = (4 - membre.tier) as Etoiles;
    const connu = parLieu.get(membre.placeId);
    if (connu === undefined || note > connu) parLieu.set(membre.placeId, note);
  }
}

export const etoilesDe = (placeId: string): Etoiles => parLieu.get(placeId) ?? 1;

/** Combien de lieux portent chaque note. Sert aux tests et aux compteurs. */
export function repartition(placeIds: string[]): Record<Etoiles, number> {
  const compte: Record<Etoiles, number> = { 1: 0, 2: 0, 3: 0 };
  for (const id of placeIds) compte[etoilesDe(id)] += 1;
  return compte;
}
