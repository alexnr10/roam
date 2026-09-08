import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import Svg, { Path } from 'react-native-svg';

import { MENTIONS, type Etoiles as Note } from '../lib/etoiles';
import { colors, type } from '../theme';

/**
 * Une étoile pleine, dessinée.
 *
 * Le glyphe « ★ » d'une police système change de dessin et de chasse d'un
 * téléphone à l'autre : trois étoiles côte à côte y devenaient une rangée
 * irrégulière. Celle-ci est au gabarit des autres icônes, grille de 24.
 */
function Etoile({ taille, couleur }: { taille: number; couleur: string }) {
  return (
    <Svg width={taille} height={taille} viewBox="0 0 24 24">
      <Path d="M12 2.6l2.9 6.1 6.6.9-4.8 4.7 1.2 6.6L12 17.8 6.1 20.9l1.2-6.6L2.5 9.6l6.6-.9z" fill={couleur} />
    </Svg>
  );
}

/**
 * La note d'un lieu : une à trois étoiles.
 *
 * Les étoiles non obtenues ne sont pas dessinées en creux : à trois niveaux, un
 * chapelet de gris ferait ressembler une étoile à un échec. Or tout ce qui est
 * au catalogue a passé la barre — une étoile veut dire « à voir en passant »,
 * pas « médiocre ».
 */
export function Etoiles({
  note,
  taille = 14,
  couleur = colors.primary,
  mention = false,
}: {
  note: Note;
  taille?: number;
  couleur?: string;
  /** Ajoute la mention en toutes lettres : « Vaut le voyage ». */
  mention?: boolean;
}) {
  return (
    <View style={styles.rangee} accessibilityLabel={`${note} étoile${note > 1 ? 's' : ''} — ${MENTIONS[note]}`}>
      {Array.from({ length: note }, (_, index) => (
        <Etoile key={index} taille={taille} couleur={couleur} />
      ))}
      {mention ? <Text style={[type.small, styles.mention]}>{MENTIONS[note]}</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  rangee: { flexDirection: 'row', alignItems: 'center', gap: 2 },
  mention: { marginLeft: 6 },
});
