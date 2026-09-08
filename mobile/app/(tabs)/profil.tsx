import { useRouter } from 'expo-router';
import React, { useMemo } from 'react';
import { Alert, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { buildLabel } from '../../src/lib/build';
import { collections, places } from '../../src/data/catalog';
import { computeProgress, earnedBadges, nextMilestone, type Badge } from '../../src/lib/progress';
import { rank, shortlists } from '../../src/lib/shortlist';
import { useLocation } from '../../src/lib/useLocation';
import { getPlacesInCollection } from '../../src/data/catalog';
import { useVisits } from '../../src/store/visits';
import { LARGEUR_MAX, colors, conquest, fonts, radius, spacing, type } from '../../src/theme';
import { Button, Card, EmptyState, Pill, ProgressBar } from '../../src/ui/components';
import { IconeRosette } from '../../src/ui/icons';
import { MiniatureFrance } from '../../src/ui/regionShape';
import { conquestByZone, shadeOf } from '../../src/lib/conquest';
import { areas } from '../../src/data/catalog';

export default function ProfileScreen() {
  const { visits, reset } = useVisits();
  const router = useRouter();
  const { position } = useLocation();

  const verified = visits.filter((visit) => visit.verified).length;

  const badges = useMemo<Badge[]>(() => {
    return collections.flatMap((collection) =>
      earnedBadges(collection, computeProgress(collection, visits)),
    );
  }, [visits]);

  // Ce qui est presque fini : le seul classement de collections qui donne
  // envie d'aller quelque part une fois qu'on collectionne déjà.
  const aUnLieuPres = useMemo(() => {
    const classe = rank(
      collections,
      (collection) => computeProgress(collection, visits),
      getPlacesInCollection,
      position,
    );
    return shortlists(classe, 3).almostDone;
  }, [visits, position]);

  /**
   * La couleur de chaque région dans la vignette.
   *
   * La même que sur la carte de conquête : une vignette qui montrerait autre
   * chose que l'écran qu'elle ouvre ne servirait à rien.
   */
  const teintes = useMemo(() => {
    const par: Record<string, string> = {};
    for (const zone of conquestByZone(places, areas.region, 'region', visits, null)) {
      const shade = shadeOf(zone);
      if (shade.kind !== 'empty') par[zone.area.code] = conquest[shade.kind];
    }
    return par;
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
      contentContainerStyle={{
        padding: spacing.lg,
        paddingBottom: spacing.xxl,
        // Centré sur grand écran plutôt qu'étiré : c'est une
        // application de téléphone, lue sur un ordinateur.
        width: '100%',
        maxWidth: LARGEUR_MAX,
        alignSelf: 'center',
      }}
    >
      <View style={styles.stats}>
        <Stat value={visits.length} label="lieux validés" />
        {/* Déclaré vs vérifié : les deux comptent, seul le second est prouvé —
            d'où la seconde voix, la sauge, plutôt que la terre cuite. */}
        <Stat value={verified} label="dont vérifiés GPS" couleur={colors.verified} />
        <Stat value={badges.length} label="badges" />
      </View>

      {/* La conquête et le quadrillage vivent ici : ce sont des récompenses, et
          une récompense ne réclame pas le quart de la barre d'onglets. */}
      <Pressable style={styles.conquete} onPress={() => router.push('/conquete')}>
        <MiniatureFrance couleurs={teintes} />
        <View style={{ flex: 1, gap: spacing.sm }}>
          <Text style={type.heading}>Ta carte de conquête</Text>
          <Text style={type.small}>
            Les départements et les régions se colorent à mesure que tu termines
            leurs collections.
          </Text>
          <Text style={styles.lien}>Voir la carte →</Text>
        </View>
      </Pressable>

      {aUnLieuPres.length ? (
        <View style={{ marginBottom: spacing.lg }}>
          <Text style={type.heading}>À un lieu près</Text>
          <Text style={[type.small, { marginBottom: spacing.md }]}>
            Il ne te manque presque rien — où que ce soit
          </Text>
          {aUnLieuPres.map((item) => {
            const jalon = nextMilestone(item.progress);
            return (
              <Pressable
                key={item.collection.slug}
                style={styles.presque}
                onPress={() => router.push(`/collection/${item.collection.slug}`)}
              >
                <Text style={type.subheading} numberOfLines={1}>
                  {item.collection.name}
                </Text>
                <ProgressBar pct={item.progress.stage.pct} />
                <Text style={type.small}>
                  {jalon
                    ? `encore ${jalon.remaining} lieu${jalon.remaining > 1 ? 'x' : ''}`
                    : 'terminée'}
                </Text>
              </Pressable>
            );
          })}
        </View>
      ) : null}

      {/* Le quadrillage, à portée du premier écran : une application de
          collection qui démarre à zéro ne dit rien de son propriétaire, alors
          que la moitié de ce qu'il a vu dans sa vie est au catalogue. */}
      <View style={styles.reconnaissance}>
        <Text style={type.heading}>Tu y es sûrement déjà allé</Text>
        <Text style={type.small}>
          {places.length} lieux au catalogue, et une vie de voyages derrière toi. Passe-les
          en photos et coche ce que tu reconnais — c'est plus rapide que de les chercher
          un par un.
        </Text>
        <Button label="Reconnaître mes lieux" onPress={() => router.push('/reconnaitre')} />
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
              <IconeRosette
                size={22}
                color={badge.kind === 'tier' ? colors.primary : conquest.theme}
              />
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
        {/* La marque de construction. L'aperçu web est un seul fichier que le
            navigateur d'un téléphone garde en cache : sans elle, on ne peut
            pas distinguer « la correction n'est pas passée » de « je regarde
            la page d'hier ». */}
        <Text style={[type.tiny, { marginTop: spacing.sm }]}>{buildLabel()}</Text>
      </View>
    </ScrollView>
  );
}

function Stat({
  value,
  label,
  couleur = colors.primary,
}: {
  value: number;
  label: string;
  couleur?: string;
}) {
  return (
    <View style={styles.stat}>
      <Text style={[styles.statValue, { color: couleur }]}>{value}</Text>
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
  statValue: { fontSize: 28, fontFamily: fonts.display, color: colors.primary },
  conquete: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.lg,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.xl,
    padding: 18,
    marginBottom: spacing.lg,
  },
  lien: { fontSize: 15, fontWeight: '600', color: colors.primary },
  reconnaissance: {
    backgroundColor: colors.primarySoft,
    borderRadius: radius.xl,
    padding: 18,
    marginBottom: spacing.lg,
    gap: spacing.sm,
  },
  presque: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.lg,
    padding: spacing.md,
    marginBottom: spacing.sm,
    gap: spacing.sm,
  },
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
});
