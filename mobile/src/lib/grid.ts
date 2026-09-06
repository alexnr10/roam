import type { Place } from '../types';

/**
 * Le quadrillage : reconnaître d'un coup d'œil les lieux où l'on est déjà allé.
 *
 * C'est le problème du premier jour. Une application de collection qui démarre
 * à zéro sur deux mille lieux ne dit rien de son propriétaire : la moitié de ce
 * qu'il a vu dans sa vie y figure, et le saisir à la main — chercher un nom,
 * ouvrir une fiche, valider, revenir — coûte trop cher pour être fait.
 *
 * On ne se souvient pas d'une liste de noms, on RECONNAÎT une image. Le
 * quadrillage montre donc des photos, en grille, et le geste se réduit à un
 * doigt qui touche ce qu'il reconnaît.
 *
 * Trois décisions d'ordre, chacune au service de ce geste :
 *
 * 1. **Les plus connus d'abord.** Une vie de voyages en France est surtout
 *    faite de lieux célèbres ; c'est là que se trouve le rendement. Descendre
 *    le classement, c'est descendre la probabilité d'y être allé.
 * 2. **Les lieux sans photo à la fin.** Vingt-trois lieux n'en ont pas, et une
 *    tuile sans image ne se reconnaît pas — elle se lit, ce qui est le geste
 *    qu'on cherchait à éviter. On ne les cache pas pour autant : les mettre en
 *    dernier suffit.
 * 3. **Le territoire comme filtre, avant le thème.** On se souvient d'un
 *    voyage par où il a eu lieu, pas par catégorie : « la Bretagne », pas
 *    « les phares ».
 */

export type Mode = 'a-reconnaitre' | 'valides';

export function tuiles(
  places: Place[],
  {
    mode,
    regionCode = null,
    visitedIds,
  }: { mode: Mode; regionCode?: string | null; visitedIds: Set<string> },
): Place[] {
  const gardes = places.filter((place) => {
    if (regionCode && place.regionCode !== regionCode) return false;
    return visitedIds.has(place.id) === (mode === 'valides');
  });
  return gardes.sort(
    (a, b) =>
      Number(!a.imageUrl) - Number(!b.imageUrl) ||
      b.score - a.score ||
      a.name.localeCompare(b.name),
  );
}

/**
 * Les régions où le catalogue a des lieux, dans l'ordre du filtre.
 *
 * Tirées des LIEUX et non du répertoire : une région sans lieu visible ne
 * mérite pas une pastille qui ne rendrait rien.
 *
 * Et seulement celles que le répertoire NOMME. Wikidata range parfois un lieu
 * dans la nomenclature d'avant 2016 — la Corse en « 92 », l'ancien code de
 * Provence-Alpes-Côte d'Azur — et le filtre affichait alors une pastille
 * intitulée « 92 », qui ne veut rien dire pour personne. Le pipeline corrige
 * ces codes ; l'écran ne doit pas en dépendre.
 */
export function regionsPresentes(
  places: Place[],
  noms: Map<string, string>,
): Array<{ value: string; label: string }> {
  const codes = new Set<string>();
  for (const place of places) {
    if (place.regionCode && noms.has(place.regionCode)) codes.add(place.regionCode);
  }
  return [...codes]
    .map((code) => ({ value: code, label: noms.get(code) as string }))
    .sort((a, b) => a.label.localeCompare(b.label));
}
