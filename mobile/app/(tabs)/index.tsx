import { useRouter } from 'expo-router';
import React, { useMemo, useState } from 'react';
import { FlatList, Platform, Pressable, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { places as allPlaces, themeLabel, themes } from '../../src/data/catalog';
import { evaluateCheckIn, suggestCheckIn } from '../../src/lib/checkin';
import { distanceToPlace, formatDistance } from '../../src/lib/geo';
import { useCheckIn } from '../../src/lib/useCheckIn';
import { useLocation } from '../../src/lib/useLocation';
import { useVisits } from '../../src/store/visits';
import { colors, spacing, radius, type, themeEmoji } from '../../src/theme';
import { Button, ChipRow, Pill, SegmentedControl } from '../../src/ui/components';
import { MapCanvas } from '../../src/ui/MapCanvas';
import type { Place } from '../../src/types';

type Filter = 'all' | 'todo' | 'done';

export default function MapScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { visitedIds } = useVisits();
  const checkIn = useCheckIn();
  const { position, granted, simulated } = useLocation();
  const [filter, setFilter] = useState<Filter>('all');
  const [theme, setTheme] = useState<string | null>(null);

  const visible = useMemo(() => {
    // Le thème d'abord : c'est lui qui dit ce qu'on cherche, l'état de
    // validation ne fait que trancher dans cette recherche.
    const scope = theme ? allPlaces.filter((p) => p.themeId === theme) : allPlaces;
    if (filter === 'todo') return scope.filter((p) => !visitedIds.has(p.id));
    if (filter === 'done') return scope.filter((p) => visitedIds.has(p.id));
    return scope;
  }, [filter, theme, visitedIds]);

  const themeOptions = useMemo(
    () => [
      { value: null, label: 'Tous les thèmes' },
      ...themes
        .map((entry) => ({ value: entry.id, label: entry.name }))
        .sort((a, b) => a.label.localeCompare(b.label, 'fr')),
    ],
    [],
  );

  /**
   * Lieux les plus proches, dans l'ordre. Sans position, on affiche quand même
   * une liste — un catalogue muet serait pire qu'une liste non triée.
   */
  const listed = useMemo<Array<{ place: Place; distanceM: number | null }>>(() => {
    if (!position) return visible.slice(0, 30).map((place) => ({ place, distanceM: null }));
    return visible
      .map((place) => ({ place, distanceM: distanceToPlace(position, place) }))
      .sort((a, b) => (a.distanceM ?? 0) - (b.distanceM ?? 0))
      .slice(0, 30);
  }, [visible, position]);

  // La validation vient à l'utilisateur, pas l'inverse.
  const suggestion = useMemo(
    () => suggestCheckIn(allPlaces, position, visitedIds),
    [position, visitedIds],
  );

  const openPlace = (place: Place) => router.push(`/place/${place.id}`);

  return (
    <View style={[styles.screen, { paddingTop: insets.top }]}>
      <View style={styles.header}>
        <Text style={type.title}>Roam</Text>
        <Text style={type.small}>
          {visitedIds.size} lieu{visitedIds.size > 1 ? 'x' : ''} validé
          {visitedIds.size > 1 ? 's' : ''} sur {allPlaces.length}
        </Text>
      </View>

      <View style={styles.controls}>
        <SegmentedControl<Filter>
          value={filter}
          onChange={setFilter}
          options={[
            { value: 'all', label: 'Tous' },
            { value: 'todo', label: 'À visiter' },
            { value: 'done', label: 'Visités' },
          ]}
        />
        {/* Vingt-trois thèmes : une rangée défilante plutôt qu'un contrôle
            segmenté, qui n'en tient que quatre. */}
        <ChipRow options={themeOptions} value={theme} onChange={setTheme} />
      </View>

      <View style={styles.map}>
        <MapCanvas
          places={visible}
          visitedIds={visitedIds}
          position={position}
          onSelectPlace={openPlace}
          highlightedId={suggestion?.id ?? null}
        />
      </View>

      {suggestion ? (
        <View style={styles.suggestion}>
          <View style={{ flex: 1 }}>
            <Text style={styles.suggestionKicker}>TU Y ES</Text>
            <Text style={type.subheading} numberOfLines={1}>
              {suggestion.name}
            </Text>
          </View>
          <Button
            label="Valider"
            onPress={() => {
              const evaluation = evaluateCheckIn(suggestion, position);
              checkIn(suggestion, 'gps', evaluation.distanceM ?? undefined);
            }}
          />
        </View>
      ) : null}

      {Platform.OS === 'web' ? (
        <View style={styles.notice}>
          <Text style={type.small}>
            {simulated
              ? 'Mode démo : ta position est simulée. Ouvre un autre lieu pour t’y téléporter.'
              : 'Aperçu web. Ouvre un lieu et utilise « me téléporter ici » pour éprouver la validation sans faire la route.'}
          </Text>
        </View>
      ) : null}

      {granted === false && Platform.OS !== 'web' ? (
        <View style={styles.notice}>
          <Text style={type.small}>
            Localisation refusée — tu peux quand même parcourir la carte et cocher
            les lieux déjà visités.
          </Text>
        </View>
      ) : null}

      <FlatList
        data={listed}
        keyExtractor={(entry) => entry.place.id}
        style={styles.list}
        contentContainerStyle={{ paddingBottom: spacing.xl }}
        ListHeaderComponent={
          <Text style={[type.tiny, styles.listHeader]}>
            {position ? 'AUTOUR DE MOI' : 'CATALOGUE'}
          </Text>
        }
        renderItem={({ item }) => {
          const visited = visitedIds.has(item.place.id);
          return (
            <Pressable style={styles.row} onPress={() => openPlace(item.place)}>
              <Text style={styles.rowEmoji}>{themeEmoji[item.place.themeId] ?? '📍'}</Text>
              <View style={{ flex: 1 }}>
                <Text style={type.body} numberOfLines={1}>
                  {item.place.name}
                </Text>
                <Text style={type.small} numberOfLines={1}>
                  {themeLabel(item.place.themeId)}
                  {item.place.departement ? ` · ${item.place.departement}` : ''}
                </Text>
              </View>
              {visited ? (
                <Pill label="Validé" tone="verified" />
              ) : item.distanceM !== null ? (
                <Text style={type.small}>{formatDistance(item.distanceM)}</Text>
              ) : null}
            </Pressable>
          );
        }}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  header: { paddingHorizontal: spacing.lg, paddingTop: spacing.sm },
  controls: { paddingHorizontal: spacing.lg, paddingVertical: spacing.md },
  map: {
    // La France, dans cette projection, est presque carrée : un cadre carré la
    // cadre au plus juste sans marges perdues.
    aspectRatio: 1,
    marginHorizontal: spacing.lg,
    borderRadius: radius.lg,
    overflow: 'hidden',
    backgroundColor: colors.surfaceAlt,
  },
  suggestion: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    margin: spacing.lg,
    marginBottom: 0,
    padding: spacing.md,
    borderRadius: radius.lg,
    backgroundColor: colors.primarySoft,
  },
  suggestionKicker: {
    ...type.tiny,
    color: colors.primary,
    fontWeight: '700',
    marginBottom: 2,
  },
  notice: {
    marginHorizontal: spacing.lg,
    marginTop: spacing.md,
    padding: spacing.md,
    borderRadius: radius.md,
    backgroundColor: colors.surfaceAlt,
  },
  list: { flex: 1, marginTop: spacing.md },
  listHeader: {
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.sm,
    fontWeight: '700',
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.border,
  },
  rowEmoji: { fontSize: 22 },
});
