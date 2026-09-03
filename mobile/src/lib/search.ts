import type { Place } from '../types';

/**
 * Retrouver un lieu qu'on a visité, sans se souvenir de son nom exact.
 *
 * C'est le problème le plus concret de l'application : personne ne se rappelle
 * ce qu'il a visité en parcourant deux mille fiches. On se souvient en
 * RECONNAISSANT — et pour reconnaître, il faut d'abord pouvoir taper trois
 * lettres.
 *
 * Trois décisions, chacune tirée d'un vrai raté du catalogue :
 *
 * 1. **La commune compte autant que le nom.** Les falaises d'Étretat sont
 *    fichées « Porte d'Aval » ; chercher « étretat » sur le seul nom ne rend
 *    rien. Le lieu se cherche par là où l'on est allé, pas par le libellé que
 *    Wikidata lui donne.
 * 2. **Les accents et la casse ne comptent pas.** On tape « chateau » sur un
 *    clavier de téléphone, pas « Château ».
 * 3. **Un début de mot vaut mieux qu'un milieu.** « Marie » doit rendre
 *    « Sainte-Marie-Majeure » avant « Les Saintes-Maries-de-la-Mer ».
 */

export type Match = {
  place: Place;
  /** Ce qui a répondu : le nom du lieu, ou l'endroit où il se trouve. */
  par: 'nom' | 'lieu';
};

const VIDES = new Set([
  'de', 'des', 'du', 'la', 'le', 'les', 'l', 'd', 'et', 'aux', 'au', 'sur',
  'sous', 'en', 'a',
]);

/** Minuscules sans accents : « Château » et « chateau » doivent se répondre. */
export function fold(texte: string): string {
  return texte
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase();
}

/** Les mots porteurs d'un texte, ponctuation et articles ôtés. */
function mots(texte: string): string[] {
  return fold(texte)
    .replace(/[^a-z0-9]+/g, ' ')
    .split(' ')
    .filter((mot) => mot.length > 0 && !VIDES.has(mot));
}

/**
 * À quel point ce texte répond à la recherche. `0` = pas du tout.
 *
 * L'échelle est grossière à dessein : elle sépare trois cas — le texte
 * COMMENCE par ce qu'on tape, un de ses MOTS commence par ce qu'on tape, ou
 * le texte le contient quelque part. Au-delà, c'est la notoriété du lieu qui
 * départage, et elle le fait mieux qu'une heuristique.
 */
export function pertinence(texte: string, recherche: string): number {
  const cible = fold(texte);
  const q = fold(recherche).trim();
  if (!q) return 0;
  if (cible === q) return 4;
  if (cible.startsWith(q)) return 3;
  if (mots(texte).some((mot) => mot.startsWith(q))) return 2;
  if (cible.includes(q)) return 1;
  return 0;
}

/** Combien de caractères il faut avoir tapés pour qu'une recherche ait un sens. */
export const MIN_CARACTERES = 2;

/**
 * Les lieux qui répondent, les plus pertinents d'abord.
 *
 * Le nom l'emporte toujours sur la commune : qui tape « gordes » cherche le
 * village, pas les six lieux qui s'y trouvent. Mais la commune reste, plus
 * bas — c'est elle qui sauve Étretat.
 */
export function search(places: Place[], recherche: string, limite = 40): Match[] {
  const q = recherche.trim();
  if (q.length < MIN_CARACTERES) return [];

  const notes: Array<{ match: Match; note: number; score: number }> = [];
  for (const place of places) {
    const parNom = pertinence(place.name, q);
    // La commune vaut un cran de moins que le nom, à pertinence égale : elle
    // répond quand le nom ne dit rien, elle ne le remplace pas.
    const ou = [place.communeName, place.departement].filter(Boolean) as string[];
    const parLieu = Math.max(0, ...ou.map((texte) => pertinence(texte, q)));

    if (parNom === 0 && parLieu === 0) continue;
    const gagnant = parNom >= parLieu ? 'nom' : 'lieu';
    notes.push({
      match: { place, par: gagnant },
      note: gagnant === 'nom' ? parNom * 2 : parLieu * 2 - 1,
      score: place.score ?? 0,
    });
  }

  notes.sort((a, b) =>
    b.note - a.note
    || b.score - a.score
    || a.match.place.name.localeCompare(b.match.place.name, 'fr'));
  return notes.slice(0, limite).map((entree) => entree.match);
}
