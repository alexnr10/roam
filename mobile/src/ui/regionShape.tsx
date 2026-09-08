import React from 'react';
import Svg, { Path } from 'react-native-svg';

import { REGIONS, cheminSvg } from '../lib/regions';
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
