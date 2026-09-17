import { useEffect, useMemo, useRef, useState } from 'react';

import { places as placesDuPaysCourant } from '../data/catalog';
import {
  catalogueDe,
  dejaCharge,
  obtenir,
  type PaysDisponible,
} from '../data/catalogues';
import { MIN_CARACTERES, search, type Match } from './search';
import type { Place } from '../types';

/**
 * Chercher un lieu sans savoir dans quel pays il est.
 *
 * L'application ne tient qu'UN catalogue actif à la fois, et c'est une
 * décision, pas une limite technique : une étoile dit un rang dans une
 * collection NATIONALE, et mélanger deux pays ferait disputer au Colisée la
 * place du Pont du Gard. La carte, les collections et les étoiles restent
 * donc résolument sur un seul pays.
 *
 * La RECHERCHE est le seul endroit où cette règle dessert l'utilisateur.
 * Personne ne se dit « je vais d'abord passer en Italie, puis chercher le
 * Colisée » : on tape « colisée », et on attend qu'il vienne. Chercher ne
 * classe rien et ne compare rien — c'est retrouver un lieu dont on a le nom en
 * tête. La règle des étoiles n'y est donc pas en jeu.
 *
 * Les catalogues des autres pays sont déjà téléchargeables et déjà mis en
 * cache : `obtenir` sert exactement à cela quand on franchit une frontière.
 * On s'en sert ici pour LIRE sans rendre actif — `catalogueDe` rend le
 * catalogue en mémoire sans toucher à celui qu'affiche la carte.
 */
export type ResultatMondial = Match & {
  /** Le pays où vit ce lieu. Égal au pays courant pour la plupart. */
  pays: string;
  /** Son nom, pour l'afficher quand ce n'est pas celui qu'on regarde. */
  nomDuPays: string;
};

export type RechercheMondiale = {
  resultats: ResultatMondial[];
  /** Un catalogue est en route : d'autres résultats vont venir. */
  chargement: boolean;
};

/**
 * Les catalogues des autres pays, cherchés UNE FOIS par session.
 *
 * Le déclenchement est la première recherche, pas le démarrage : quelqu'un qui
 * ouvre l'application pour regarder la carte autour de lui ne doit pas payer
 * le téléchargement d'un pays qu'il ne cherche pas. Et il n'est payé qu'une
 * fois — `obtenir` garde ce qu'il a lu.
 *
 * Un échec ne dit rien à personne : sans réseau, la recherche rend le pays
 * courant, ce qu'elle a toujours fait. Annoncer « l'Italie est injoignable » à
 * quelqu'un qui cherche « pont du gard » serait du bruit.
 */
function useAutresCatalogues(
  actif: boolean,
  disponibles: PaysDisponible[],
): { prets: number; chargement: boolean } {
  const [prets, setPrets] = useState(0);
  const [chargement, setChargement] = useState(false);
  // Ce qu'on a DÉJÀ demandé, pays par pays — et non un simple « on a demandé ».
  //
  // La distinction a été payée. La liste des pays vient d'`index.json`, donc du
  // réseau, et elle arrive APRÈS le premier rendu : une recherche tapée dans
  // la première seconde ne voyait que le pays embarqué. Avec un drapeau
  // unique, le passage suivant se croyait fait, et l'Italie n'était jamais
  // demandée — de toute la session. Mesuré : « colisée » rendait zéro
  // résultat, indéfiniment.
  const demandes = useRef(new Set<string>());

  useEffect(() => {
    if (!actif) return;
    const manquants = disponibles.filter(
      (pays) => pays.fichier && !dejaCharge(pays.code) && !demandes.current.has(pays.code),
    );
    if (manquants.length === 0) return;
    for (const pays of manquants) demandes.current.add(pays.code);
    let annule = false;
    setChargement(true);
    Promise.allSettled(manquants.map((pays) => obtenir(pays.code))).then(() => {
      if (annule) return;
      setChargement(false);
      setPrets((n) => n + 1);
    });
    return () => {
      annule = true;
    };
  }, [actif, disponibles]);

  return { prets, chargement };
}

/**
 * Les lieux qui répondent, dans tous les pays connus.
 *
 * Le pays COURANT passe devant, à pertinence égale : on cherche neuf fois sur
 * dix là où l'on est, et faire remonter un lieu d'ailleurs devant celui qu'on
 * a sous les yeux serait une surprise désagréable. Les autres suivent, et se
 * disent — la ligne porte le nom de leur pays.
 */
/** Un pays lisible : son code, son nom, et les lieux qu'on peut fouiller. */
export type PaysFouillable = { code: string; name: string; places: Place[] };

/**
 * La fusion, sans React ni réseau — c'est elle qu'on peut éprouver.
 *
 * Le pays COURANT passe devant, à pertinence égale : on cherche neuf fois sur
 * dix là où l'on est, et faire remonter un lieu d'ailleurs devant celui qu'on
 * a sous les yeux serait une surprise désagréable. Les autres suivent, chacun
 * classé par `search`, et se disent — la ligne porte le nom de leur pays.
 */
export function fusionner(
  recherche: string,
  paysCourant: string,
  fouillables: PaysFouillable[],
  limite = 40,
): ResultatMondial[] {
  if (recherche.trim().length < MIN_CARACTERES) return [];
  const marquer = (pays: PaysFouillable): ResultatMondial[] =>
    search(pays.places, recherche, limite).map((match) => ({
      ...match,
      pays: pays.code,
      nomDuPays: pays.name,
    }));

  const ici = fouillables.filter((pays) => pays.code === paysCourant).flatMap(marquer);
  const ailleurs = fouillables.filter((pays) => pays.code !== paysCourant).flatMap(marquer);

  // UN Q-id, UNE ligne — ET C'EST CELLE DU PLUS PETIT PAYS.
  //
  // Deux catalogues peuvent revendiquer le même lieu : la basilique
  // Saint-Pierre est Q12512 en Italie ET au Vatican, tant que la collecte
  // italienne absorbe l'enclave. C'est une faute de données, mais l'écran n'a
  // pas à la répéter.
  //
  // Garder la première occurrence — celle du pays qu'on regarde — était le
  // mauvais sens : la basilique n'apparaissait plus QU'EN ITALIE, ce qu'elle
  // n'est pas. Un doublon de ce genre naît toujours d'un grand catalogue qui a
  // absorbé le lieu d'un petit pays ; c'est donc le petit qui en est le
  // propriétaire. Dix-neuf lieux contre deux mille soixante-neuf : le Vatican
  // gagne, et la ligne porte sa pastille.
  //
  // Le RANG, lui, ne bouge pas : la ligne garde la place que sa pertinence lui
  // a donnée, elle change seulement de pays. Sans quoi Saint-Pierre passerait
  // derrière Saint-Pierre-aux-Liens pour avoir changé de drapeau.
  const taille = new Map(fouillables.map((pays) => [pays.code, pays.places.length]));
  const rang = new Map<string, number>();
  const uniques: ResultatMondial[] = [];
  for (const resultat of [...ici, ...ailleurs]) {
    const deja = rang.get(resultat.place.id);
    if (deja === undefined) {
      rang.set(resultat.place.id, uniques.length);
      uniques.push(resultat);
      continue;
    }
    const ancien = taille.get(uniques[deja].pays) ?? Infinity;
    const nouveau = taille.get(resultat.pays) ?? Infinity;
    if (nouveau < ancien) uniques[deja] = resultat;
  }
  return uniques.slice(0, limite);
}

export function useRechercheMondiale(
  recherche: string,
  paysCourant: string,
  version: number,
  disponibles: PaysDisponible[],
  limite = 40,
): RechercheMondiale {
  const cherche = recherche.trim().length >= MIN_CARACTERES;
  const { prets, chargement } = useAutresCatalogues(cherche, disponibles);

  const resultats = useMemo(() => {
    if (!cherche) return [];
    const fouillables: PaysFouillable[] = [];
    for (const pays of disponibles) {
      // Le pays courant se lit dans `places`, le lien vivant du catalogue
      // actif : `catalogueDe` rendrait celui qui a été TÉLÉCHARGÉ, et le pays
      // embarqué n'est jamais passé par là.
      const lieux =
        pays.code === paysCourant ? placesDuPaysCourant : catalogueDe(pays.code)?.places;
      if (lieux?.length) fouillables.push({ code: pays.code, name: pays.name, places: lieux });
    }
    return fusionner(recherche, paysCourant, fouillables, limite);
  }, [cherche, recherche, paysCourant, version, prets, disponibles, limite]);

  return { resultats, chargement: chargement && cherche };
}
