import { useRouter } from 'expo-router';
import React, { useRef } from 'react';
import {
  Image,
  PixelRatio,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
  ViewStyle,
} from 'react-native';

import { photoUrl } from '../lib/photo';
import { useRoulette } from '../lib/roulette';
import { colors, radius, spacing, themeEmoji, type } from '../theme';
import { IconeChevron, IconeCroix, IconeLoupe } from './icons';
import { ThemeIcon } from './themeIcons';
import type { Tier } from '../types';

/**
 * La photo d'un lieu, avec son repli.
 *
 * Le catalogue en donne une pour 2 005 lieux sur 2 028. Les vingt-trois autres
 * — la villa Savoye, le gouffre Jean-Bernard — ne doivent pas laisser un trou :
 * l'emoji du thème sur fond teinté dit « pas de photo », pas « ça a raté ».
 *
 * Le même repli sert quand le chargement échoue, et c'est le cas important :
 * hors réseau, un cadre vide sur toute une liste donne une application cassée.
 *
 * La largeur DEMANDÉE est celle du cadre, pas celle du fichier : `photoUrl`
 * l'arrondit à l'un des trois paliers que Commons garde en cache.
 */
export function Photo({
  url,
  themeId,
  width,
  height,
  round = radius.md,
}: {
  url?: string | null;
  themeId: string;
  /** Largeur du cadre en points — sert à choisir la taille téléchargée. */
  width: number;
  height: number;
  round?: number;
}) {
  const [rate, setRate] = React.useState(false);
  // La densité de l'écran, pas seulement la taille du cadre : une photo
  // demandée en POINTS est étirée d'autant de fois qu'il y a de pixels par
  // point, et arrive floue là où l'application vend des images.
  const src = rate ? null : photoUrl(url, width, PixelRatio.get());
  const cadre = {
    width,
    height,
    borderRadius: round,
    backgroundColor: colors.surfaceAlt,
    overflow: 'hidden' as const,
  };

  if (!src) {
    // Le repli d'une photo manquante : l'icône du thème, dessinée. Un emoji
    // change de dessin d'un système à l'autre, et une grille de vignettes en
    // devenait un patchwork de styles.
    return (
      <View style={[cadre, styles.sansPhoto]}>
        <ThemeIcon
          themeId={themeId}
          size={Math.round(Math.min(width, height) * 0.42)}
          color={colors.locked}
          strokeWidth={1.6}
        />
      </View>
    );
  }

  return (
    <Image
      accessibilityIgnoresInvertColors
      source={{ uri: src }}
      onError={(evenement) => {
        // Le repli est silencieux À L'ÉCRAN — c'est voulu, un cadre vide sur
        // toute une liste donne une application cassée. Mais il l'était aussi
        // dans les journaux, et une photo qui ne vient jamais ressemblait
        // exactement à un lieu qui n'en a pas. Le message du système dit la
        // différence : un refus du serveur, un réseau absent, une adresse
        // fausse.
        console.warn('Roam : photo —', src, evenement.nativeEvent?.error);
        setRate(true);
      }}
      resizeMode="cover"
      style={cadre}
    />
  );
}

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
export function BackBar({ label = 'Carte' }: { label?: string }) {
  const router = useRouter();
  return (
    <Pressable
      onPress={() => (router.canGoBack() ? router.back() : router.replace('/'))}
      style={styles.back}
      accessibilityRole="button"
      accessibilityLabel={label}
      hitSlop={12}
    >
      <IconeChevron size={20} color={colors.primary} />
      <Text style={styles.backLabel}>{label}</Text>
    </Pressable>
  );
}

export function ChipRow<T extends string>({
  options,
  value,
  onChange,
}: {
  /** `icone` reçoit la couleur d'encre : une pastille choisie s'inverse. */
  options: Array<{
    value: T | null;
    label: string;
    icone?: (couleur: string) => React.ReactNode;
  }>;
  value: T | null;
  onChange: (value: T | null) => void;
}) {
  const rangee = useRef<ScrollView | null>(null);
  useRoulette(rangee);

  return (
    <ScrollView
      ref={rangee}
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
            {option.icone?.(selected ? colors.surface : colors.text)}
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
      <IconeLoupe size={18} color={colors.muted} />
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
          <IconeCroix size={18} color={colors.muted} />
        </Pressable>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  sansPhoto: { alignItems: 'center', justifyContent: 'center' },
  // Le seul chemin de retour d'un écran de fiche, et il tenait en quatre points
  // de marge : quarante-quatre de haut, comme tout ce qui se touche.
  back: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    alignSelf: 'flex-start',
    paddingVertical: spacing.md,
    paddingRight: spacing.lg,
    marginBottom: spacing.sm,
  },
  backLabel: { fontSize: 17, color: colors.primary, fontWeight: '600' },
  chipRow: { gap: spacing.xs, paddingVertical: spacing.xs, paddingRight: spacing.lg },
  // Treize pixels de texte dans six de marge : il fallait zoomer pour lire les
  // thèmes, et la pastille faisait trente-deux points de haut là où le pouce en
  // demande quarante-quatre.
  chip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 7,
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderRadius: radius.pill,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
  },
  chipSelected: { backgroundColor: colors.primary, borderColor: colors.primary },
  chipText: { fontSize: 15, color: colors.text },
  chipTextSelected: { color: colors.surface, fontWeight: '600' },
  track: { backgroundColor: colors.surfaceAlt, overflow: 'hidden', width: '100%' },
  search: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingHorizontal: spacing.md,
    height: 52,
    borderRadius: radius.md,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
  },
  searchIcon: { fontSize: 15 },
  // `outlineWidth` ne sert que sur le web : sans lui, le champ garde le liseré
  // bleu que le navigateur pose sur tout élément qui a le focus.
  searchInput: { flex: 1, ...type.body, padding: 0, outlineWidth: 0 },
  searchClear: { fontSize: 17, color: colors.muted, paddingHorizontal: spacing.sm },
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
    paddingVertical: spacing.md,
    borderRadius: radius.pill,
    alignItems: 'center',
  },
  segmentSelected: { backgroundColor: colors.surface },
  segmentText: { fontSize: 15, fontWeight: '600', color: colors.muted },
  segmentTextSelected: { color: colors.text },
  // Quarante-quatre points de haut au minimum, c'est la taille d'un pouce.
  button: {
    // Cinquante-deux points de haut, et en pastille : tout ce qui se touche
    // est rond, tout ce qui contient est arrondi.
    height: 52,
    justifyContent: 'center',
    paddingHorizontal: spacing.lg,
    borderRadius: radius.pill,
    alignItems: 'center',
  },
  buttonPrimary: { backgroundColor: colors.primary },
  buttonSecondary: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.primary,
  },
  buttonDisabled: { backgroundColor: colors.surfaceAlt },
  buttonText: { fontSize: 17, fontWeight: '700' },
  buttonTextPrimary: { color: colors.surface },
  buttonTextSecondary: { color: colors.primary },
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
