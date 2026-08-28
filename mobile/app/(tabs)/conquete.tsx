import React, { useEffect, useMemo, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View, useWindowDimensions } from 'react-native';

import { areas, places, themeLabel, themes } from '../../src/data/catalog';
import { conquestByZone, shadeOf } from '../../src/lib/conquest';
import type { ZoneConquest, ZoneShade } from '../../src/lib/conquest';
import { useVisits } from '../../src/store/visits';
import { colors, conquest, radius, spacing, type } from '../../src/theme';
import { ConquestMap, conquestOutlinesExist } from '../../src/ui/ConquestMap';
import { ChipRow, EmptyState, Pill, ProgressBar } from '../../src/ui/components';
import { SegmentedControl } from '../../src/ui/components';
import type { AreaLevel } from '../../src/types';

/**
 * L'écran de conquête : la carte coloriée, et ce qu'il reste à faire dessous.
 *
 * Les deux se répondent. Un aplat de couleur ne dit que ce qui est fait ; la
 * liste dit ce qui manque, et nomme les thèmes. Taper un territoire sur la
 * carte y réduit la liste — c'est le geste qui relie les deux.
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
  const [selected, setSelected] = useState<string | null>(null);
  const [theme, setTheme] = useState<string | null>(null);
  const { height } = useWindowDimensions();

  const zones = useMemo(
    () => conquestByZone(places, areas[level], level, visits, theme),
    [level, visits, theme],
  );

  // Un thème n'a pas partout de quoi jouer ; ne proposer que ceux du catalogue
  // évite de filtrer sur du vide.
  const themeOptions = useMemo(
    () => [
      { value: null, label: 'Tous les thèmes' },
      ...themes
        .map((entry) => ({ value: entry.id, label: entry.name }))
        .sort((a, b) => a.label.localeCompare(b.label, 'fr')),
    ],
    [],
  );

  // Un code de département n'a aucun sens à l'échelle des régions.
  useEffect(() => setSelected(null), [level]);

  const current = LEVELS.find((entry) => entry.value === level)!;
  const totals = useMemo(() => {
    const conquered = zones.filter((zone) => zone.allComplete && zone.playable).length;
    const partial = zones.filter(
      (zone) => !zone.allComplete && zone.anyThemeComplete,
    ).length;
    const started = zones.filter(
      (zone) => !zone.anyThemeComplete && zone.overall.visited > 0,
    ).length;
    return { conquered, partial, started };
  }, [zones]);

  const drawn = conquestOutlinesExist(level);
  // Assez haut pour que la France tienne en entier, assez bas pour qu'il reste
  // de la liste sous le pouce.
  const mapHeight = Math.max(220, Math.min(360, height * 0.42));

  const focused = selected ? zones.filter((zone) => zone.area.code === selected) : zones;
  const focusedName = selected
    ? zones.find((zone) => zone.area.code === selected)?.area.name
    : null;

  return (
    <View style={styles.screen}>
      <View style={styles.controls}>
        <SegmentedControl
          options={LEVELS.map(({ value, label }) => ({ value, label }))}
          value={level}
          onChange={setLevel}
        />
        {/* Filtrer par thème change ce que « territoire complet » veut dire :
            avoir fini les châteaux du Val-d'Oise est une conquête en soi. */}
        <ChipRow options={themeOptions} value={theme} onChange={setTheme} />
      </View>

      {drawn && zones.length > 0 ? (
        <View style={[styles.map, { height: mapHeight }]}>
          <ConquestMap
            zones={zones}
            level={level}
            selectedCode={selected}
            onSelectZone={setSelected}
          />
        </View>
      ) : null}

      <ScrollView
        style={{ backgroundColor: colors.bg }}
        contentContainerStyle={styles.list}
      >
        {zones.length === 0 ? (
          <EmptyState
            title={`Aucune ${current.one} au catalogue`}
            body={
              level === 'commune'
                ? "Le rattachement aux communes se fait par les coordonnées : relance `enrich` puis `export-app` dans le pipeline pour l'obtenir."
                : 'Le catalogue ne contient encore aucun lieu à cette échelle.'
            }
          />
        ) : (
          <>
            <View style={styles.summary}>
              {selected ? (
                <Pressable onPress={() => setSelected(null)} style={styles.clear}>
                  <Text style={type.small}>{focusedName} — tout voir ✕</Text>
                </Pressable>
              ) : (
                <Text style={type.small}>
                  {theme ? `${themeLabel(theme)} — ` : ''}
                  {plural(totals.conquered, current.one, current.many)} au complet ·{' '}
                  {totals.partial} avec une collection finie · {totals.started}{' '}
                  {`entamé${current.feminine ? 'e' : ''}${totals.started > 1 ? 's' : ''}`} sur{' '}
                  {zones.length}
                </Text>
              )}
              <View style={styles.legend}>
                {theme ? (
                  <Legend
                    color={conquest.total}
                    label={`${themeLabel(theme)} — thème terminé ici`}
                  />
                ) : (
                  <>
                    <Legend color={conquest.theme} label="une collection finie" />
                    <Legend color={conquest.total} label="territoire complet" />
                  </>
                )}
              </View>
            </View>

            {focused.map((zone) => (
              <ZoneCard
                key={`${level}:${zone.area.code}`}
                zone={zone}
                themeId={theme}
                onPress={() =>
                  setSelected(selected === zone.area.code ? null : zone.area.code)
                }
              />
            ))}
          </>
        )}
      </ScrollView>
    </View>
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

function ZoneCard({
  zone,
  themeId,
  onPress,
}: {
  zone: ZoneConquest;
  themeId: string | null;
  onPress: () => void;
}) {
  const shade = shadeOf(zone);
  const color = shadeColor(shade);
  const done = zone.themes.filter((entry) => entry.state.complete);
  const active = zone.themes.filter(
    (entry) => !entry.state.complete && entry.state.visited > 0,
  );

  return (
    <Pressable
      onPress={onPress}
      style={[styles.card, shade.kind !== 'empty' && { borderColor: color }]}
    >
      <View style={styles.head}>
        {/* Le bandeau porte la couleur du territoire : c'est exactement ce que
            la carte montre, en aplat, au même endroit du même vocabulaire. */}
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
        {/* La liste doit dire la même chose que la carte. Annoncer « territoire
            conquis » sur une zone que l'aplat laisse grise, parce qu'elle n'a
            pas assez de lieux du thème, était une contradiction à l'écran. */}
        {zone.allComplete && zone.playable ? (
          <Pill label="Territoire conquis" tone="primary" />
        ) : zone.overall.tier > 0 && zone.playable ? (
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

      {!zone.playable ? (
        <Text style={type.tiny}>
          Trop peu de {themeLabel(themeId!).toLowerCase()} ici pour que la conquête
          compte — il en faut au moins trois.
        </Text>
      ) : themeId === null && zone.themes.length === 0 && zone.overall.visited > 0 ? (
        <Text style={type.tiny}>
          Aucun thème jouable ici — il faut au moins trois lieux d'un même thème.
        </Text>
      ) : null}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  controls: { paddingHorizontal: spacing.lg, paddingTop: spacing.lg },
  map: {
    marginHorizontal: spacing.lg,
    marginTop: spacing.md,
    borderRadius: radius.lg,
    overflow: 'hidden',
  },
  list: { padding: spacing.lg, paddingBottom: spacing.xxl },
  summary: { marginBottom: spacing.md, gap: spacing.sm },
  clear: { alignSelf: 'flex-start' },
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
