import { useLocalSearchParams, useRouter } from 'expo-router';
import React, { useMemo } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { getCollection, getPlace, themeLabel } from '../../src/data/catalog';
import { computeProgress, nextMilestone } from '../../src/lib/progress';
import { useVisits } from '../../src/store/visits';
import { colors, radius, spacing, themeEmoji, type } from '../../src/theme';
import { Card, Pill, ProgressBar, TierDot } from '../../src/ui/components';
import type { Tier } from '../../src/types';

const TIER_TITLES: Record<Tier, string> = {
  1: 'Niveau 1 · les incontournables',
  2: 'Niveau 2 · la deuxième ligne',
  3: 'Niveau 3 · les pépites',
};

export default function CollectionScreen() {
  const { slug } = useLocalSearchParams<{ slug: string }>();
  const router = useRouter();
  const { visits, visitedIds } = useVisits();

  const collection = slug ? getCollection(slug) : undefined;
  const progress = useMemo(
    () => (collection ? computeProgress(collection, visits) : null),
    [collection, visits],
  );

  if (!collection || !progress) {
    return (
      <View style={styles.centered}>
        <Text style={type.subheading}>Collection introuvable</Text>
      </View>
    );
  }

  const milestone = nextMilestone(progress);

  return (
    <ScrollView
      style={{ backgroundColor: colors.bg }}
      contentContainerStyle={{ padding: spacing.lg, paddingBottom: spacing.xxl }}
    >
      <Text style={type.title}>{collection.name}</Text>

      <Card style={{ marginTop: spacing.lg, gap: spacing.md }}>
        <View style={styles.rowBetween}>
          <Text style={styles.pct}>{progress.pct}%</Text>
          <Text style={type.small}>
            {progress.visited}/{progress.total} lieux · {progress.verified} vérifié
            {progress.verified > 1 ? 's' : ''}
          </Text>
        </View>
        <ProgressBar pct={progress.pct} height={10} />
        {progress.complete ? (
          <Pill label="Collection terminée" tone="verified" />
        ) : milestone ? (
          <Text style={type.small}>
            Prochain palier : {milestone.label} — encore {milestone.remaining} lieu
            {milestone.remaining > 1 ? 'x' : ''}.
          </Text>
        ) : null}
      </Card>

      {([1, 2, 3] as Tier[]).map((tier) => {
        const members = collection.places.filter((member) => member.tier === tier);
        if (members.length === 0) return null;
        const tierProgress = progress.tiers[tier - 1];

        return (
          <View key={tier} style={{ marginTop: spacing.xl }}>
            <View style={styles.tierHead}>
              <TierDot tier={tier} size={12} />
              <Text style={type.subheading}>{TIER_TITLES[tier]}</Text>
            </View>
            <Text style={[type.small, { marginBottom: spacing.md }]}>
              {tierProgress.visited}/{tierProgress.total}
              {/* Le niveau supérieur reste visible mais verrouillé : on doit
                  voir ce qu'on va gagner. */}
              {tierProgress.unlocked ? '' : ' · verrouillé'}
            </Text>

            {members.map((member) => {
              const place = getPlace(member.placeId);
              if (!place) return null;
              const visited = visitedIds.has(place.id);
              return (
                <Pressable
                  key={place.id}
                  style={[styles.row, !tierProgress.unlocked && styles.rowLocked]}
                  onPress={() => router.push(`/place/${place.id}`)}
                >
                  <Text style={styles.emoji}>{themeEmoji[place.themeId] ?? '📍'}</Text>
                  <View style={{ flex: 1 }}>
                    <Text style={type.body} numberOfLines={1}>
                      {place.name}
                    </Text>
                    <Text style={type.small} numberOfLines={1}>
                      {themeLabel(place.themeId)}
                      {place.departement ? ` · ${place.departement}` : ''}
                    </Text>
                  </View>
                  {visited ? <Pill label="Validé" tone="verified" /> : null}
                </Pressable>
              );
            })}
          </View>
        );
      })}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  centered: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  rowBetween: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: spacing.md,
  },
  pct: { fontSize: 32, fontWeight: '700', color: colors.primary },
  tierHead: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    padding: spacing.md,
    marginBottom: spacing.sm,
  },
  rowLocked: { opacity: 0.55 },
  emoji: { fontSize: 20 },
});
