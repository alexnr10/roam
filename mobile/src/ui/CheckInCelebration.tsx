import React, { useEffect, useRef, useState } from 'react';
import {
  AccessibilityInfo,
  Animated,
  Easing,
  Modal,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import type { CheckInReward } from '../lib/progress';
import { colors, radius, spacing, themeEmoji, type } from '../theme';
import type { Place } from '../types';

/**
 * Le moment de récompense.
 *
 * Une validation ne doit pas se contenter de cocher une case : ce qu'on
 * célèbre, c'est le MOUVEMENT. Les barres partent du pourcentage d'avant et
 * montent jusqu'à celui d'après — voir passer de 18 % à 25 % vaut mieux que
 * lire « 25 % ».
 */

const BAR_DURATION = 900;
const MAX_ADVANCES = 3;

export function CheckInCelebration({
  place,
  reward,
  onDismiss,
}: {
  place: Place;
  reward: CheckInReward;
  onDismiss: () => void;
}) {
  const [reduceMotion, setReduceMotion] = useState(false);
  const backdrop = useRef(new Animated.Value(0)).current;
  const medallion = useRef(new Animated.Value(0)).current;
  const halo = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    AccessibilityInfo.isReduceMotionEnabled()
      .then(setReduceMotion)
      .catch(() => setReduceMotion(false));
  }, []);

  useEffect(() => {
    Animated.parallel([
      Animated.timing(backdrop, {
        toValue: 1,
        duration: reduceMotion ? 0 : 220,
        useNativeDriver: true,
      }),
      Animated.spring(medallion, {
        toValue: 1,
        friction: 5,
        tension: 90,
        useNativeDriver: true,
      }),
    ]).start();

    if (reduceMotion) return;
    // Une onde unique qui part du médaillon : un seul geste, pas une pluie
    // d'effets — la répétition banaliserait le moment.
    Animated.timing(halo, {
      toValue: 1,
      duration: 1100,
      easing: Easing.out(Easing.quad),
      useNativeDriver: true,
    }).start();
  }, [backdrop, medallion, halo, reduceMotion]);

  // Le niveau le plus haut atteint donne la couleur du médaillon.
  const bestTier = reward.tierUps.reduce<number | null>(
    (best, entry) => (best === null ? entry.tier : Math.min(best, entry.tier)),
    null,
  );
  const accent = bestTier ? colors.tier[bestTier - 1] : colors.primary;

  return (
    <Modal transparent animationType="none" onRequestClose={onDismiss}>
      <Animated.View style={[styles.backdrop, { opacity: backdrop }]}>
        <Pressable style={styles.dismissArea} onPress={onDismiss} accessibilityRole="button">
          <View style={styles.card}>
            <View style={styles.medallionWrap}>
              {!reduceMotion ? (
                <Animated.View
                  style={[
                    styles.halo,
                    {
                      borderColor: accent,
                      opacity: halo.interpolate({
                        inputRange: [0, 1],
                        outputRange: [0.55, 0],
                      }),
                      transform: [
                        {
                          scale: halo.interpolate({
                            inputRange: [0, 1],
                            outputRange: [0.6, 2.4],
                          }),
                        },
                      ],
                    },
                  ]}
                />
              ) : null}
              <Animated.View
                style={[
                  styles.medallion,
                  { backgroundColor: accent, transform: [{ scale: medallion }] },
                ]}
              >
                <Text style={styles.medallionGlyph}>
                  {themeEmoji[place.themeId] ?? '📍'}
                </Text>
              </Animated.View>
            </View>

            <Text style={styles.kicker}>VALIDÉ</Text>
            <Text style={[type.heading, styles.centered]}>{place.name}</Text>

            <View style={styles.advances}>
              {reward.advances.slice(0, MAX_ADVANCES).map((advance, index) => (
                <AdvanceRow
                  key={advance.collection.slug}
                  name={advance.collection.name}
                  tier={advance.tier}
                  from={advance.fromVisited}
                  to={advance.toVisited}
                  total={advance.tierTotal}
                  delay={reduceMotion ? 0 : 260 + index * 140}
                  animate={!reduceMotion}
                />
              ))}
              {reward.advances.length > MAX_ADVANCES ? (
                <Text style={[type.small, styles.centered]}>
                  et {reward.advances.length - MAX_ADVANCES} autre
                  {reward.advances.length - MAX_ADVANCES > 1 ? 's' : ''} collection
                  {reward.advances.length - MAX_ADVANCES > 1 ? 's' : ''}
                </Text>
              ) : null}
            </View>

            {reward.tierUps.map((entry) => (
              <View
                key={`${entry.collection.slug}-${entry.tier}`}
                style={[styles.highlight, { borderColor: colors.tier[entry.tier - 1] }]}
              >
                <Text style={styles.highlightGlyph}>🏅</Text>
                <View style={{ flex: 1 }}>
                  <Text style={type.subheading}>Niveau {entry.tier} terminé</Text>
                  <Text style={type.small} numberOfLines={1}>
                    {entry.collection.name}
                  </Text>
                </View>
              </View>
            ))}

            {reward.newBadges
              .filter((badge) => badge.kind === 'threshold')
              .map((badge) => (
                <View key={badge.id} style={styles.highlight}>
                  <Text style={styles.highlightGlyph}>🎖️</Text>
                  <View style={{ flex: 1 }}>
                    <Text style={type.subheading}>{badge.label}</Text>
                    <Text style={type.small} numberOfLines={1}>
                      {badge.collectionName}
                    </Text>
                  </View>
                </View>
              ))}

            <Text style={[type.small, styles.centered, { marginTop: spacing.md }]}>
              Touche pour continuer
            </Text>
          </View>
        </Pressable>
      </Animated.View>
    </Modal>
  );
}

/**
 * Une collection qui avance, comptée en lieux et non en pourcents.
 *
 * « 7 sur 8 » dit ce qu'il reste à faire ; « 87 % » demande une division avant
 * de vouloir dire quelque chose. Le reste de l'application compte déjà en
 * lieux — l'écran de récompense parlait encore l'autre langue.
 */
function AdvanceRow({
  name,
  tier,
  from,
  to,
  total,
  delay,
  animate,
}: {
  name: string;
  tier: number;
  from: number;
  to: number;
  total: number;
  delay: number;
  animate: boolean;
}) {
  const progress = useRef(new Animated.Value(animate ? from : to)).current;
  const [shown, setShown] = useState(animate ? from : to);

  useEffect(() => {
    if (!animate) return;
    const listener = progress.addListener(({ value }) => setShown(value));
    Animated.timing(progress, {
      toValue: to,
      duration: BAR_DURATION,
      delay,
      easing: Easing.out(Easing.cubic),
      // La largeur n'est pas animable par le pilote natif.
      useNativeDriver: false,
    }).start();
    return () => progress.removeListener(listener);
  }, [progress, to, delay, animate]);

  const width = progress.interpolate({
    // Une barre vide sur « 1 sur 12 » ne récompense rien. Le trait garde donc
    // une amorce visible dès le premier lieu : ce qu'on montre est un début,
    // pas une proportion à la virgule près.
    inputRange: [0, Math.max(total, 1)],
    outputRange: ['0%', '100%'],
    extrapolate: 'clamp',
  });

  return (
    <View style={styles.advance}>
      <View style={styles.advanceHead}>
        <Text style={type.small} numberOfLines={1}>
          {name}
        </Text>
        <Text style={styles.advanceValue}>
          N{tier} {Math.round(shown)}/{total}
        </Text>
      </View>
      <View style={styles.advanceTrack}>
        <Animated.View
          style={[
            styles.advanceFill,
            { width, minWidth: to > 0 ? 6 : 0, backgroundColor: colors.tier[tier - 1] },
          ]}
        />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  backdrop: { flex: 1, backgroundColor: 'rgba(26, 25, 23, 0.55)' },
  dismissArea: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: spacing.lg },
  card: {
    width: '100%',
    maxWidth: 380,
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    padding: spacing.xl,
    alignItems: 'center',
    gap: spacing.sm,
  },
  medallionWrap: {
    width: 96,
    height: 96,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: spacing.sm,
  },
  halo: { position: 'absolute', width: 96, height: 96, borderRadius: 48, borderWidth: 3 },
  medallion: { width: 76, height: 76, borderRadius: 38, alignItems: 'center', justifyContent: 'center' },
  medallionGlyph: { fontSize: 34 },
  kicker: { ...type.tiny, fontWeight: '700', color: colors.primary, letterSpacing: 1.5 },
  centered: { textAlign: 'center' },
  advances: { width: '100%', gap: spacing.md, marginTop: spacing.lg },
  advance: { gap: spacing.xs },
  advanceHead: { flexDirection: 'row', justifyContent: 'space-between', gap: spacing.sm },
  advanceValue: { ...type.small, fontWeight: '700', color: colors.primary },
  advanceTrack: {
    height: 8,
    borderRadius: 4,
    backgroundColor: colors.surfaceAlt,
    overflow: 'hidden',
  },
  advanceFill: { height: '100%', borderRadius: 4, backgroundColor: colors.primary },
  highlight: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    width: '100%',
    marginTop: spacing.md,
    padding: spacing.md,
    borderRadius: radius.md,
    borderWidth: 1.5,
    borderColor: colors.border,
    backgroundColor: colors.surfaceAlt,
  },
  highlightGlyph: { fontSize: 24 },
});
