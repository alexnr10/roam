import React from 'react';
import Svg, { Path } from 'react-native-svg';

import { paysCourant, versionDuCatalogue } from '../data/catalog';
import type { Emprise } from '../lib/regions';
import {
  REGIONS,
  cheminSvg,
  cheminSvgDans,
  emprise,
  regionsDuCadre,
  voisinage,
} from '../lib/regions';
import { colors } from '../theme';
import type { TonDeRegion } from './mapStyle';
import { REGION_TONES, tonsDuPays } from './mapStyle';

/**
 * Le coloriage du pays regardé, calculé une fois par catalogue.
 *
 * Il l'était par PAYS, et ce pays était la France : les silhouettes italiennes
 * lisaient `REGION_TONE_BY_CODE`, une table de codes français, et n'y
 * rencontraient que les quelques codes que les deux découpages partagent par
 * hasard. Le reste retombait sur le lin.
 *
 * Le voisinage se déduit des sommets partagés, ce qui coûte un passage sur
 * tous les contours : à l'échelle d'une liste de silhouettes, le refaire à
 * chaque vignette se paierait. On le garde donc tant que le catalogue ne
 * change pas.
 */
let tonsEnCache: Record<string, TonDeRegion> = {};
let versionDesTons = -1;

function tonsCourants(): Record<string, TonDeRegion> {
  const version = versionDuCatalogue();
  if (version !== versionDesTons) {
    tonsEnCache = tonsDuPays(paysCourant(), voisinage());
    versionDesTons = version;
  }
  return tonsEnCache;
}

/**
 * La silhouette d'une région, remplie de son sable.
 *
 * Le même coloriage que sur la carte : une région gardée reconnaissable d'un
 * écran à l'autre, sans avoir à la nommer.
 */
export function SilhouetteRegion({
  code,
  taille = 34,
}: {
  code: string;
  taille?: number;
}) {
  const feature = REGIONS.get(code);
  if (!feature) return null;
  // Tracée sur trente, centrée dans trente-quatre : la silhouette respire, et
  // deux régions voisines dans la liste ne se touchent pas.
  const interieur = taille - 4;
  const chemin = cheminSvg(feature.geometry, interieur);
  const ton = REGION_TONES[tonsCourants()[code] ?? 'lin'];
  return (
    <Svg width={taille} height={taille} viewBox={`-2 -2 ${taille} ${taille}`}>
      <Path d={chemin} fill={ton} stroke="#B49A76" strokeWidth={1} strokeLinejoin="round" />
    </Svg>
  );
}

/**
 * Le pays regardé en vignette, colorié par la conquête.
 *
 * Un aplat par région, dans un cadre commun : la Corse reste au sud-est et la
 * Bretagne à l'ouest. C'est la même image que la carte de conquête, en petit —
 * on la reconnaît sans avoir à l'ouvrir, et elle donne une raison de le faire.
 */
export function MiniaturePays({
  couleurs,
  cote = 124,
}: {
  couleurs?: Record<string, string>;
  /**
   * Le côté de la vignette. CARRÉ, parce que le contenu l'est : projetée comme
   * sur la carte, la France métropolitaine tient dans un carré, Corse comprise.
   * Un cadre plus large laissait une bande vide et faisait flotter la Corse
   * contre le texte voisin.
   */
  cote?: number;
}) {
  // Les régions du CADRE, et pas une liste de codes.
  //
  // C'était `OUTRE_MER`, cinq codes français — 01 à 04 et 06 — écrits pour
  // sortir la Guadeloupe et Mayotte d'une vignette qu'elles auraient étirée sur
  // deux océans. Appliqués à l'Italie, ces mêmes codes sont le Piémont, le Val
  // d'Aoste, la Lombardie, le Trentin et le Frioul : la vignette italienne
  // perdait tout son nord.
  //
  // `bornesDuPays` cadre déjà sur les régions qui portent l'essentiel des
  // lieux, et c'est le même cadre que la carte à l'ouverture. On garde ce qui
  // s'y trouve, quel que soit le pays.
  const codes = regionsDuCadre();
  // Le cadre commun : l'emprise de toutes les régions dessinées, réunies.
  const bornes = codes.reduce<Emprise>(
    (acc, code) => {
      const b = emprise(REGIONS.get(code)!.geometry);
      return [
        [Math.min(acc[0][0], b[0][0]), Math.min(acc[0][1], b[0][1])],
        [Math.max(acc[1][0], b[1][0]), Math.max(acc[1][1], b[1][1])],
      ];
    },
    [
      [180, 90],
      [-180, -90],
    ],
  );
  return (
    <Svg width={cote} height={cote} viewBox={`0 0 ${cote} ${cote}`}>
      {codes.map((code) => (
        <Path
          key={code}
          d={cheminSvgDans(REGIONS.get(code)!.geometry, bornes, cote)}
          fill={couleurs?.[code] ?? REGION_TONES[tonsCourants()[code] ?? 'lin']}
          stroke={colors.surface}
          strokeWidth={1.4}
          strokeLinejoin="round"
        />
      ))}
    </Svg>
  );
}

