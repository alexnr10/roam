import React from 'react';
import Svg, { Path } from 'react-native-svg';

import type { Emprise } from '../lib/regions';
import { REGIONS, cheminSvg, cheminSvgDans, emprise } from '../lib/regions';
import { colors } from '../theme';
import { REGION_TONES, REGION_TONE_BY_CODE } from './mapStyle';

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
  const ton = REGION_TONES[REGION_TONE_BY_CODE[code] ?? 'lin'];
  return (
    <Svg width={taille} height={taille} viewBox={`-2 -2 ${taille} ${taille}`}>
      <Path d={chemin} fill={ton} stroke="#B49A76" strokeWidth={1} strokeLinejoin="round" />
    </Svg>
  );
}

/**
 * La France métropolitaine en vignette, coloriée par la conquête.
 *
 * Un aplat par région, dans un cadre commun : la Corse reste au sud-est et la
 * Bretagne à l'ouest. C'est la même image que la carte de conquête, en petit —
 * on la reconnaît sans avoir à l'ouvrir, et elle donne une raison de le faire.
 */
export function MiniatureFrance({
  couleurs,
  largeur = 132,
  hauteur = 128,
}: {
  couleurs?: Record<string, string>;
  largeur?: number;
  hauteur?: number;
}) {
  const codes = [...REGIONS.keys()].filter((code) => !OUTRE_MER.has(code));
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
  const cote = Math.min(largeur, hauteur);
  return (
    <Svg width={largeur} height={hauteur} viewBox={`0 0 ${cote} ${cote}`}>
      {codes.map((code) => (
        <Path
          key={code}
          d={cheminSvgDans(REGIONS.get(code)!.geometry, bornes, cote)}
          fill={couleurs?.[code] ?? REGION_TONES[REGION_TONE_BY_CODE[code] ?? 'lin']}
          stroke={colors.surface}
          strokeWidth={1.4}
          strokeLinejoin="round"
        />
      ))}
    </Svg>
  );
}

/** Les cinq régions d'outre-mer : elles ont leur propre place, pas la vignette. */
const OUTRE_MER = new Set(['01', '02', '03', '04', '06']);
