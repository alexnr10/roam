import { useRouter } from 'expo-router';
import React, { useMemo } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { collections } from '../../src/data/catalog';
import { computeProgress, nextMilestone } from '../../src/lib/progress';
import { useVisits } from '../../src/store/visits';
import { colors, radius, spacing, type } from '../../src/theme';
import { Pill, ProgressBar } from '../../src/ui/components';
import type { CollectionKind } from '../../src/types';

const SECTIONS: Array<{ kind: CollectionKind; title: string; blurb: string }> = [
  { kind: 'theme', title: 'Par thème', blurb: 'Châteaux, cascades, sommets…' },
  { kind: 'label', title: 'Par label', blurb: 'Les listes officielles, déjà curées' },
  { kind: 'geo', title: 'Par géographie', blurb: 'Ta région, ton département, le pays' },
];

export default function CollectionsScreen() {
  const router = useRouter();
  const { visits } = useVisits();

  const progressBySlug = useMemo(() => {
    return new Map(
      collections.map((collection) => [
        collection.slug,
        computeProgress(collection, visits),
      ]),
    );
  }, [visits]);

  return (
    <ScrollView
      style={{ backgroundColor: colors.bg }}
      contentContainerStyle={{ padding: spacing.lg, paddingBottom: spacing.xxl }}
    >
      {SECTIONS.map((section) => {
        const items = collections.filter((c) => c.kind === section.kind);
        if (items.length === 0) return null;

        return (
          <View key={section.kind} style={{ marginBottom: spacing.xl }}>
            <Text style={type.heading}>{section.title}</Text>
            <Text style={[type.small, { marginBottom: spacing.md }]}>{section.blurb}</Text>

            {items
              .map((collection) => ({
                collection,
                progress: progressBySlug.get(collection.slug)!,
              }))
              .sort((a, b) => b.progress.pct - a.progress.pct)
              .map(({ collection, progress }) => {
                const milestone = nextMilestone(progress);
                return (
                  <Pressable
                    key={collection.slug}
                    style={styles.card}
                    onPress={() => router.push(`/collection/${collection.slug}`)}
                  >
                    <View style={styles.cardHead}>
                      <Text style={type.subheading} numberOfLines={1}>
                        {collection.name}
                      </Text>
                      <Text style={styles.pct}>{progress.pct}%</Text>
                    </View>

                    <ProgressBar pct={progress.pct} />

                    <View style={styles.cardFoot}>
                      <Text style={type.small}>
                        {progress.visited}/{progress.total} lieux
                      </Text>
                      {progress.complete ? (
                        <Pill label="Terminée" tone="verified" />
                      ) : milestone ? (
                        <Text style={type.small}>
                          {milestone.label} — encore {milestone.remaining} lieu
                          {milestone.remaining > 1 ? 'x' : ''}
                        </Text>
                      ) : null}
                    </View>
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
  card: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.lg,
    padding: spacing.lg,
    marginBottom: spacing.md,
    gap: spacing.sm,
  },
  cardHead: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  pct: { ...type.subheading, marginLeft: 'auto', color: colors.primary },
  cardFoot: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
});
