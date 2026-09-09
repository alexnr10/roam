import embarque from './catalog.json';
import type { Emprise, PaysConnu } from '../lib/pays';
import type { Catalog } from '../types';

/**
 * Les catalogues disponibles, et comment les obtenir.
 *
 * UN catalogue par pays. Celui du pays de départ est EMBARQUÉ : il doit être
 * là au premier lancement, sans réseau, sinon l'application s'ouvre sur rien.
 * Les autres sont servis par le DÉPÔT lui-même — ils y sont déjà versionnés,
 * en HTTPS, gratuitement, et une version du catalogue va donc toujours avec
 * la version de l'application qui la lit.
 *
 * `index.json` dit ce qui existe et OÙ : c'est lui qui permet à la carte de
 * savoir, en se déplaçant, qu'elle vient d'entrer dans un autre pays.
 */
export type PaysDisponible = PaysConnu & {
  /** Absent = embarqué dans l'application, disponible hors ligne. */
  fichier?: string;
  lieux?: number;
};

/**
 * D'où viennent les catalogues servis.
 *
 * La branche est écrite ici plutôt que devinée : une application publiée doit
 * lire une branche stable, pas celle sur laquelle on travaille ce jour-là.
 */
const DEPOT = 'https://raw.githubusercontent.com/alexnr10/roam';
const BRANCHE = 'main';
export const BASE = `${DEPOT}/${BRANCHE}/catalogues`;

const catalogueEmbarque = embarque as unknown as Catalog;

export const PAYS_EMBARQUE: string =
  catalogueEmbarque.areas?.country?.[0]?.code ?? 'FR';

export const PAYS: PaysDisponible[] = [
  {
    code: PAYS_EMBARQUE,
    name: catalogueEmbarque.areas?.country?.[0]?.name ?? 'France',
    emprises: [],
  },
];

const enMain = new Map<string, Catalog>([[PAYS_EMBARQUE, catalogueEmbarque]]);

export const dejaCharge = (code: string): boolean => enMain.has(code);
export const catalogueDe = (code: string): Catalog | undefined => enMain.get(code);

/** Pour les tests, et pour un catalogue reçu par un autre chemin. */
export function deposer(code: string, catalogue: Catalog): void {
  enMain.set(code, catalogue);
}

export class PaysInconnu extends Error {}

/**
 * Lit l'index et complète la liste des pays.
 *
 * Silencieux en cas d'échec, et c'est voulu : sans réseau, l'application
 * reste parfaitement utilisable sur son pays embarqué. Un message d'erreur au
 * démarrage pour une fonction dont on ne se sert peut-être pas serait pire
 * que le manque.
 */
export async function lireIndex(aller: typeof fetch = fetch): Promise<PaysDisponible[]> {
  try {
    const reponse = await aller(`${BASE}/index.json`);
    if (!reponse.ok) return PAYS;
    const donnees = (await reponse.json()) as {
      pays?: { code: string; name: string; fichier?: string; lieux?: number; emprises?: Emprise[] }[];
    };
    for (const entree of donnees.pays ?? []) {
      if (!entree.code) continue;
      const connu = PAYS.find((p) => p.code === entree.code);
      const complet: PaysDisponible = {
        code: entree.code,
        name: entree.name || entree.code,
        emprises: entree.emprises ?? [],
        fichier: entree.fichier,
        lieux: entree.lieux,
      };
      // Le pays embarqué GARDE son catalogue local — on ne retéléchargera pas
      // ce qu'on a déjà — mais il gagne son emprise, sans laquelle la carte ne
      // saurait pas qu'on vient d'en sortir.
      if (connu) Object.assign(connu, { emprises: complet.emprises, lieux: complet.lieux });
      else PAYS.push(complet);
    }
  } catch {
    // Hors ligne : le pays embarqué suffit.
  }
  return PAYS;
}

/** Va chercher un catalogue absent. Rend celui qu'on a déjà, sans requête. */
export async function obtenir(
  code: string,
  aller: typeof fetch = fetch,
): Promise<Catalog> {
  const connu = enMain.get(code);
  if (connu) return connu;

  const pays = PAYS.find((p) => p.code === code);
  if (!pays?.fichier) throw new PaysInconnu(code);

  const reponse = await aller(`${BASE}/${pays.fichier}`);
  if (!reponse.ok) throw new Error(`catalogue ${code} : HTTP ${reponse.status}`);
  const catalogue = (await reponse.json()) as Catalog;
  enMain.set(code, catalogue);
  return catalogue;
}
