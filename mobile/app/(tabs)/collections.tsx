import { useRouter } from 'expo-router';
import React, { useMemo } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { collections, getPlacesInCollection } from '../../src/data/catalog';
import { computeProgress, nextMilestone } from '../../src/lib/progress';
import {
  byProgressThenDistance, formatDistance, rank, shortlists, type Ranked,
} from '../../src/lib/shortlist';
import { useLocation } from '../../src/lib/useLocation';
import { useVisits } from '../../src/store/visits';
import { colors, radius, spacing, type } from '../../src/theme';
import { Pill, ProgressBar } from '../../src/ui/components';
import type { CollectionKind } from '../../src/types';

/**
 * Deux cent quatre-vingts collections, et trois questions pour les ranger.
 *
 * Le tri par progression décroissante ne triait RIEN tant qu'aucun lieu
 * n'était collecté : tout valait 0 %, et l'ordre des cartes était celui du
 * fichier. Le nouvel arrivant voyait 253 collections géographiques sans le
 * moindre principe d'organisation.
 */
const SECTIONS: Array<{ kind: CollectionKind; title: string; blurb: string }> = [
  { kind: 'theme', title: 'Par thème', blurb: 'Châteaux, cascades, sommets…' },
  { kind: 'label', title: 'Par label', blurb: 'Les listes officielles, déjà curées' },
  { kind: 'geo', title: 'Par géographie', blurb: 'Ta région, ton département, le pays' },
];

export default function CollectionsScreen() {
  const router = useRouter();
  const { visits } = useVisits();
  const { position } = useLocation();

  const classe = useMemo(
    () => rank(
      collections,
      (collection) => computeProgress(collection, visits),
      getPlacesInCollection,
      position,
    ),
    [visits, position],
  );

  const { almostDone, nearby, rest } = useMemo(() => shortlists(classe), [classe]);

  return (
    <ScrollView
      style={{ backgroundColor: colors.bg }}
      contentContainerStyle={{ padding: spacing.lg, paddingBottom: spacing.xxl }}
    >
      <Bloc
        titre="À un lieu près"
        blurb="Il ne te manque presque rien — où que ce soit"
        items={almostDone}
        router={router}
      />
      <Bloc
        titre="Près de toi"
        blurb="Ce que tu peux aller voir ce week-end"
        items={nearby}
        router={router}
      />

      {SECTIONS.map((section) => {
        const items = rest
          .filter((r) => r.collection.kind === section.kind)
          .sort(byProgressThenDistance);
        return (
          <Bloc
            key={section.kind}
            titre={section.title}
            blurb={section.blurb}
            items={items}
            router={router}
          />
        );
      })}
    </ScrollView>
  );
}

function Bloc({
  titre, blurb, items, router,
}: {
  titre: string;
  blurb: string;
  items: Ranked[];
  router: ReturnType<typeof useRouter>;
}) {
  if (items.length === 0) return null;
  return (
    <View style={{ marginBottom: spacing.xl }}>
      <Text style={type.heading}>{titre}</Text>
      <Text style={[type.small, { marginBottom: spacing.md }]}>{blurb}</Text>
      {items.map((item) => (
        <Carte key={item.collection.slug} item={item} router={router} />
      ))}
    </View>
  );
}

function Carte({
  item, router,
}: {
  item: Ranked;
  router: ReturnType<typeof useRouter>;
}) {
  const { collection, progress } = item;
  const { stage } = progress;
  const milestone = nextMilestone(progress);
  const distance = formatDistance(item.distanceM);
  return (
    <Pressable
      style={styles.card}
      onPress={() => router.push(`/collection/${collection.slug}`)}
    >
      <View style={styles.cardHead}>
        <Text style={type.subheading} numberOfLines={1}>
          {collection.name}
        </Text>
        {/* Le niveau, pas le pourcentage global : « N1 5/8 » se lit comme un
            palier à portée, « 45,5 % » comme une corvée à moitié faite. */}
        <Text style={styles.pct}>
          N{stage.tier} {stage.visited}/{stage.total}
        </Text>
      </View>

      <ProgressBar pct={stage.pct} />

      <View style={styles.cardFoot}>
        <Text style={type.small}>
          {progress.visited}/{progress.total} au total
          {distance ? ` · à ${distance}` : ''}
        </Text>
        {progress.complete ? (
          <Pill label="Terminée" tone="verified" />
        ) : milestone ? (
          <Text style={type.small}>
            encore {milestone.remaining} lieu{milestone.remaining > 1 ? 'x' : ''}
          </Text>
        ) : null}
      </View>
    </Pressable>
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
