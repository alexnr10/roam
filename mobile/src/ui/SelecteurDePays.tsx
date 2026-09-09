import React from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';

import { usePays } from '../store/pays';
import { colors, radius, spacing, type } from '../theme';

/**
 * De quel pays parle ce catalogue, et comment en changer.
 *
 * INVISIBLE tant qu'un seul pays est disponible. Un sélecteur à une entrée
 * n'est pas un choix, c'est un encombrement — et la règle est la même que
 * pour les adresses de collections côté pipeline, qui ne prennent le suffixe
 * du pays que le jour où il désambiguïse.
 *
 * Quand il apparaît, il dit d'abord OÙ L'ON EST. Changer de pays change tout
 * ce qui est à l'écran ; l'utilisateur doit pouvoir lire l'état courant sans
 * ouvrir quoi que ce soit, sinon il croira que la carte a un défaut.
 */
export function SelecteurDePays() {
  const { pays, disponibles, chargement, erreur, choisir } = usePays();
  if (disponibles.length < 2) return null;

  return (
    <View style={styles.bloc}>
      <Text style={type.small}>Catalogue</Text>
      <View style={styles.rangee}>
        {disponibles.map((entree) => {
          const actif = entree.code === pays;
          return (
            <Pressable
              key={entree.code}
              onPress={() => choisir(entree.code)}
              disabled={chargement}
              accessibilityRole="button"
              accessibilityState={{ selected: actif }}
              accessibilityLabel={`Catalogue ${entree.name}`}
              style={[styles.pastille, actif && styles.pastilleActive]}
            >
              <Text style={[type.body, actif && styles.texteActif]}>{entree.name}</Text>
            </Pressable>
          );
        })}
        {chargement ? <ActivityIndicator color={colors.primary} /> : null}
      </View>
      {/* Un téléchargement peut échouer — c'est même le cas normal en voyage.
          Le dire vaut mieux que de laisser le pays précédent à l'écran sans
          explication. */}
      {erreur ? <Text style={[type.small, styles.erreur]}>{erreur}</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  bloc: { gap: spacing.sm, marginBottom: spacing.lg },
  rangee: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, flexWrap: 'wrap' },
  pastille: {
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  pastilleActive: { backgroundColor: colors.primary, borderColor: colors.primary },
  texteActif: { color: colors.surface },
  erreur: { color: colors.primary },
});
