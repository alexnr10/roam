import embarque from './catalog.json';
import contoursEmbarques from './outlines.json';
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
  /**
   * Les contours administratifs de ce pays, s'il en a.
   *
   * Un pays peut très bien arriver sans : sa carte de conquête retombe alors
   * sur la liste, qui dit la même chose sans dessin. C'est ce qui permet
   * d'ouvrir un pays avant d'avoir tracé ses frontières.
   */
  contours?: string;
};

/**
 * D'où viennent les catalogues servis.
 *
 * Deux choses arrivent sur le téléphone, et une seule est figée par le paquet.
 * L'application, oui ; les catalogues, non — ils sont relus À CHAQUE
 * démarrage, et c'est tout l'intérêt : corriger le catalogue ne demande pas
 * de recompiler.
 *
 * Mais une version DONNÉE à quelqu'un ne doit pas changer sous ses pieds. En
 * lisant `main`, une application publiée verrait apparaître un pays le jour où
 * on l'y pousse — sans mise à jour, sans rien demander. Quelqu'un à qui on a
 * confié « la version France » ferait glisser la carte vers Menton et
 * trouverait l'Italie.
 *
 * La référence est donc une donnée de compilation, dans `app.json` :
 *
 *     "extra": { "catalogues": "main" }        pour le développement
 *     "extra": { "catalogues": "v0.1-france" } pour une version publiée
 *
 * `raw.githubusercontent.com` sert une ÉTIQUETTE exactement comme une
 * branche : pointer une version publiée sur un tag fige ses catalogues pour de
 * bon, et rend `main` à son rôle, qui est de bouger.
 */
const DEPOT = 'https://raw.githubusercontent.com/alexnr10/roam';

/** La référence par défaut, quand la configuration ne dit rien. */
export const REFERENCE_PAR_DEFAUT = 'main';

/**
 * La référence servie, dans l'ordre où elle peut être connue.
 *
 * 1. **`EXPO_PUBLIC_ROAM_CATALOGUES`**, inlinée dans le bundle à la
 *    compilation. C'est la seule qui marche PARTOUT.
 * 2. La configuration Expo, pour une application compilée.
 * 3. `main`, pour développer.
 *
 * L'ordre a été payé. La configuration seule suffisait à l'APK — une
 * application native embarque son manifeste — mais PAS à un site statique :
 * l'`index.html` exporté ne porte aucune configuration, `expo-constants` n'y
 * trouve rien, et la version publiée retombait silencieusement sur `main`.
 * Elle aurait donc vu apparaître un deuxième pays le jour où on l'y pousse :
 * exactement ce que tout ce mécanisme cherche à empêcher.
 *
 * Une variable `EXPO_PUBLIC_*` est remplacée par sa VALEUR au moment du
 * bundling : elle est donc dans le fichier livré, vérifiable en le lisant, et
 * ne dépend d'aucun manifeste à l'exécution.
 */
export function referenceServie(): string {
  const inlinee = process.env.EXPO_PUBLIC_ROAM_CATALOGUES;
  if (typeof inlinee === 'string' && inlinee.trim()) return inlinee.trim();
  try {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const Constants = require('expo-constants').default;
    const dite = Constants?.expoConfig?.extra?.catalogues;
    return typeof dite === 'string' && dite.trim() ? dite.trim() : REFERENCE_PAR_DEFAUT;
  } catch {
    return REFERENCE_PAR_DEFAUT;
  }
}

export const BASE = `${DEPOT}/${referenceServie()}/catalogues`;

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
const contoursEnMain = new Map<string, unknown>([[PAYS_EMBARQUE, contoursEmbarques]]);

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
      pays?: {
        code: string; name: string; fichier?: string; lieux?: number;
        emprises?: Emprise[]; contours?: string;
      }[];
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
        contours: entree.contours,
      };
      // Le pays embarqué GARDE son catalogue local — on ne retéléchargera pas
      // ce qu'on a déjà — mais il gagne son emprise, sans laquelle la carte ne
      // saurait pas qu'on vient d'en sortir.
      if (connu) {
        Object.assign(connu, {
          emprises: complet.emprises, lieux: complet.lieux, contours: complet.contours,
        });
      }
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


/**
 * Les contours d'un pays, ou null s'il n'en a pas.
 *
 * Ceux du pays embarqué sont déjà là : les redemander serait huit cent
 * soixante kilo-octets pour rien. Un échec de téléchargement n'est pas une
 * erreur non plus — la carte de conquête retombe sur la liste, et le
 * catalogue, lui, est déjà chargé.
 */
export async function obtenirContours(
  code: string,
  aller: typeof fetch = fetch,
): Promise<unknown | null> {
  if (contoursEnMain.has(code)) return contoursEnMain.get(code) ?? null;

  const pays = PAYS.find((p) => p.code === code);
  if (!pays?.contours) return null;
  try {
    const reponse = await aller(`${BASE}/${pays.contours}`);
    if (!reponse.ok) return null;
    const donnees = await reponse.json();
    contoursEnMain.set(code, donnees);
    return donnees;
  } catch {
    return null;
  }
}
