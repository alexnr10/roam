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

/** L'emprise TOTALE d'un pays : la boîte qui contient toutes les siennes. */
function tout(emprises: Emprise[]): Emprise | null {
  if (emprises.length === 0) return null;
  let [ouest, sud, est, nord] = emprises[0];
  for (const [o, s, e, n] of emprises) {
    if (o < ouest) ouest = o;
    if (s < sud) sud = s;
    if (e > est) est = e;
    if (n > nord) nord = n;
  }
  return [ouest, sud, est, nord];
}

/**
 * Le pays `petit` tient-il tout entier dans UNE boîte du pays `grand` ?
 *
 * C'est la définition d'une ENCLAVE, et elle se lit dans les emprises sans
 * qu'aucune liste n'ait à la déclarer.
 *
 * UNE boîte, et non leur union : l'union française va de la Guadeloupe à
 * Mayotte, soit de 61° ouest à 45° est, et l'Italie entière tient dedans. La
 * règle écrite ainsi faisait basculer le mont Blanc vers l'Italie — mesuré sur
 * les emprises réellement servies, pas supposé. Une boîte départementale fait
 * un degré ou deux : l'Italie n'y entre pas, le Vatican entre dans celle de la
 * province de Rome.
 */
function enclaveDe(petit: PaysConnu, grand: PaysConnu): boolean {
  const p = tout(petit.emprises);
  if (!p) return false;
  return grand.emprises.some(
    ([ouest, sud, est, nord]) =>
      p[0] >= ouest && p[1] >= sud && p[2] <= est && p[3] <= nord,
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
 *
 * **Une ENCLAVE fait exception à la première.** On ne sort jamais de l'Italie
 * en entrant au Vatican : sa boîte est dans celle de la province de Rome, donc
 * l'hystérésis répondait « reste en Italie » au-dessus même de Saint-Pierre, et
 * le Vatican était INATTEIGNABLE — mesuré : `paysAAdopter` ne le rendait jamais.
 * Un pays dont l'emprise tient tout entière dans celle du pays courant n'est
 * pas un pays voisin dont on frôle la frontière : c'est un pays DEDANS, et y
 * entrer est un geste, pas un tremblement. La règle du candidat unique
 * s'applique quand même — deux enclaves superposées ne se devinent pas.
 */
export function paysAAdopter(
  lon: number,
  lat: number,
  courant: string,
  connus: PaysConnu[],
): string | null {
  const ici = connus.find((p) => p.code === courant);
  const candidats = connus.filter(
    (p) => p.code !== courant && p.emprises.length > 0 && dansLEmprise(lon, lat, p.emprises),
  );

  if (ici && dansLEmprise(lon, lat, ici.emprises)) {
    const dedans = candidats.filter((p) => enclaveDe(p, ici));
    return dedans.length === 1 ? dedans[0].code : null;
  }

  return candidats.length === 1 ? candidats[0].code : null;
}
