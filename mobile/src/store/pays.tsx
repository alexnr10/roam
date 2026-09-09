import AsyncStorage from '@react-native-async-storage/async-storage';
import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';

import { chargerCatalogue, paysCourant } from '../data/catalog';
import { PAYS, PAYS_EMBARQUE, dejaCharge, lireIndex, obtenir, obtenirContours } from '../data/catalogues';
import { chargerContours } from '../data/outlines';
import { paysAAdopter } from '../lib/pays';

const STORAGE_KEY = 'roam.pays.v1';

/**
 * Le pays qu'on regarde — et qui change tout seul.
 *
 * Un catalogue par pays, un seul à la fois : une étoile dit un rang dans une
 * collection nationale, et qui prépare un voyage en Italie se moque des plages
 * françaises.
 *
 * La bascule est INVISIBLE. Elle ne se demande pas, elle s'observe : la carte
 * dit où l'on regarde, et le catalogue suit. Se promener jusqu'à Turin charge
 * l'Italie sans rien réclamer à personne — et revenir en France ne redemande
 * rien, le catalogue précédent étant resté en main.
 *
 * Le carnet de visites et la liste d'envies, eux, ne bougent pas : ils sont
 * indexés par identifiant de lieu, qui est mondial.
 */
type PaysContextValue = {
  /** Le code du pays affiché — « FR », « IT ». */
  pays: string;
  /**
   * Change à CHAQUE catalogue chargé. Les écrans qui dérivent du catalogue le
   * mettent dans leurs dépendances : c'est ce qui les refait sans remonter la
   * navigation — remonter la pile en pleine promenade rendrait la carte à son
   * point de départ, ce qui est exactement le contraire d'invisible.
   */
  version: number;
  disponibles: typeof PAYS;
  chargement: boolean;
  erreur: string | null;
  /** Choix explicite, depuis un réglage. */
  choisir: (code: string) => void;
  /** Ce que la carte regarde. Bascule toute seule s'il le faut. */
  regarder: (lon: number, lat: number) => void;
};

const PaysContext = createContext<PaysContextValue | null>(null);

export function PaysProvider({ children }: { children: React.ReactNode }) {
  const [pays, setPays] = useState(() => paysCourant() || PAYS_EMBARQUE);
  const [version, setVersion] = useState(0);
  const [chargement, setChargement] = useState(false);
  const [erreur, setErreur] = useState<string | null>(null);
  const [connus, setConnus] = useState(() => [...PAYS]);
  // Une bascule à la fois : `moveend` part à chaque geste, et deux
  // téléchargements concurrents du même pays se marcheraient dessus.
  const enCours = useRef<string | null>(null);

  const appliquer = useCallback(async (code: string) => {
    if (code === paysCourant() || enCours.current === code) return;
    enCours.current = code;
    setErreur(null);
    // Le drapeau ne se lève QUE si l'on va vraiment attendre : le faire
    // clignoter sur une bascule instantanée donne l'impression d'une lenteur
    // qui n'existe pas.
    if (!dejaCharge(code)) setChargement(true);
    try {
      const catalogue = await obtenir(code);
      // Les contours AVANT le catalogue, et l'ordre n'est pas indifférent :
      // c'est le catalogue qui déclenche la reconstruction de tout ce qui en
      // dérive, dont la table des régions, qui lit les contours. Dans l'autre
      // sens, la carte garderait un tour les frontières du pays précédent.
      chargerContours(await obtenirContours(code));
      chargerCatalogue(catalogue);
      setPays(code);
      setVersion((n) => n + 1);
      AsyncStorage.setItem(STORAGE_KEY, code).catch(() => {});
    } catch (souci) {
      setErreur(souci instanceof Error ? souci.message : String(souci));
    } finally {
      enCours.current = null;
      setChargement(false);
    }
  }, []);

  useEffect(() => {
    let annule = false;
    lireIndex().then((liste) => {
      if (!annule) setConnus([...liste]);
    });
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

  const regarder = useCallback(
    (lon: number, lat: number) => {
      const cible = paysAAdopter(lon, lat, paysCourant() || PAYS_EMBARQUE, connus);
      if (cible) appliquer(cible);
    },
    [connus, appliquer],
  );

  const value = useMemo<PaysContextValue>(
    () => ({ pays, version, disponibles: connus, chargement, erreur, choisir: appliquer, regarder }),
    [pays, version, connus, chargement, erreur, appliquer, regarder],
  );

  return <PaysContext.Provider value={value}>{children}</PaysContext.Provider>;
}

export function usePays(): PaysContextValue {
  const context = useContext(PaysContext);
  if (!context) throw new Error('usePays doit être utilisé dans <PaysProvider>');
  return context;
}
