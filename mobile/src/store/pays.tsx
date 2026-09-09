import AsyncStorage from '@react-native-async-storage/async-storage';
import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';

import { chargerCatalogue, paysCourant } from '../data/catalog';
import { PAYS, PAYS_EMBARQUE, dejaCharge, obtenir } from '../data/catalogues';

const STORAGE_KEY = 'roam.pays.v1';

/**
 * Le pays qu'on regarde.
 *
 * Un catalogue par pays, un seul à la fois : une étoile dit un rang dans une
 * collection nationale, et qui prépare un voyage en Italie se moque des plages
 * françaises.
 *
 * Deux exigences opposées, et c'est tout le sujet. Il faut pouvoir CHANGER de
 * pays depuis chez soi — on prépare un voyage avant de partir, pas une fois
 * arrivé — et il ne faut pas que ce soit une corvée : un pays déjà chargé
 * revient sans une requête, donc instantanément.
 *
 * Le carnet de visites et la liste d'envies, eux, ne changent PAS : ils sont
 * indexés par identifiant de lieu, qui est mondial. Revenir en France, c'est
 * retrouver ses visites intactes.
 */
type PaysContextValue = {
  /** Le code du pays affiché — « FR », « IT ». */
  pays: string;
  /** Ce que l'application sait proposer. */
  disponibles: typeof PAYS;
  /** Vrai pendant un téléchargement, faux pour un pays déjà en main. */
  chargement: boolean;
  /** Ce qui a échoué, en clair, ou null. */
  erreur: string | null;
  choisir: (code: string) => void;
};

const PaysContext = createContext<PaysContextValue | null>(null);

export function PaysProvider({ children }: { children: React.ReactNode }) {
  const [pays, setPays] = useState(() => paysCourant() || PAYS_EMBARQUE);
  const [chargement, setChargement] = useState(false);
  const [erreur, setErreur] = useState<string | null>(null);

  const appliquer = useCallback(async (code: string) => {
    if (code === paysCourant()) return;
    setErreur(null);
    // Le drapeau ne se lève QUE si l'on va vraiment attendre : le faire
    // clignoter sur un changement instantané donne l'impression d'une lenteur
    // qui n'existe pas.
    if (!dejaCharge(code)) setChargement(true);
    try {
      chargerCatalogue(await obtenir(code));
      setPays(code);
      AsyncStorage.setItem(STORAGE_KEY, code).catch(() => {});
    } catch (souci) {
      setErreur(souci instanceof Error ? souci.message : String(souci));
    } finally {
      setChargement(false);
    }
  }, []);

  useEffect(() => {
    let annule = false;
    AsyncStorage.getItem(STORAGE_KEY)
      .then((garde) => {
        // On ne restaure QUE ce qu'on peut servir sans réseau : rouvrir
        // l'application dans un train sur un pays téléchargé la veille ne doit
        // pas l'ouvrir sur une erreur.
        if (annule || !garde || garde === paysCourant() || !dejaCharge(garde)) return;
        appliquer(garde);
      })
      .catch(() => {});
    return () => {
      annule = true;
    };
  }, [appliquer]);

  const value = useMemo<PaysContextValue>(
    () => ({ pays, disponibles: PAYS, chargement, erreur, choisir: appliquer }),
    [pays, chargement, erreur, appliquer],
  );

  return <PaysContext.Provider value={value}>{children}</PaysContext.Provider>;
}

export function usePays(): PaysContextValue {
  const context = useContext(PaysContext);
  if (!context) throw new Error('usePays doit être utilisé dans <PaysProvider>');
  return context;
}
