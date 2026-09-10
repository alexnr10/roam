import React from 'react';
import Svg, { Path } from 'react-native-svg';

import { colors } from '../theme';

/**
 * Les 23 thèmes en icônes dessinées.
 *
 * Elles remplacent les emoji : un emoji est rendu par le système, donc jamais
 * deux fois pareil (couleur, épaisseur, cadrage), et `⛪` servait pour les
 * abbayes ET les cathédrales. Ici les 23 thèmes ont chacun un signe, tous
 * tracés dans la même grille de 24, à la même épaisseur.
 *
 * En SVG en ligne, sans fichier : le web est un seul HTML inliné, aucune image
 * ni police d'icônes ne doit être téléchargée. Demande `react-native-svg`
 * (`npx expo install react-native-svg`), qui rend aussi sur le web.
 *
 * Les tracés sont en LIGNE, jamais en aplat : une icône pleine à 18 points se
 * referme et devient une tache, et il en faut 23 sur une même rangée.
 */
/**
 * Les tracés, à la disposition de la carte aussi.
 *
 * MapLibre ne sait pas dessiner un composant React : il lui faut des IMAGES.
 * Les mêmes chemins servent donc aux deux — une icône de thème est la même
 * qu'on la voie sur une pastille de filtre ou posée sur la carte.
 */
export const TRACES: Record<string, string[]> = {
  chateaux: [
    'M4 20V10h16v10',
    'M4 10V6h3v2.5h3.5V6h3v2.5H17V6h3v4',
    'M10 20v-4.5a2 2 0 0 1 4 0V20',
  ],
  abbayes: [
    'M6 20v-8a6 6 0 0 1 12 0v8',
    'M12 2.5v4',
    'M10 4.5h4',
    'M12 20v-5',
  ],
  cathedrales: [
    'M4 20v-9l3.5-4L11 11v9',
    'M13 20v-9l3.5-4L20 11v9',
    'M11 20v-5a1 1 0 0 1 2 0v5',
    'M7.5 7V4.5',
    'M16.5 7V4.5',
  ],
  // La piazza : un thème que la France n'a pas. Ici une place est un
  // carrefour ; en Italie c'est une destination.
  //
  // Ce qui la définit n'est pas un édifice mais une COMPOSITION : un vide
  // encadré de façades basses, avec quelque chose au centre. Le glyphe la
  // rend donc en trois masses sur une ligne de sol — l'obélisque seul serait
  // « monuments ». Cinq variantes ont été rendues à 90, 22 et 14 pixels avant
  // celle-ci : la fontaine devenait illisible sous 22, et l'arcade se
  // confondait avec « abbayes ».
  piazzas: [
    'M2 20h20',
    'M11 20V8.5l1-2.5 1 2.5V20',
    'M2.5 20v-5.5h5.5V20',
    'M16 20v-5.5h5.5V20',
  ],
  villages: [
    'M2 20v-6l4.5-3.5L11 14v6',
    'M11 20v-8l5-4 5 4v8',
    'M14.5 20v-4h3v4',
  ],
  sommets: [
    'M2 19 9 6l4.5 8L16 10l6 9z',
    'M6.6 13.6 9 11.6l2 1.7',
  ],
  cascades: [
    'M4 4.5h16',
    'M8 4.5v9',
    'M12 4.5v11',
    'M16 4.5v9',
    'M3.5 18.5c3 2 5.5-1 8.5 0s5.5 2 8.5 0',
  ],
  gorges: [
    'M4 3l3 8-3 10',
    'M20 3l-3 8 3 10',
    'M12 7c-2 3.5 2 5.5 0 10',
  ],
  plages: [
    'M17.5 6.5a2.5 2.5 0 1 1-.01 0',
    'M2.5 14c2.2-1.6 4.3-1.6 6.5 0s4.3 1.6 6.5 0 4.3-1.6 6-.4',
    'M2.5 19c2.2-1.6 4.3-1.6 6.5 0s4.3 1.6 6.5 0 4.3-1.6 6-.4',
  ],
  grottes: [
    'M3 21c0-8.5 4-14.5 9-14.5S21 12.5 21 21',
    'M9 21c0-4.5 1.3-7.5 3-7.5s3 3 3 7.5',
    'M8 10.5l1.2 2',
    'M12.5 9l1.2 2',
  ],
  lacs: [
    'M12 8.5c4.4 0 8 2.2 8 5s-3.6 5-8 5-8-2.2-8-5 3.6-5 8-5',
    'M8.5 13.5c1.4-.8 2.6-.8 4 0s2.6.8 4 0',
  ],
  ponts: [
    'M2.5 9.5h19',
    'M6 9.5c0 3.6 2.7 6.5 6 6.5s6-2.9 6-6.5',
    'M4.5 9.5V20',
    'M19.5 9.5V20',
  ],
  phares: [
    'M9.5 20 10.5 9h3l1 11z',
    'M10.5 9V6.5h3V9',
    'M12 4V2.5',
    'M6.5 4.5 8 5.5',
    'M17.5 4.5 16 5.5',
    'M7.5 20h9',
  ],
  monuments: [
    'M10 20V7l2-4.5L14 7v13',
    'M7 20h10',
    'M10 11h4',
  ],
  musees: [
    'M2.5 9.5 12 4l9.5 5.5',
    'M6 9.5v9',
    'M10 9.5v9',
    'M14 9.5v9',
    'M18 9.5v9',
    'M3 20h18',
  ],
  maisons: [
    'M4 11 12 5l8 6v9H4z',
    'M10 20v-5h4v5',
  ],
  jardins: [
    'M12 21v-7',
    'M12 17c-2.2 0-3.5-1.2-3.5-3',
    'M12 16c2.2 0 3.5-1.2 3.5-3',
    'M9 9.5a3 3 0 0 1 6 0c0 2-1.3 3.5-3 3.5s-3-1.5-3-3.5',
    'M4 21h16',
  ],
  megalithes: [
    'M3.5 8.5 20.5 6',
    'M6.5 21V8.8',
    'M18 21V6.5',
    'M12 21v-11',
  ],
  iles: [
    'M3 18.5c2.5-4 5.5-6 9-6s6.5 2 9 6',
    'M13 17c0-3.5 1-5.5 2.5-6.5',
    'M15.5 10.5c-2-1-4 .3-4 .3',
    'M15.5 10.5c.6-2 2.8-2.4 2.8-2.4',
    'M15.5 10.5c1.8-.3 3.2.8 3.2.8',
  ],
  volcans: [
    'M3 20 9 9h6l6 11z',
    'M10.5 6c0-2 3.5-1.6 3.5-3.5',
    'M14.5 5.5c0-1.4 2-1.2 2-2.5',
  ],
  forets: [
    'M12 21v-3.5',
    'M12 17.5H7L12 8l5 9.5z',
    'M12 12.5H9.2L12 7l2.8 5.5z',
    'M5 21h14',
  ],
  cirques: [
    'M3.5 20a8.5 8.5 0 0 1 17 0',
    'M7 20a5 5 0 0 1 10 0',
    'M10.5 20a1.5 1.5 0 0 1 3 0',
  ],
  "dunes-marais": [
    'M2 18.5c4-6 8-6 10-2s6 4 10-2',
    'M7.5 15v-5',
    'M11 13.5v-7',
    'M14.5 14.5v-4',
    'M2 21h20',
  ],
  rochers: [
    'M2.5 20 8 10l5.5 10z',
    'M12 20l4.5-7L21 20z',
  ],
};

export const THEME_IDS = Object.keys(TRACES);

export function ThemeIcon({
  themeId,
  size = 22,
  color = colors.text,
  strokeWidth = 2,
}: {
  themeId: string;
  size?: number;
  color?: string;
  strokeWidth?: number;
}) {
  const traces = TRACES[themeId];
  if (!traces) return null;
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24">
      {traces.map((d, i) => (
        <Path
          key={i}
          d={d}
          stroke={color}
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeLinejoin="round"
          fill="none"
        />
      ))}
    </Svg>
  );
}

/** Le nom court d'un thème, pour l'étiquette sous l'icône. */
export const THEME_LABELS: Record<string, string> = {
  chateaux: "Châteaux",
  abbayes: "Abbayes",
  cathedrales: "Cathédrales",
  piazzas: "Places",
  villages: "Villages",
  sommets: "Sommets",
  cascades: "Cascades",
  gorges: "Gorges",
  plages: "Plages",
  grottes: "Grottes",
  lacs: "Lacs",
  ponts: "Ponts",
  phares: "Phares",
  monuments: "Monuments",
  musees: "Musées",
  maisons: "Maisons",
  jardins: "Jardins",
  megalithes: "Mégalithes",
  iles: "Îles",
  volcans: "Volcans",
  forets: "Forêts",
  cirques: "Cirques",
  "dunes-marais": "Dunes et marais",
  rochers: "Rochers",
};
