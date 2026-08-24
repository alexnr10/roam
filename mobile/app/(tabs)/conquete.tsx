import React, { useMemo, useState } from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';

import { areas, places, themeLabel } from '../../src/data/catalog';
import { conquestByZone, shadeOf } from '../../src/lib/conquest';
import type { ZoneConquest, ZoneShade } from '../../src/lib/conquest';
import { useVisits } from '../../src/store/visits';
import { colors, conquest, radius, spacing, type } from '../../src/theme';
import { EmptyState, Pill, ProgressBar } from '../../src/ui/components';
import { SegmentedControl } from '../../src/ui/components';
import type { AreaLevel } from '../../src/types';

/**
 * L'écran de conquête, en liste.
 *
 * La carte coloriée viendra ensuite ; les règles, elles, se valident ici. Voir
 * « Cantal — châteaux terminés » écrit noir sur blanc dit tout de suite si le
 * seuil de jouabilité et les niveaux tombent juste, ce qu'un aplat de couleur
 * ne dirait pas.
 */

type LevelCopy = {
  value: AreaLevel;
  label: string;
  one: string;
  many: string;
  /** Le français accorde : « une commune entamée », « un département entamé ». */
  feminine: boolean;
};

const LEVELS: LevelCopy[] = [
  { value: 'commune', label: 'Communes', one: 'commune', many: 'communes', feminine: true },
  {
    value: 'departement',
    label: 'Départements',
    one: 'département',
    many: 'départements',
    feminine: false,
  },
  { value: 'region', label: 'Régions', one: 'région', many: 'régions', feminine: true },
  { value: 'country', label: 'France', one: 'pays', many: 'pays', feminine: true },
];

const plural = (count: number, singular: string, many: string) =>
  `${count} ${count > 1 ? many : singular}`;

function shadeColor(shade: ZoneShade): string {
  switch (shade.kind) {
    case 'total':
      return conquest.total;
    case 'theme':
      return conquest.theme;
    case 'started':
      return conquest.started;
    case 'empty':
      return conquest.empty;
  }
}

export default function ConquestScreen() {
  const { visits } = useVisits();
  const [level, setLevel] = useState<AreaLevel>('departement');

  const zones = useMemo(
    () => conquestByZone(places, areas[level], level, visits),
    [level, visits],
  );

  const current = LEVELS.find((entry) => entry.value === level)!;
  const totals = useMemo(() => {
    const conquered = zones.filter((zone) => zone.allComplete).length;
    const partial = zones.filter(
      (zone) => !zone.allComplete && zone.anyThemeComplete,
    ).length;
    const started = zones.filter(
      (zone) => !zone.anyThemeComplete && zone.overall.visited > 0,
    ).length;
    return { conquered, partial, started };
  }, [zones]);

  return (
    <ScrollView
      style={{ backgroundColor: colors.bg }}
      contentContainerStyle={{ padding: spacing.lg, paddingBottom: spacing.xxl }}
    >
      <SegmentedControl
        options={LEVELS.map(({ value, label }) => ({ value, label }))}
        value={level}
        onChange={setLevel}
      />

      {zones.length === 0 ? (
        <View style={{ marginTop: spacing.xl }}>
          <EmptyState
            title={`Aucune ${current.one} au catalogue`}
            body={
              level === 'commune'
                ? "Le rattachement aux communes se fait par les coordonnées : relance `enrich` puis `export-app` dans le pipeline pour l'obtenir."
                : 'Le catalogue ne contient encore aucun lieu à cette échelle.'
            }
          />
        </View>
      ) : (
        <>
          <View style={styles.summary}>
            <Text style={type.small}>
              {plural(totals.conquered, current.one, current.many)} au complet ·{' '}
              {totals.partial} avec une collection finie · {totals.started}{' '}
              {`entamé${current.feminine ? 'e' : ''}${totals.started > 1 ? 's' : ''}`} sur{' '}
              {zones.length}
            </Text>
            <View style={styles.legend}>
              <Legend color={conquest.theme} label="une collection finie" />
              <Legend color={conquest.total} label="territoire complet" />
            </View>
          </View>

          {zones.map((zone) => (
            <ZoneCard key={`${level}:${zone.area.code}`} zone={zone} />
          ))}
        </>
      )}
    </ScrollView>
  );
}

function Legend({ color, label }: { color: string; label: string }) {
  return (
    <View style={styles.legendItem}>
      <View style={[styles.swatch, { backgroundColor: color }]} />
      <Text style={type.tiny}>{label}</Text>
    </View>
  );
}

function ZoneCard({ zone }: { zone: ZoneConquest }) {
  const shade = shadeOf(zone);
  const color = shadeColor(shade);
  const done = zone.themes.filter((entry) => entry.state.complete);
  const active = zone.themes.filter(
    (entry) => !entry.state.complete && entry.state.visited > 0,
  );

  return (
    <View style={[styles.card, shade.kind !== 'empty' && { borderColor: color }]}>
      <View style={styles.head}>
        {/* Le bandeau porte la couleur du territoire : c'est ce que la carte
            montrera, en aplat, au même endroit du même vocabulaire. */}
        <View style={[styles.marker, { backgroundColor: color }]} />
        <Text style={type.subheading} numberOfLines={1}>
          {zone.area.name}
        </Text>
        <Text
          style={[
            styles.pct,
            { color: shade.kind === 'empty' ? colors.muted : color },
          ]}
        >
          {zone.overall.pct}%
        </Text>
      </View>

      <ProgressBar pct={zone.overall.pct} color={color} />

      <View style={styles.foot}>
        <Text style={type.small}>
          {zone.overall.visited}/{plural(zone.overall.total, 'lieu', 'lieux')}
        </Text>
        {zone.allComplete ? (
          <Pill label="Territoire conquis" tone="primary" />
        ) : zone.overall.tier > 0 ? (
          <Text style={type.small}>Niveau {zone.overall.tier}</Text>
        ) : null}
      </View>

      {done.length > 0 && (
        <View style={styles.chips}>
          {done.map((entry) => (
            <Pill
              key={entry.themeId}
              label={`${themeLabel(entry.themeId)} ✓`}
              tone="verified"
            />
          ))}
        </View>
      )}

      {active.length > 0 && (
        <View style={styles.chips}>
          {active.slice(0, 4).map((entry) => (
            <Pill
              key={entry.themeId}
              label={`${themeLabel(entry.themeId)} ${entry.state.visited}/${entry.state.total}`}
              tone="muted"
            />
          ))}
        </View>
      )}

      {zone.themes.length === 0 && zone.overall.visited > 0 && (
        <Text style={type.tiny}>
          Aucun thème jouable ici — il faut au moins trois lieux d'un même thème.
        </Text>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  summary: { marginTop: spacing.lg, marginBottom: spacing.md, gap: spacing.sm },
  legend: { flexDirection: 'row', gap: spacing.lg },
  legendItem: { flexDirection: 'row', alignItems: 'center', gap: spacing.xs },
  swatch: { width: 12, height: 12, borderRadius: 3 },
  card: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.lg,
    padding: spacing.lg,
    marginBottom: spacing.md,
    gap: spacing.sm,
  },
  head: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  marker: { width: 10, height: 10, borderRadius: 5 },
  pct: { ...type.subheading, marginLeft: 'auto' },
  foot: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.xs },
});
