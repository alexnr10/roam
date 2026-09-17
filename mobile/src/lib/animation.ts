/**
 * Une animation pilotée image par image, et son arrêt.
 *
 * Sortie de `MapCanvas` pour une raison précise : elle porte un piège qui a
 * coûté un vrai défaut, et qui était invisible là où elle vivait. Un mécanisme
 * de quarante lignes qui ne peut pas s'éprouver finit toujours par se payer.
 *
 * LE PIÈGE. Une animation qui repose sur `requestAnimationFrame` seul ne
 * s'exécute pas dans un onglet en arrière-plan et se fait rationner sur une
 * machine chargée : elle s'arrête en chemin, et laisse ce qu'elle animait à
 * mi-course — des pastilles à moitié transparentes, pour toujours. Il faut
 * donc un FILET, un `setTimeout` qui la fait aboutir de force.
 *
 * Mais alors, arrêter l'animation ne suffit plus à l'arrêter : couper l'image
 * suivante laisse courir le filet, qui la fera aboutir quand même, jusqu'à
 * cent cinquante millisecondes plus tard. Une animation annulée qui exécute
 * quand même sa fin est une bombe à retardement — et elle a explosé : le
 * fondu de sortie des lieux se termine en VIDANT la source de la carte, et il
 * vidait donc une source qu'une autre animation venait de remplir.
 *
 * Les deux s'annulent ensemble, ou rien ne s'annule.
 */
export type Animation = {
  /** Fait aboutir l'animation tout de suite, `surFin` compris. */
  finir: () => void;
  /** L'abandonne : ni image de plus, ni filet, ni `surFin`. */
  arreter: () => void;
};

export type Horloge = {
  maintenant: () => number;
  image: (suite: () => void) => number;
  annulerImage: (jeton: number) => void;
  filet: (suite: () => void, delai: number) => ReturnType<typeof setTimeout>;
  annulerFilet: (jeton: ReturnType<typeof setTimeout>) => void;
};

/** L'horloge du navigateur. Remplaçable, pour que le mécanisme s'éprouve. */
export const HORLOGE: Horloge = {
  maintenant: () => performance.now(),
  image: (suite) => requestAnimationFrame(suite),
  annulerImage: (jeton) => cancelAnimationFrame(jeton),
  filet: (suite, delai) => setTimeout(suite, delai),
  annulerFilet: (jeton) => clearTimeout(jeton),
};

/** De combien le filet dépasse la durée annoncée, en millisecondes. */
export const MARGE_DU_FILET = 150;

/**
 * Anime pendant `duree`, en appelant `surImage(avancement, ecoule)`.
 *
 * `surImage(1, duree)` est toujours appelé en dernier, puis `surFin` — sauf
 * si l'animation a été ARRÊTÉE, auquel cas ni l'un ni l'autre ne vient.
 */
export function animer(
  duree: number,
  surImage: (avancement: number, ecoule: number) => void,
  surFin?: () => void,
  horloge: Horloge = HORLOGE,
): Animation {
  const debut = horloge.maintenant();
  let jetonImage: number | null = null;
  let jetonFilet: ReturnType<typeof setTimeout> | null = null;
  let close = false;

  const ranger = () => {
    if (jetonImage !== null) horloge.annulerImage(jetonImage);
    if (jetonFilet !== null) horloge.annulerFilet(jetonFilet);
    jetonImage = null;
    jetonFilet = null;
  };

  const finir = () => {
    if (close) return;
    close = true;
    ranger();
    surImage(1, duree);
    surFin?.();
  };

  const arreter = () => {
    if (close) return;
    close = true;
    ranger();
  };

  const pas = () => {
    jetonImage = null;
    const ecoule = horloge.maintenant() - debut;
    if (ecoule >= duree) return finir();
    surImage(Math.min(1, ecoule / duree), ecoule);
    jetonImage = horloge.image(pas);
  };

  jetonFilet = horloge.filet(finir, duree + MARGE_DU_FILET);
  jetonImage = horloge.image(pas);
  return { finir, arreter };
}
