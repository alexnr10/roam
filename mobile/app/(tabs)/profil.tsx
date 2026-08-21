import React, { useMemo } from 'react';
import { Alert, ScrollView, StyleSheet, Text, View } from 'react-native';

import { collections, places } from '../../src/data/catalog';
import { computeProgress, earnedBadges, type Badge } from '../../src/lib/progress';
import { useVisits } from '../../src/store/visits';
import { colors, radius, spacing, type } from '../../src/theme';
import { Button, Card, EmptyState, Pill } from '../../src/ui/components';

export default function ProfileScreen() {
  const { visits, reset } = useVisits();

  const verified = visits.filter((visit) => visit.verified).length;

  const badges = useMemo<Badge[]>(() => {
    return collections.flatMap((collection) =>
      earnedBadges(collection, computeProgress(collection, visits)),
    );
  }, [visits]);

  const confirmReset = () =>
    Alert.alert(
      'Tout effacer ?',
      'Tes validations et tes badges seront perdus. Cette action est définitive.',
      [
        { text: 'Annuler', style: 'cancel' },
        { text: 'Effacer', style: 'destructive', onPress: reset },
      ],
    );

  return (
    <ScrollView
      style={{ backgroundColor: colors.bg }}
      contentContainerStyle={{ padding: spacing.lg, paddingBottom: spacing.xxl }}
    >
      <View style={styles.stats}>
        <Stat value={visits.length} label="lieux validés" />
        {/* Déclaré vs vérifié : les deux comptent, seul le second est prouvé. */}
        <Stat value={verified} label="dont vérifiés GPS" />
        <Stat value={badges.length} label="badges" />
      </View>

      <Text style={[type.heading, { marginBottom: spacing.md }]}>Badges</Text>

      {badges.length === 0 ? (
        <Card>
          <EmptyState
            title="Aucun badge pour l'instant"
            body="Valide tes premiers lieux : les badges tombent dès 25 % d'une collection, et à chaque niveau terminé."
          />
        </Card>
      ) : (
        <View style={styles.badges}>
          {badges.map((badge) => (
            <View key={badge.id} style={styles.badge}>
              <Text style={styles.badgeGlyph}>{badge.kind === 'tier' ? '🏅' : '🎖️'}</Text>
              <View style={{ flex: 1 }}>
                <Text style={type.body} numberOfLines={1}>
                  {badge.collectionName}
                </Text>
                <Text style={type.small}>{badge.label}</Text>
              </View>
            </View>
          ))}
        </View>
      )}

      <View style={{ marginTop: spacing.xl, gap: spacing.md }}>
        <Text style={type.small}>
          Catalogue de démonstration : {places.length} lieux, {collections.length}{' '}
          collections.
        </Text>
        <Pill label="Prototype" tone="muted" />
        <Button label="Effacer mes données" tone="secondary" onPress={confirmReset} />
      </View>
    </ScrollView>
  );
}

function Stat({ value, label }: { value: number; label: string }) {
  return (
    <View style={styles.stat}>
      <Text style={styles.statValue}>{value}</Text>
      <Text style={[type.small, { textAlign: 'center' }]}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  stats: { flexDirection: 'row', gap: spacing.md, marginBottom: spacing.xl },
  stat: {
    flex: 1,
    alignItems: 'center',
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.lg,
    paddingVertical: spacing.lg,
    paddingHorizontal: spacing.sm,
    gap: spacing.xs,
  },
  statValue: { fontSize: 26, fontWeight: '700', color: colors.primary },
  badges: { gap: spacing.sm },
  badge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    padding: spacing.md,
  },
  badgeGlyph: { fontSize: 22 },
});
