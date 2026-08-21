import React from 'react';
import { Pressable, StyleSheet, Text, View, ViewStyle } from 'react-native';

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

const styles = StyleSheet.create({
  track: { backgroundColor: colors.surfaceAlt, overflow: 'hidden', width: '100%' },
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
