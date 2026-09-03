import { useRouter } from 'expo-router';
import React from 'react';
import {
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
  ViewStyle,
} from 'react-native';

import { colors, radius, spacing, type } from '../theme';
import type { Tier } from '../types';

export function ProgressBar({
  pct,
  color = colors.primary,
  height = 8,
}: {
  pct: number;
  color?: string;
  height?: number;
}) {
  const clamped = Math.max(0, Math.min(100, pct));
  return (
    <View style={[styles.track, { height, borderRadius: height / 2 }]}>
      <View
        style={{
          width: `${clamped}%`,
          height: '100%',
          backgroundColor: color,
          borderRadius: height / 2,
        }}
      />
    </View>
  );
}

export function Pill({
  label,
  tone = 'neutral',
  style,
}: {
  label: string;
  tone?: 'neutral' | 'primary' | 'verified' | 'muted';
  style?: ViewStyle;
}) {
  const tones = {
    neutral: { bg: colors.surfaceAlt, fg: colors.text },
    primary: { bg: colors.primarySoft, fg: colors.primary },
    verified: { bg: '#E3F0E8', fg: colors.verified },
    muted: { bg: colors.surfaceAlt, fg: colors.muted },
  }[tone];

  return (
    <View style={[styles.pill, { backgroundColor: tones.bg }, style]}>
      <Text style={[styles.pillText, { color: tones.fg }]}>{label}</Text>
    </View>
  );
}

export function TierDot({ tier, size = 10 }: { tier: Tier; size?: number }) {
  return (
    <View
      style={{
        width: size,
        height: size,
        borderRadius: size / 2,
        backgroundColor: colors.tier[tier - 1],
      }}
    />
  );
}

/**
 * Rangée de pastilles défilante, pour un choix parmi beaucoup.
 *
 * Le contrôle segmenté ne tient qu'à quatre ou cinq options ; les thèmes sont
 * vingt-trois. Le défilement horizontal garde le geste à un doigt et laisse
 * voir le choix courant, là où un menu déroulant le cacherait derrière un
 * appui de plus.
 */
/**
 * Retour vers l'écran précédent, posé DANS l'écran.
 *
 * L'en-tête de la pile de navigation en fournissait un — sauf dans la page
 * repliée en un seul fichier, où l'adresse ne change jamais : la pile croit
 * n'avoir qu'un écran, l'en-tête reste vide, et on se retrouve enfermé sur la
 * fiche d'un lieu sans aucun moyen d'en sortir.
 *
 * Un contrôle qui ne dépend d'aucune de ces subtilités, et un repli explicite
 * vers la carte quand il n'y a réellement rien derrière : on ne doit jamais
 * pouvoir rester bloqué.
 */
export function BackBar({ label = 'Retour' }: { label?: string }) {
  const router = useRouter();
  return (
    <Pressable
      onPress={() => (router.canGoBack() ? router.back() : router.replace('/'))}
      style={styles.back}
      accessibilityRole="button"
      accessibilityLabel={label}
      hitSlop={12}
    >
      <Text style={styles.backArrow}>←</Text>
      <Text style={styles.backLabel}>{label}</Text>
    </Pressable>
  );
}

export function ChipRow<T extends string>({
  options,
  value,
  onChange,
}: {
  options: Array<{ value: T | null; label: string }>;
  value: T | null;
  onChange: (value: T | null) => void;
}) {
  return (
    <ScrollView
      horizontal
      showsHorizontalScrollIndicator={false}
      contentContainerStyle={styles.chipRow}
    >
      {options.map((option) => {
        const selected = option.value === value;
        return (
          <Pressable
            key={option.value ?? '__all__'}
            onPress={() => onChange(option.value)}
            style={[styles.chip, selected && styles.chipSelected]}
            accessibilityRole="button"
            accessibilityState={{ selected }}
          >
            <Text style={[styles.chipText, selected && styles.chipTextSelected]}>
              {option.label}
            </Text>
          </Pressable>
        );
      })}
    </ScrollView>
  );
}

export function SegmentedControl<T extends string>({
  options,
  value,
  onChange,
}: {
  options: Array<{ value: T; label: string }>;
  value: T;
  onChange: (value: T) => void;
}) {
  return (
    <View style={styles.segmented}>
      {options.map((option) => {
        const selected = option.value === value;
        return (
          <Pressable
            key={option.value}
            onPress={() => onChange(option.value)}
            style={[styles.segment, selected && styles.segmentSelected]}
            accessibilityRole="button"
            accessibilityState={{ selected }}
          >
            <Text style={[styles.segmentText, selected && styles.segmentTextSelected]}>
              {option.label}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}

export function Button({
  label,
  onPress,
  tone = 'primary',
  disabled = false,
}: {
  label: string;
  onPress: () => void;
  tone?: 'primary' | 'secondary';
  disabled?: boolean;
}) {
  const isPrimary = tone === 'primary';
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled}
      accessibilityRole="button"
      style={({ pressed }) => [
        styles.button,
        isPrimary ? styles.buttonPrimary : styles.buttonSecondary,
        disabled && styles.buttonDisabled,
        pressed && !disabled && { opacity: 0.85 },
      ]}
    >
      <Text
        style={[
          styles.buttonText,
          isPrimary ? styles.buttonTextPrimary : styles.buttonTextSecondary,
          disabled && { color: colors.muted },
        ]}
      >
        {label}
      </Text>
    </Pressable>
  );
}

export function Card({
  children,
  style,
}: {
  children: React.ReactNode;
  style?: ViewStyle;
}) {
  return <View style={[styles.card, style]}>{children}</View>;
}

export function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <View style={styles.empty}>
      <Text style={type.subheading}>{title}</Text>
      <Text style={[type.small, { textAlign: 'center', marginTop: spacing.sm }]}>{body}</Text>
    </View>
  );
}

/**
 * Le champ de recherche.
 *
 * Une croix pour effacer plutôt qu'un bouton « annuler » : sur téléphone, on
 * corrige sa recherche bien plus souvent qu'on ne l'abandonne. La croix
 * n'apparaît que lorsqu'il y a quelque chose à effacer.
 */
export function SearchField({
  value,
  onChange,
  placeholder = 'Rechercher',
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
}) {
  return (
    <View style={styles.search}>
      <Text style={styles.searchIcon}>🔍</Text>
      <TextInput
        value={value}
        onChangeText={onChange}
        placeholder={placeholder}
        placeholderTextColor={colors.muted}
        style={styles.searchInput}
        autoCorrect={false}
        autoCapitalize="none"
        returnKeyType="search"
        accessibilityLabel={placeholder}
      />
      {value.length > 0 ? (
        <Pressable
          onPress={() => onChange('')}
          accessibilityRole="button"
          accessibilityLabel="Effacer la recherche"
          hitSlop={8}
        >
          <Text style={styles.searchClear}>✕</Text>
        </Pressable>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  back: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    alignSelf: 'flex-start',
    paddingVertical: spacing.xs,
    paddingRight: spacing.md,
    marginBottom: spacing.sm,
  },
  backArrow: { fontSize: 20, color: colors.primary, lineHeight: 22 },
  backLabel: { fontSize: 15, color: colors.primary, fontWeight: '600' },
  chipRow: { gap: spacing.xs, paddingVertical: spacing.xs, paddingRight: spacing.lg },
  chip: {
    paddingHorizontal: spacing.md,
    paddingVertical: 6,
    borderRadius: radius.pill,
    backgroundColor: colors.surfaceAlt,
    borderWidth: 1,
    borderColor: colors.border,
  },
  chipSelected: { backgroundColor: colors.primary, borderColor: colors.primary },
  chipText: { fontSize: 13, color: colors.muted },
  chipTextSelected: { color: '#FFFFFF', fontWeight: '600' },
  track: { backgroundColor: colors.surfaceAlt, overflow: 'hidden', width: '100%' },
  search: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingHorizontal: spacing.md,
    height: 44,
    borderRadius: radius.md,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
  },
  searchIcon: { fontSize: 15 },
  // `outlineWidth` ne sert que sur le web : sans lui, le champ garde le liseré
  // bleu que le navigateur pose sur tout élément qui a le focus.
  searchInput: { flex: 1, ...type.body, padding: 0, outlineWidth: 0 },
  searchClear: { fontSize: 15, color: colors.muted, paddingHorizontal: spacing.xs },
  pill: {
    paddingHorizontal: spacing.md,
    paddingVertical: 5,
    borderRadius: radius.pill,
    alignSelf: 'flex-start',
  },
  pillText: { fontSize: 12, fontWeight: '600' },
  segmented: {
    flexDirection: 'row',
    backgroundColor: colors.surfaceAlt,
    borderRadius: radius.pill,
    padding: 3,
  },
  segment: {
    flex: 1,
    paddingVertical: spacing.sm,
    borderRadius: radius.pill,
    alignItems: 'center',
  },
  segmentSelected: { backgroundColor: colors.surface },
  segmentText: { fontSize: 13, fontWeight: '600', color: colors.muted },
  segmentTextSelected: { color: colors.text },
  button: {
    paddingVertical: spacing.md + 2,
    paddingHorizontal: spacing.lg,
    borderRadius: radius.md,
    alignItems: 'center',
  },
  buttonPrimary: { backgroundColor: colors.primary },
  buttonSecondary: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
  },
  buttonDisabled: { backgroundColor: colors.surfaceAlt },
  buttonText: { fontSize: 15, fontWeight: '700' },
  buttonTextPrimary: { color: '#FFFFFF' },
  buttonTextSecondary: { color: colors.text },
  card: {
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.lg,
  },
  empty: {
    alignItems: 'center',
    paddingVertical: spacing.xxl,
    paddingHorizontal: spacing.xl,
  },
});
