import type { RefObject } from 'react';

/**
 * Faire défiler une rangée horizontale à la molette.
 *
 * Sur téléphone, une rangée horizontale se pousse du doigt. Sur un ordinateur,
 * la molette ne défile que verticalement : les thèmes au-dessus de la carte et
 * le bandeau des lieux voisins étaient donc INATTEIGNABLES au-delà de ce qui
 * tenait à l'écran, sans le moindre indice qu'il y avait autre chose.
 *
 * Sur téléphone, il n'y a pas de molette et rien à faire : cette version ne
 * fait rien, et c'est `roulette.web.ts` qui porte le comportement.
 */
export function useRoulette(_ref: RefObject<unknown>): void {
  // Rien à brancher hors du web.
}
