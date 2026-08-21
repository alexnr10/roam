import { useLocalSearchParams, useRouter } from 'expo-router';
import React, { useMemo } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import {
  getCollectionsForPlace,
  getPlace,
  getTierForPlace,
  themeLabel,
} from '../../src/data/catalog';
import { evaluateCheckIn } from '../../src/lib/checkin';
import { formatDistance } from '../../src/lib/geo';
import { computeProgress } from '../../src/lib/progress';
import { useLocation } from '../../src/lib/useLocation';
import { useVisits } from '../../src/store/visits';
import { colors, radius, spacing, themeEmoji, type } from '../../src/theme';
import { Button, Card, Pill, ProgressBar, TierDot } from '../../src/ui/components';

export default function PlaceScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const { visits, visitedIds, addVisit, removeVisit } = useVisits();
  const { position } = useLocation();

  const place = id ? getPlace(id) : undefined;

  const memberships = useMemo(
    () => (place ? getCollectionsForPlace(place.id) : []),
    [place],
  );

  if (!place) {
    return (
      <View style={styles.centered}>
        <Text style={type.subheading}>Lieu introuvable</Text>
      </View>
    );
  }

  const visited = visitedIds.has(place.id);
  const visit = visits.find((entry) => entry.placeId === place.id);
  const evaluation = evaluateCheckIn(place, position);

  return (
    <ScrollView
      style={{ backgroundColor: colors.bg }}
      contentContainerStyle={{ padding: spacing.lg, paddingBottom: spacing.xxl }}
    >
      <Text style={styles.emoji}>{themeEmoji[place.themeId] ?? '📍'}</Text>
      <Text style={type.title}>{place.name}</Text>
      <Text style={[type.small, { marginTop: spacing.xs }]}>
        {themeLabel(place.themeId)}
        {place.departement ? ` · ${place.departement}` : ''}
      </Text>

      {place.summary ? (
        <Text style={[type.body, styles.summary]}>{place.summary}</Text>
      ) : null}

      <Card style={{ marginTop: spacing.lg, gap: spacing.md }}>
        {visited ? (
          <>
            <View style={styles.rowBetween}>
              <Pill
                label={visit?.verified ? 'Visite vérifiée' : 'Visite déclarée'}
                tone={visit?.verified ? 'verified' : 'neutral'}
              />
              {evaluation.distanceM !== null ? (
                <Text style={type.small}>{formatDistance(evaluation.distanceM)}</Text>
              ) : null}
            </View>
            <Button
              label="Retirer cette visite"
              tone="secondary"
              onPress={() => removeVisit(place.id)}
            />
          </>
        ) : (
          <>
            <View style={styles.rowBetween}>
              <Text style={type.body}>{evaluation.message}</Text>
              {/* Le rayon porte la taille du site : 120 m pour une cathédrale,
                  2 km pour des gorges. */}
              <Text style={type.small}>rayon {place.radiusM} m</Text>
            </View>

            <Button
              label={evaluation.canCheckIn ? 'Je suis sur place' : 'Trop loin pour valider'}
              disabled={!evaluation.canCheckIn}
              onPress={() => addVisit(place, 'gps', evaluation.distanceM ?? undefined)}
            />

            {/* Sans ça, l'utilisateur démarre à 0 % partout et décroche. */}
            <Button
              label="J'y suis déjà allé"
              tone="secondary"
              onPress={() => addVisit(place, 'declared')}
            />
            <Text style={[type.small, { textAlign: 'center' }]}>
              Une visite déclarée compte dans tes pourcentages, mais n'est pas
              marquée « vérifiée ».
            </Text>
          </>
        )}
      </Card>

      <Text style={[type.heading, { marginTop: spacing.xl, marginBottom: spacing.md }]}>
        Compte dans {memberships.length} collection{memberships.length > 1 ? 's' : ''}
      </Text>

      {memberships.map((collection) => {
        const tier = getTierForPlace(collection, place.id);
        const progress = computeProgress(collection, visits);
        return (
          <Pressable
            key={collection.slug}
            style={styles.collectionRow}
            onPress={() => router.push(`/collection/${collection.slug}`)}
          >
            <View style={styles.rowBetween}>
              <View style={styles.tierLabel}>
                {tier ? <TierDot tier={tier} /> : null}
                <Text style={type.body} numberOfLines={1}>
                  {collection.name}
                </Text>
              </View>
              <Text style={type.small}>{progress.pct}%</Text>
            </View>
            <ProgressBar
              pct={progress.pct}
              color={tier ? colors.tier[tier - 1] : colors.primary}
              height={6}
            />
            {tier ? <Text style={type.small}>Niveau {tier} de cette collection</Text> : null}
          </Pressable>
        );
      })}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  centered: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  emoji: { fontSize: 40, marginBottom: spacing.sm },
  summary: { marginTop: spacing.md, lineHeight: 22 },
  rowBetween: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: spacing.md,
  },
  tierLabel: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, flex: 1 },
  collectionRow: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    padding: spacing.md,
    marginBottom: spacing.sm,
    gap: spacing.sm,
  },
});
