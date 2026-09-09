import embarque from './catalog.json';
import type { Catalog } from '../types';

/**
 * Les catalogues disponibles, et comment les obtenir.
 *
 * UN catalogue par pays. Celui du pays de départ est EMBARQUÉ : il doit être
 * là au premier lancement, sans réseau, sinon l'application s'ouvre sur rien.
 * Les autres se téléchargent une fois et restent en mémoire — passer de la
 * France à l'Italie et revenir ne redemande rien à personne.
 *
 * `url` reste à renseigner : c'est la seule décision qui manque, et elle est
 * d'hébergement, pas de code. Le dépôt lui-même ferait l'affaire — les
 * catalogues y sont déjà versionnés et servis en HTTPS.
 */
export type PaysDisponible = {
  code: string;
  name: string;
  /** Absent = embarqué dans l'application, disponible hors ligne. */
  url?: string;
};

const catalogueEmbarque = embarque as unknown as Catalog;

export const PAYS_EMBARQUE: string =
  catalogueEmbarque.areas?.country?.[0]?.code ?? 'FR';

export const PAYS: PaysDisponible[] = [
  {
    code: PAYS_EMBARQUE,
    name: catalogueEmbarque.areas?.country?.[0]?.name ?? 'France',
  },
];

/**
 * Les catalogues déjà en main. Le retour dans un pays déjà visité est
 * instantané : c'est toute la différence entre « changer de pays » et
 * « attendre ».
 */
const enMain = new Map<string, Catalog>([[PAYS_EMBARQUE, catalogueEmbarque]]);

export const dejaCharge = (code: string): boolean => enMain.has(code);

export const catalogueDe = (code: string): Catalog | undefined => enMain.get(code);

/** Pour les tests, et pour un catalogue reçu par un autre chemin. */
export function deposer(code: string, catalogue: Catalog): void {
  enMain.set(code, catalogue);
}

export class PaysInconnu extends Error {}

/**
 * Va chercher un catalogue absent. Rend celui qu'on a déjà, sans requête.
 *
 * Le `fetch` est passé en paramètre plutôt qu'appelé en dur : c'est ce qui
 * permet d'éprouver le chemin d'erreur — un réseau coupé au milieu d'un
 * voyage n'est pas une hypothèse d'école — sans dépendre d'un vrai serveur.
 */
export async function obtenir(
  code: string,
  aller: typeof fetch = fetch,
): Promise<Catalog> {
  const connu = enMain.get(code);
  if (connu) return connu;

  const pays = PAYS.find((p) => p.code === code);
  if (!pays?.url) throw new PaysInconnu(code);

  const reponse = await aller(pays.url);
  if (!reponse.ok) throw new Error(`catalogue ${code} : HTTP ${reponse.status}`);
  const catalogue = (await reponse.json()) as Catalog;
  enMain.set(code, catalogue);
  return catalogue;
}
