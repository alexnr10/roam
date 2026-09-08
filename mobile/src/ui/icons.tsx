import React from 'react';
import Svg, { Path } from 'react-native-svg';

import { colors } from '../theme';

/**
 * Les icônes de l'interface — celles qui ne sont pas des thèmes.
 *
 * Même gabarit que `themeIcons` : grille de 24, ligne seule, épaisseur 2,
 * bouts et angles arrondis. Un emoji est rendu par le système, donc jamais deux
 * fois pareil d'un téléphone à l'autre : couleur, épaisseur et cadrage
 * changent, et la barre d'onglets d'une application de voyage y ressemblait à
 * un clavier de messagerie.
 *
 * En SVG dans le code : la page publiée est un fichier unique, une police
 * d'icônes ou un fichier distant y ajouterait une dépendance réseau.
 */

type Props = {
  size?: number;
  color?: string;
  strokeWidth?: number;
};

function Trace({ d, size = 24, color = colors.text, strokeWidth = 2 }: Props & { d: string[] }) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24">
      {d.map((trace, index) => (
        <Path
          key={index}
          d={trace}
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

/** Onglet Carte : une carte pliée. */
export const IconeCarte = (props: Props) => (
  <Trace
    {...props}
    d={[
      'M2.5 6.5 9 4l6 2.5L21.5 4v13.5L15 20l-6-2.5-6.5 2.5z',
      'M9 4v13.5',
      'M15 6.5V20',
    ]}
  />
);

/** Onglet Explorer : une boussole. */
export const IconeBoussole = (props: Props) => (
  <Trace
    {...props}
    d={['M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18z', 'm15.5 8.5-2 5-5 2 2-5z']}
  />
);

/** Onglet Moi : un jalon planté. */
export const IconeJalon = (props: Props) => (
  <Trace
    {...props}
    d={[
      'M12 21V4',
      'M12 4h7l-2 3 2 3h-7',
      'M8.5 21h7',
    ]}
  />
);

/** La loupe de la recherche. */
export const IconeLoupe = (props: Props) => (
  <Trace {...props} d={['M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14z', 'm16.2 16.2 4 4']} />
);

/** Le chevron de retour, pointe à gauche. */
export const IconeChevron = (props: Props) => <Trace {...props} d={['m14.5 5-7 7 7 7']} />;

/** La croix de fermeture. */
export const IconeCroix = (props: Props) => (
  <Trace {...props} d={['m6 6 12 12', 'm18 6-12 12']} />
);

/** Le chevron d'une ligne de liste, pointe à droite. */
export const IconeChevronDroit = (props: Props) => <Trace {...props} d={['m9.5 5 7 7-7 7']} />;

/** Une rosette : le badge, dessiné. */
export const IconeRosette = (props: Props) => (
  <Trace
    {...props}
    d={['M12 3a6 6 0 1 0 0 12 6 6 0 0 0 0-12z', 'M8.5 14.5 7 21l5-2.5 5 2.5-1.5-6.5']}
  />
);
