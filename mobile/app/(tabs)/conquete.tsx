import React, { useEffect, useMemo, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View, useWindowDimensions } from 'react-native';

import { areas, places, themeLabel, themes } from '../../src/data/catalog';
import { useCatalogue } from '../../src/lib/useCatalogue';
import { conquestByZone, shadeOf } from '../../src/lib/conquest';
import { palierMinuscule } from '../../src/lib/paliers';
import type { ZoneConquest, ZoneShade } from '../../src/lib/conquest';
import { useVisits } from '../../src/store/visits';
import { colors, conquest, conquestInk, conquestTrait, radius, spacing, type } from '../../src/theme';
import { ConquestMap, conquestOutlinesExist } from '../../src/ui/ConquestMap';
import { BackBar, ChipRow, EmptyState, Pill, ProgressBar } from '../../src/ui/components';
import { SegmentedControl } from '../../src/ui/components';
import { ThemeIcon } from '../../src/ui/themeIcons';
import type { AreaLevel, Tier } from '../../src/types';

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

/**
 * Les échelles de la conquête.
 *
 * Les communes en sont sorties : le catalogue ne les rattache pas encore, et
 * un quatrième segment faisait déborder « Départements » de sa case — trois
 * mots qui se chevauchent valent moins qu'une échelle en moins.
 */
const LEVELS: LevelCopy[] = [
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

/** Ce qui se LIT : un pourcentage, un libellé. Toujours au-dessus de 4,5:1. */
const encreDe = (shade: ZoneShade): string => conquestInk[shade.kind];

/** Ce qui se VOIT : une pastille, une jauge. Le contraste de forme suffit. */
const traitDe = (shade: ZoneShade): string => conquestTrait[shade.kind];

export default function ConquestScreen() {
  // Le catalogue peut changer de pays sous nos pieds : on s'y abonne.
  const catalogue = useCatalogue();
  const { visits } = useVisits();
  const [level, setLevel] = useState<AreaLevel>('departement');
  const [selected, setSelected] = useState<string | null>(null);
  const [theme, setTheme] = useState<string | null>(null);
  const { height } = useWindowDimensions();

  const zones = useMemo(
    () => conquestByZone(places, areas[level], level, visits, theme),
    [level, visits, theme, catalogue],
  );

  // Un thème n'a pas partout de quoi jouer ; ne proposer que ceux du catalogue
  // évite de filtrer sur du vide.
  const themeOptions = useMemo(
    () => [
      { value: null, label: 'Tous' },
      ...themes
        .map((entry) => ({
          value: entry.id,
          // Le nom court, comme au-dessus de la carte : « Monuments et édifices
          // remarquables » occupe à lui seul la largeur d'un téléphone.
          label: entry.nameShort || entry.name,
          icone: (couleur: string) => (
            <ThemeIcon themeId={entry.id} size={19} color={couleur} />
          ),
        }))
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
  // Plus basse qu'avant : au-dessus d'elle il y a le retour, l'échelle et les
  // thèmes, en dessous la liste. À quarante-deux pour cent de la hauteur, les
  // pastilles de thèmes se retrouvaient coincées contre la carte.
  const mapHeight = Math.max(180, Math.min(300, height * 0.32));

  const focused = selected ? zones.filter((zone) => zone.area.code === selected) : zones;
  const focusedName = selected
    ? zones.find((zone) => zone.area.code === selected)?.area.name
    : null;

  return (
    <View style={styles.screen}>
      <View style={styles.controls}>
        {/* La conquête n'est plus un onglet : on y entre depuis « Moi », et il
            faut donc pouvoir en ressortir. */}
        <BackBar />
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
  const encre = encreDe(shade);
  const trait = traitDe(shade);
  return (
    <Pressable
      onPress={onPress}
      style={[styles.card, shade.kind !== 'empty' && { borderColor: trait }]}
    >
      <View style={styles.head}>
        {/* Le bandeau porte la couleur du territoire : c'est exactement ce que
            la carte montre, en aplat, au même endroit du même vocabulaire. */}
        <View style={[styles.marker, { backgroundColor: trait }]} />
        <Text style={type.subheading} numberOfLines={1}>
          {zone.area.name}
        </Text>
        <Text style={[styles.pct, { color: encre }]}>
          {zone.overall.pct}%
        </Text>
      </View>

      <ProgressBar pct={zone.overall.pct} color={trait} />

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
          <Text style={type.small}>{palierMinuscule(zone.overall.tier as Tier)} — fait</Text>
        ) : null}
      </View>

      {/* Les collections du territoire, TOUJOURS visibles.
          Elles n'apparaissaient qu'une fois entamées : une carte de conquête
          vierge — c'est-à-dire celle de tout le monde au premier lancement — ne
          montrait que des pourcentages à zéro, et ne disait nulle part ce qu'il
          y a À FAIRE ici. Or c'est la seule chose qui donne envie d'y aller.
          L'icône plutôt que le nom : six collections tiennent sur deux lignes
          là où six libellés en prenaient quatre. */}
      {zone.themes.length > 0 ? (
        <View style={styles.collections}>
          {zone.themes.slice(0, 8).map((entry) => {
            const fini = entry.state.complete;
            return (
              <View
                key={entry.themeId}
                style={[styles.collection, fini && styles.collectionFinie]}
              >
                <ThemeIcon
                  themeId={entry.themeId}
                  size={16}
                  color={fini ? colors.surface : colors.muted}
                  strokeWidth={1.8}
                />
                <Text style={[styles.collectionTexte, fini && { color: colors.surface }]}>
                  {entry.state.visited}/{entry.state.total}
                </Text>
              </View>
            );
          })}
          {zone.themes.length > 8 ? (
            <Text style={[type.small, { alignSelf: 'center' }]}>
              +{zone.themes.length - 8}
            </Text>
          ) : null}
        </View>
      ) : null}

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
  controls: { paddingHorizontal: spacing.lg, paddingTop: spacing.sm, gap: spacing.sm },
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
  collections: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  collection: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: 8,
    paddingVertical: 5,
    borderRadius: radius.pill,
    backgroundColor: colors.surfaceAlt,
    borderWidth: 1,
    borderColor: colors.border,
  },
  collectionFinie: { backgroundColor: conquest.theme, borderColor: conquest.theme },
  collectionTexte: { fontSize: 13, color: colors.muted, fontVariant: ['tabular-nums'] },
});
