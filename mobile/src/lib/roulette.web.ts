import { useEffect, type RefObject } from 'react';

/**
 * Faire défiler une rangée horizontale à la molette, sur le web.
 *
 * La molette d'une souris ne produit que du défilement VERTICAL. Une rangée
 * horizontale — les thèmes au-dessus de la carte, le bandeau des lieux voisins —
 * restait donc bloquée sur ce qui tenait à l'écran, sans le moindre indice
 * qu'il y avait autre chose. Le navigateur sait le faire avec Maj + molette,
 * mais personne ne le sait.
 *
 * On convertit donc le geste : ce que la molette donne en vertical, on le rend
 * en horizontal — et seulement quand le geste EST vertical, pour ne pas voler
 * un pavé tactile qui, lui, sait déjà défiler de côté.
 */
export function useRoulette(ref: RefObject<{ getScrollableNode?: () => unknown } | null>): void {
  useEffect(() => {
    const noeud = ref.current?.getScrollableNode?.() as HTMLElement | undefined;
    if (!noeud || typeof noeud.addEventListener !== 'function') return;

    const surMolette = (event: WheelEvent) => {
      if (Math.abs(event.deltaY) <= Math.abs(event.deltaX)) return;
      // Rien à faire si la rangée tient entièrement à l'écran : on laisserait
      // sinon la page immobile sous une molette qui devrait la faire défiler.
      if (noeud.scrollWidth <= noeud.clientWidth) return;
      noeud.scrollLeft += event.deltaY;
      event.preventDefault();
    };

    noeud.addEventListener('wheel', surMolette, { passive: false });
    return () => noeud.removeEventListener('wheel', surMolette);
  }, [ref]);
}
