/**
 * Quel pays regarde-t-on ?
 *
 * La bascule d'un pays à l'autre doit être INVISIBLE : on se promène sur la
 * carte, on passe la frontière, le catalogue suit. Pas de menu, pas de
 * question — la carte est déjà le geste.
 *
 * Tout est pur ici : ni carte, ni réseau, ni React. C'est ce qui permet
 * d'éprouver la règle de bascule, qui est plus subtile qu'elle n'en a l'air.
 */

/** (ouest, sud, est, nord) — une boîte, en degrés. */
export type Emprise = [number, number, number, number];

export type PaysConnu = {
  code: string;
  name: string;
  emprises: Emprise[];
};

export function dansLEmprise(lon: number, lat: number, emprises: Emprise[]): boolean {
  return emprises.some(
    ([ouest, sud, est, nord]) => lon >= ouest && lon <= est && lat >= sud && lat <= nord,
  );
}

/**
 * Le pays vers lequel basculer, ou null pour ne rien changer.
 *
 * Deux règles, et la seconde est celle qui fait tout le confort.
 *
 * **On ne bascule que si l'on est SORTI du pays courant.** Les emprises se
 * chevauchent le long d'une frontière — les Alpes sont dans la boîte de la
 * Savoie et dans celle du Piémont. Sans cette hystérésis, se promener autour
 * du mont Blanc ferait clignoter le catalogue d'un pays à l'autre à chaque
 * mouvement de doigt.
 *
 * **On ne bascule que vers UN seul candidat.** Au-dessus d'un point qui
 * appartient à deux pays voisins sans appartenir au courant — cela arrive au
 * milieu du Rhin — deviner serait pire que ne rien faire : on attend que la
 * carte tranche d'elle-même.
 */
export function paysAAdopter(
  lon: number,
  lat: number,
  courant: string,
  connus: PaysConnu[],
): string | null {
  const ici = connus.find((p) => p.code === courant);
  if (ici && dansLEmprise(lon, lat, ici.emprises)) return null;

  const candidats = connus.filter(
    (p) => p.code !== courant && p.emprises.length > 0 && dansLEmprise(lon, lat, p.emprises),
  );
  return candidats.length === 1 ? candidats[0].code : null;
}
