import { places } from '../data/catalog';

/**
 * De quelle construction vient la page qu'on regarde.
 *
 * L'aperçu web est UN SEUL fichier `index.html`, sans nom haché : le
 * navigateur d'un téléphone le garde en cache longtemps après la publication
 * suivante. On croit alors voir un lieu qu'on vient d'écarter, et on ne peut
 * pas distinguer « la suppression n'a pas marché » de « je regarde la page
 * d'hier » — deux causes très différentes, aucun moyen de trancher.
 *
 * Le nombre de lieux suffit presque toujours : il change à chaque
 * construction, et il se compare d'un coup d'œil au journal du build. La
 * signature et la date le confirment exactement.
 */
export type Build = {
  /** Les sept premiers caractères du commit publié. */
  sha: string;
  /** Date de construction, au format ISO. */
  date: string;
};

declare global {
  // eslint-disable-next-line no-var
  var __ROAM_BUILD__: Build | undefined;
}

/**
 * `null` hors de l'aperçu web : l'application native n'est pas servie par un
 * cache, la question ne s'y pose pas.
 */
export function buildStamp(): Build | null {
  const stamp = globalThis.__ROAM_BUILD__;
  if (!stamp || typeof stamp.sha !== 'string' || typeof stamp.date !== 'string') {
    return null;
  }
  return stamp;
}

/** Ce qu'on affiche en pied de page. Le catalogue d'abord : c'est le chiffre
 *  qui répond à « est-ce que ma suppression est passée ? ». */
export function buildLabel(): string {
  const parts = [`${places.length} lieux`];
  const stamp = buildStamp();
  if (stamp) {
    parts.push(stamp.sha);
    const quand = new Date(stamp.date);
    if (!Number.isNaN(quand.getTime())) {
      parts.push(
        quand.toLocaleString('fr-FR', {
          day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit',
        }),
      );
    }
  }
  return parts.join(' · ');
}
