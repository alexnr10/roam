import type { Envie } from '../types';

/**
 * La liste des envies, en tant que valeur.
 *
 * Le magasin `store/envies.tsx` ne fait que porter cette liste dans un
 * contexte React et l'écrire dans le stockage local. Tout ce qui DÉCIDE est
 * ici, en fonctions pures — c'est la même séparation que `visit.ts` et
 * `store/visits.tsx`, et c'est ce qui rend la règle testable : l'outillage de
 * test du projet est en environnement Node, sans moteur de rendu.
 */

/** Ajoute un lieu, sans doublon. Une envie deux fois n'est pas deux envies. */
export function ajoutee(envies: Envie[], placeId: string, maintenant = new Date()): Envie[] {
  if (envies.some((envie) => envie.placeId === placeId)) return envies;
  return [...envies, { placeId, addedAt: maintenant.toISOString() }];
}

export function retiree(envies: Envie[], placeId: string): Envie[] {
  return envies.filter((envie) => envie.placeId !== placeId);
}

/** Le geste d'un bouton unique : présent → absent, absent → présent. */
export function basculee(envies: Envie[], placeId: string, maintenant = new Date()): Envie[] {
  return envies.some((envie) => envie.placeId === placeId)
    ? retiree(envies, placeId)
    : ajoutee(envies, placeId, maintenant);
}

/**
 * Une envie réalisée sort de la liste.
 *
 * C'est la règle du curateur, et elle est plus juste qu'un simple affichage
 * filtré : la liste dit ce qu'il RESTE à faire. Un lieu validé qu'on y
 * laisserait coché ferait de la liste un second carnet de visites, alors
 * qu'elle existe pour dire l'inverse.
 *
 * Conséquence assumée : retirer une visite ne fait pas revenir l'envie. Elle a
 * été honorée, la promesse est éteinte.
 *
 * Rend la liste INCHANGÉE quand il n'y a rien à retirer — l'identité compte,
 * elle évite un rendu et une écriture dans le stockage à chaque visite.
 */
export function sansLesVisites(envies: Envie[], visitedIds: ReadonlySet<string>): Envie[] {
  const restants = envies.filter((envie) => !visitedIds.has(envie.placeId));
  return restants.length === envies.length ? envies : restants;
}

/** Les dernières envies d'abord : c'est celle qu'on vient d'ajouter qu'on cherche. */
export function parDateDecroissante(envies: Envie[]): Envie[] {
  return [...envies].sort((a, b) => b.addedAt.localeCompare(a.addedAt));
}
