import type { Tier } from '../types';

/**
 * Les trois paliers d'une collection, par leur nom.
 *
 * Une collection est une échelle qu'on grimpe : on finit d'abord ses lieux les
 * plus forts, puis les suivants. Ce classement est RELATIF à la collection — le
 * même lieu est premier de son département et dernier de son thème national.
 *
 * Il ne faut donc pas le dire en étoiles, et pas non plus en niveaux.
 *
 * **Pas en étoiles**, parce que l'étoile est déjà la note d'un lieu, nationale
 * et par catégorie : la maison du docteur Gachet vaut une étoile en France et
 * serait « trois étoiles du Val-d'Oise ». Deux notes contradictoires sur la
 * même fiche, et le lecteur ne sait plus laquelle croire. On a d'ailleurs
 * vérifié qu'on ne peut pas non plus fondre les deux : trente-huit collections
 * sur deux cent deux n'ont aucun lieu trois étoiles, et « Le meilleur du
 * Val-d'Oise » n'aurait plus de premier palier du tout.
 *
 * **Pas en niveaux non plus**, parce que « niveau 3 » et « une étoile » sur le
 * même écran font deux barèmes à apprendre pour une seule idée.
 *
 * Restent les noms. Ils ne demandent rien à personne, ils ne se confondent avec
 * aucune note, et ils disent ce que le palier est : le haut du panier de CETTE
 * liste, puis ce qui vient après.
 */
export const PALIERS: Record<Tier, string> = {
  1: 'Les incontournables',
  2: 'La deuxième ligne',
  3: 'Les pépites',
};

/** Le même nom, en minuscule, pour une phrase : « … la deuxième ligne finie ». */
export const palierMinuscule = (tier: Tier): string =>
  PALIERS[tier].charAt(0).toLowerCase() + PALIERS[tier].slice(1);
