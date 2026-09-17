import { useEffect, useMemo, useRef, useState } from 'react';

import { catalogueDe, dejaCharge, obtenir, type PaysDisponible } from '../data/catalogues';
import type { Emprise as EmpriseCarte } from './regions';
import { dansLEmprise, type Emprise, type PaysConnu } from './pays';
import type { Catalog, Place } from '../types';
import type { Etoiles } from './etoiles';

/**
 * Les lieux d'une enclave, posés sur la carte du pays qui l'entoure.
 *
 * Roam ne tient qu'UN catalogue actif, et c'est une décision : une étoile dit
 * un rang dans une collection nationale, mélanger deux pays ferait disputer au
 * Colisée la place du Pont du Gard. La carte suit cette règle, et elle a
 * raison partout sauf ici.
 *
 * Au-dessus de Rome, le Vatican est DANS l'écran. Ses dix-neuf lieux — la
 * basilique Saint-Pierre, la chapelle Sixtine, les Musées — n'appartiennent
 * plus au catalogue italien depuis qu'il est un pays à part entière, et la
 * carte romaine s'ouvrait donc sur un trou de quarante-quatre hectares à
 * l'endroit précis où le guide a le plus à dire. Personne, debout devant le
 * Château Saint-Ange, ne se demande dans quel État il se trouve.
 *
 * Ce module ne mélange rien : il AJOUTE, sans rendre actif. Les lieux ajoutés
 * portent leur pays et leur note, parce que ni l'un ni l'autre ne se déduit du
 * catalogue courant.
 *
 * Deux conditions, et les deux comptent :
 *
 * - le pays est une ENCLAVE du pays courant — son emprise tient dans une boîte
 *   de la sienne. C'est la même définition que pour la bascule de pays, lue
 *   dans les emprises sans qu'aucune liste ne la déclare ;
 * - il est DANS LE CADRE, c'est-à-dire réellement visible. Mesuré sur les
 *   catalogues servis : à Rome, tous les lieux italiens dans un rayon de
 *   quatre-vingts kilomètres sont du Latium. Ce qui manque à cette vue ne
 *   vient jamais d'une région voisine — il vient d'un autre pays.
 */

/** Deux boîtes se touchent-elles ? */
export function seTouchent(a: Emprise, b: Emprise): boolean {
  return a[0] <= b[2] && a[2] >= b[0] && a[1] <= b[3] && a[3] >= b[1];
}

/** Le cadre de la carte, en boîte (ouest, sud, est, nord). */
export function enBoite(cadre: EmpriseCarte): Emprise {
  return [cadre[0][0], cadre[0][1], cadre[1][0], cadre[1][1]];
}

/** L'emprise TOTALE d'un pays. */
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
 * Les pays à poser par-dessus le pays courant, pour ce cadre.
 *
 * Pur : ni React, ni réseau. C'est la règle, et c'est elle qu'on éprouve.
 */
export function enclavesDansLeCadre(
  cadre: Emprise | null,
  paysCourant: string,
  connus: PaysConnu[],
): string[] {
  if (!cadre) return [];
  const ici = connus.find((p) => p.code === paysCourant);
  if (!ici) return [];
  return connus
    .filter((autre) => {
      if (autre.code === paysCourant || autre.emprises.length === 0) return false;
      const sienne = tout(autre.emprises);
      if (!sienne) return false;
      // Une ENCLAVE du pays courant, et non un voisin : la France n'apparaît
      // pas sur la carte italienne parce qu'on regarde les Alpes.
      const dedans = ici.emprises.some(
        ([o, s, e, n]) =>
          sienne[0] >= o && sienne[1] >= s && sienne[2] <= e && sienne[3] <= n,
      );
      // Et VISIBLE : le cadre la touche, ou son centre est chez elle.
      return dedans && seTouchent(sienne, cadre);
    })
    .map((autre) => autre.code);
}

/** La note d'un lieu dans SON catalogue, où ses collections vivent. */
export function notesDe(catalogue: Catalog): Map<string, Etoiles> {
  const notes = new Map<string, Etoiles>();
  const noter = (membres: { placeId: string; tier: number }[]) => {
    for (const membre of membres) {
      const note = (4 - membre.tier) as Etoiles;
      const connu = notes.get(membre.placeId);
      if (connu === undefined || note > connu) notes.set(membre.placeId, note);
    }
  };
  // La même règle qu'`etoilesDe` : les collections nationales de thème, et à
  // défaut celle du pays. Un micro-État n'a pas de thème assez fourni.
  const themes = catalogue.collections.filter((c) => c.kind === 'theme' && !c.geoCode);
  if (themes.length) for (const c of themes) noter(c.places);
  else
    for (const c of catalogue.collections)
      if (c.kind === 'geo' && c.geoLevel === 'country') noter(c.places);
  return notes;
}

/** Les lieux d'un pays, marqués de leur origine et de leur note. */
export function lieuxMarques(code: string, catalogue: Catalog): Place[] {
  const notes = notesDe(catalogue);
  return catalogue.places.map((place) => ({
    ...place,
    paysDOrigine: code,
    etoiles: notes.get(place.id) ?? 1,
  }));
}

/**
 * Les lieux des enclaves visibles, téléchargés au besoin.
 *
 * Le téléchargement se déclenche à la VUE, pas au démarrage : vingt et un
 * kilo-octets qu'on ne paie qu'en arrivant sur Rome, et une seule fois.
 */
export function useLieuxDesEnclaves(
  cadre: Emprise | null,
  paysCourant: string,
  connus: PaysConnu[],
): Place[] {
  const codes = useMemo(
    () => enclavesDansLeCadre(cadre, paysCourant, connus),
    [cadre, paysCourant, connus],
  );
  const cle = codes.join(',');
  const [prets, setPrets] = useState(0);
  const demandes = useRef(new Set<string>());

  useEffect(() => {
    const manquants = codes.filter(
      (code) => !dejaCharge(code) && !demandes.current.has(code),
    );
    if (manquants.length === 0) return;
    for (const code of manquants) demandes.current.add(code);
    let annule = false;
    Promise.allSettled(manquants.map((code) => obtenir(code))).then(() => {
      if (!annule) setPrets((n) => n + 1);
    });
    return () => {
      annule = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cle]);

  return useMemo(() => {
    const lieux: Place[] = [];
    for (const code of codes) {
      const catalogue = catalogueDe(code);
      if (catalogue) lieux.push(...lieuxMarques(code, catalogue));
    }
    return lieux;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cle, prets]);
}

/** Le type est réexporté pour que l'appelant n'ait pas deux imports. */
export type { PaysDisponible };
export { dansLEmprise };
