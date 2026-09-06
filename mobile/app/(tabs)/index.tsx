import { useRouter } from 'expo-router';
import React, { useMemo, useRef, useState } from 'react';
import { FlatList, Platform, Pressable, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { places as allPlaces, themeLabel, themes } from '../../src/data/catalog';
import { bandeau } from '../../src/lib/carte';
import { evaluateCheckIn, suggestCheckIn } from '../../src/lib/checkin';
import { distanceToPlace, formatDistance } from '../../src/lib/geo';
import { useCheckIn } from '../../src/lib/useCheckIn';
import { useLocation } from '../../src/lib/useLocation';
import { MIN_CARACTERES, search } from '../../src/lib/search';
import { useVisits } from '../../src/store/visits';
import { colors, spacing, radius, type } from '../../src/theme';
import {
  Button,
  ChipRow,
  EmptyState,
  Photo,
  Pill,
  SearchField,
} from '../../src/ui/components';
import { MapCanvas } from '../../src/ui/MapCanvas';
import type { Place } from '../../src/types';

/** Combien de vignettes dans le bandeau. Au-delà, on fait défiler pour rien. */
const BANDEAU = 30;
/** Largeur d'une vignette du bandeau, points. */
const VIGNETTE = 168;

/**
 * L'écran principal : une carte, et ce qu'elle contient.
 *
 * L'application est d'abord un guide — on y cherche quoi faire autour de soi,
 * ou sur la route d'un voyage. La carte n'est donc pas une illustration posée
 * dans une page : c'est l'écran. Elle occupe tout, la recherche flotte
 * au-dessus, et un bandeau de vignettes montre en photos ce qu'on regarde.
 *
 * Trois gestes, et trois seulement :
 *
 * - faire défiler le bandeau recentre la carte sur la vignette du milieu ;
 * - toucher un point de la carte ouvre sa vignette, en grand ;
 * - toucher une vignette ouvre la fiche.
 *
 * L'ancien écran empilait un titre, une recherche, un contrôle segmenté, une
 * rangée de thèmes, une carte carrée, un avis, et une liste : la carte y tenait
 * un tiers de la hauteur et se trouvait au milieu d'un défilement.
 */
export default function MapScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { visitedIds } = useVisits();
  const checkIn = useCheckIn();
  const { position, simulated } = useLocation();
  const [theme, setTheme] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [choisi, setChoisi] = useState<Place | null>(null);
  const [auMilieu, setAuMilieu] = useState<Place | null>(null);
  const rail = useRef<FlatList<Place> | null>(null);

  const visible = useMemo(
    () => (theme ? allPlaces.filter((p) => p.themeId === theme) : allPlaces),
    [theme],
  );

  const themeOptions = useMemo(
    () => [
      { value: null, label: 'Tous les thèmes' },
      ...themes
        .map((entry) => ({ value: entry.id, label: entry.name }))
        .sort((a, b) => a.label.localeCompare(b.label, 'fr')),
    ],
    [],
  );

  /** Ce que le bandeau montre : le plus proche d'abord, ou le mieux classé. */
  const vignettes = useMemo(
    () => bandeau(visible, position, BANDEAU),
    [visible, position],
  );

  /**
   * La recherche ignore le thème : quelqu'un qui tape « etretat » ne veut pas
   * s'entendre dire que ce lieu est hors du thème choisi trois écrans plus tôt.
   */
  const resultats = useMemo(() => search(allPlaces, query), [query]);
  const enRecherche = query.trim().length >= MIN_CARACTERES;

  // La validation vient à l'utilisateur, pas l'inverse.
  const suggestion = useMemo(
    () => suggestCheckIn(allPlaces, position, visitedIds),
    [position, visitedIds],
  );

  const openPlace = (place: Place) => router.push(`/place/${place.id}`);

  const enAvant = choisi ?? auMilieu ?? null;
  const distance = (place: Place) =>
    position ? formatDistance(distanceToPlace(position, place)) : null;

  return (
    <View style={styles.screen}>
      {/* La carte occupe tout : le reste flotte au-dessus. */}
      <View style={StyleSheet.absoluteFill}>
        <MapCanvas
          places={visible}
          visitedIds={visitedIds}
          position={position}
          onSelectPlace={setChoisi}
          highlightedId={enAvant?.id ?? suggestion?.id ?? null}
          focus={enAvant ? { lat: enAvant.lat, lon: enAvant.lon } : null}
        />
      </View>

      <View style={[styles.haut, { paddingTop: insets.top + spacing.sm }]}>
        <SearchField
          value={query}
          onChange={setQuery}
          placeholder="Un lieu, une commune, un département"
        />
        {enRecherche ? null : (
          <ChipRow options={themeOptions} value={theme} onChange={setTheme} />
        )}
      </View>

      {/* Pendant une recherche, les résultats couvrent la carte : elle ne
          répond pas à la question posée. */}
      {enRecherche ? (
        <View style={[styles.resultats, { top: insets.top + 108 }]}>
          <FlatList
            data={resultats}
            keyExtractor={(entry) => entry.place.id}
            keyboardShouldPersistTaps="handled"
            ListHeaderComponent={
              <Text style={[type.tiny, styles.titreListe]}>
                {resultats.length} RÉSULTAT{resultats.length > 1 ? 'S' : ''}
              </Text>
            }
            ListEmptyComponent={
              <EmptyState
                title="Aucun lieu ne répond"
                body="Essaie le nom de la commune, ou du département — beaucoup de lieux sont fichés sous un nom qu'on n'emploie jamais."
              />
            }
            renderItem={({ item }) => (
              <Pressable
                style={styles.ligne}
                onPress={() => {
                  setQuery('');
                  setChoisi(item.place);
                }}
              >
                <Photo
                  url={item.place.imageUrl}
                  themeId={item.place.themeId}
                  width={52}
                  height={52}
                />
                <View style={{ flex: 1 }}>
                  <Text style={type.body} numberOfLines={1}>
                    {item.place.name}
                  </Text>
                  <Text style={type.small} numberOfLines={1}>
                    {item.par === 'lieu'
                      ? [item.place.communeName, item.place.departement]
                          .filter(Boolean)
                          .join(' · ')
                      : `${themeLabel(item.place.themeId)}${
                          item.place.departement ? ` · ${item.place.departement}` : ''
                        }`}
                  </Text>
                </View>
                {visitedIds.has(item.place.id) ? <Pill label="Validé" tone="verified" /> : null}
              </Pressable>
            )}
          />
        </View>
      ) : null}

      {!enRecherche ? (
        <View style={[styles.bas, { paddingBottom: insets.bottom + spacing.sm }]}>
          {suggestion && !choisi ? (
            <View style={styles.suggestion}>
              <View style={{ flex: 1 }}>
                <Text style={styles.kicker}>TU Y ES</Text>
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

          {choisi ? (
            /* Un point touché s'ouvre ICI, pas dans un autre écran : on regarde
               une carte, on veut savoir ce qu'est ce point sans la quitter. */
            <Pressable style={styles.fiche} onPress={() => openPlace(choisi)}>
              <Photo
                url={choisi.imageUrl}
                themeId={choisi.themeId}
                width={96}
                height={96}
              />
              <View style={{ flex: 1, gap: 2 }}>
                <Text style={type.subheading} numberOfLines={2}>
                  {choisi.name}
                </Text>
                <Text style={type.small} numberOfLines={1}>
                  {themeLabel(choisi.themeId)}
                  {choisi.communeName ? ` · ${choisi.communeName}` : ''}
                </Text>
                {distance(choisi) ? (
                  <Text style={type.small}>à {distance(choisi)}</Text>
                ) : null}
                <Text style={[type.small, { color: colors.primary }]}>Voir la fiche →</Text>
              </View>
              <Pressable
                onPress={() => setChoisi(null)}
                style={styles.fermer}
                accessibilityRole="button"
                accessibilityLabel="Fermer"
              >
                <Text style={styles.fermerTexte}>✕</Text>
              </Pressable>
            </Pressable>
          ) : (
            <FlatList
              ref={rail}
              data={vignettes}
              keyExtractor={(place) => place.id}
              horizontal
              showsHorizontalScrollIndicator={false}
              // Une vignette par cran : le bandeau s'arrête toujours sur un
              // lieu entier, jamais entre deux.
              snapToInterval={VIGNETTE + spacing.sm}
              decelerationRate="fast"
              contentContainerStyle={{ paddingHorizontal: spacing.lg, gap: spacing.sm }}
              onMomentumScrollEnd={(event) => {
                const index = Math.round(
                  event.nativeEvent.contentOffset.x / (VIGNETTE + spacing.sm),
                );
                setAuMilieu(vignettes[index] ?? null);
              }}
              renderItem={({ item }) => (
                <Pressable
                  style={[styles.vignette, { width: VIGNETTE }]}
                  onPress={() => openPlace(item)}
                >
                  <Photo
                    url={item.imageUrl}
                    themeId={item.themeId}
                    width={VIGNETTE}
                    height={96}
                  />
                  <Text style={[type.body, styles.nom]} numberOfLines={1}>
                    {item.name}
                  </Text>
                  <Text style={type.small} numberOfLines={1}>
                    {distance(item) ?? item.communeName ?? item.departement ?? ''}
                  </Text>
                </Pressable>
              )}
            />
          )}

          {Platform.OS === 'web' && simulated ? (
            <Text style={[type.tiny, styles.avis]}>
              Mode démo : ta position est simulée.
            </Text>
          ) : null}
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  haut: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    gap: spacing.sm,
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.sm,
    // Un voile clair : la recherche doit rester lisible au-dessus d'une carte
    // dont on ne maîtrise pas les couleurs.
    backgroundColor: 'rgba(251, 250, 247, 0.92)',
  },
  resultats: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: colors.bg,
  },
  titreListe: { paddingHorizontal: spacing.lg, paddingVertical: spacing.sm, fontWeight: '700' },
  ligne: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.border,
  },
  bas: { position: 'absolute', left: 0, right: 0, bottom: 0, gap: spacing.sm },
  vignette: {
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    padding: spacing.sm,
    gap: 2,
    borderWidth: 1,
    borderColor: colors.border,
  },
  nom: { marginTop: spacing.xs },
  fiche: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    marginHorizontal: spacing.lg,
    padding: spacing.sm,
    borderRadius: radius.lg,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
  },
  fermer: { padding: spacing.sm },
  fermerTexte: { fontSize: 16, color: colors.muted },
  suggestion: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    marginHorizontal: spacing.lg,
    padding: spacing.md,
    borderRadius: radius.lg,
    backgroundColor: colors.primarySoft,
  },
  kicker: { ...type.tiny, color: colors.primary, fontWeight: '700', marginBottom: 2 },
  avis: { textAlign: 'center' },
});
