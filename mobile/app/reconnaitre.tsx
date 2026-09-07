import { useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import React, { useMemo, useState } from 'react';
import {
  FlatList,
  Pressable,
  StyleSheet,
  Text,
  View,
  useWindowDimensions,
} from 'react-native';

import { areas, places as toutes } from '../src/data/catalog';
import { regionsPresentes, tuiles, type Mode } from '../src/lib/grid';
import { useVisits } from '../src/store/visits';
import { LARGEUR_MAX, colors, largeurUtile, radius, spacing, type } from '../src/theme';
import { BackBar, ChipRow, EmptyState, Photo, SegmentedControl } from '../src/ui/components';
import type { Place } from '../src/types';

/**
 * Le quadrillage : reconnaître d'un coup d'œil les lieux déjà visités.
 *
 * Une application de collection qui démarre à zéro sur deux mille lieux ne dit
 * rien de son propriétaire : la moitié de ce qu'il a vu dans sa vie y figure.
 * Le saisir à la main — chercher un nom, ouvrir une fiche, valider, revenir —
 * coûte trop cher pour être fait. On ne se souvient pas d'une liste de noms, on
 * RECONNAÎT une image.
 *
 * D'où l'écran : des photos en grille, un doigt qui touche ce qu'il reconnaît,
 * et un seul enregistrement à la fin. Rien ne part tant que le bouton n'est pas
 * pressé — cocher n'engage à rien, et c'est ce qui permet d'aller vite.
 */
export default function RecognitionScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { width: ecran } = useWindowDimensions();
  const { visitedIds, addVisits, removeVisits } = useVisits();

  const [mode, setMode] = useState<Mode>('a-reconnaitre');
  const [region, setRegion] = useState<string | null>(null);
  const [choisis, setChoisis] = useState<Set<string>>(new Set());

  const regions = useMemo(() => {
    const noms = new Map(areas.region.map((zone) => [zone.code, zone.name]));
    return regionsPresentes(toutes, noms);
  }, []);

  const lot = useMemo(
    () => tuiles(toutes, { mode, regionCode: region, visitedIds }),
    [mode, region, visitedIds],
  );

  // Deux colonnes : au-delà, la photo devient trop petite pour être reconnue,
  // ce qui vide l'écran de sa raison d'être. Et bornées : sur un ordinateur,
  // la même règle donnait des tuiles de neuf cents pixels — deux photos par
  // écran, là où le quadrillage vit d'en montrer beaucoup d'un coup.
  const colonne = Math.floor((largeurUtile(ecran) - spacing.lg * 2 - spacing.md) / 2);

  const basculer = (id: string) =>
    setChoisis((actuels) => {
      const suivant = new Set(actuels);
      if (!suivant.delete(id)) suivant.add(id);
      return suivant;
    });

  // Changer de filtre garde la sélection : on peut parcourir la Bretagne puis
  // la Normandie et n'enregistrer qu'une fois.
  const enregistrer = () => {
    const ids = [...choisis];
    if (mode === 'valides') removeVisits(ids);
    else addVisits(toutes.filter((place) => choisis.has(place.id)), 'declared');
    setChoisis(new Set());
  };

  const renderTile = ({ item }: { item: Place }) => {
    const choisi = choisis.has(item.id);
    return (
      <Pressable
        onPress={() => basculer(item.id)}
        onLongPress={() => router.push(`/place/${item.id}`)}
        style={[styles.tuile, { width: colonne }]}
        accessibilityRole="checkbox"
        accessibilityState={{ checked: choisi }}
        accessibilityLabel={item.name}
      >
        <View>
          <Photo
            url={item.imageUrl}
            themeId={item.themeId}
            width={colonne}
            height={Math.round(colonne * 0.75)}
          />
          {choisi ? (
            <View style={[styles.voile, { width: colonne, height: Math.round(colonne * 0.75) }]}>
              <Text style={styles.coche}>✓</Text>
            </View>
          ) : null}
        </View>
        <Text style={[type.body, styles.nom]} numberOfLines={2}>
          {item.name}
        </Text>
        <Text style={type.small} numberOfLines={1}>
          {item.communeName ?? item.departement ?? ''}
        </Text>
      </Pressable>
    );
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.bg }}>
      <FlatList
        data={lot}
        keyExtractor={(place) => place.id}
        numColumns={2}
        columnWrapperStyle={{ gap: spacing.md }}
        contentContainerStyle={{
          padding: spacing.lg,
          paddingTop: insets.top + spacing.md,
          paddingBottom: spacing.xxl * 3,
          gap: spacing.lg,
          width: '100%',
          maxWidth: LARGEUR_MAX,
          alignSelf: 'center',
        }}
        // La grille est longue — deux mille tuiles. On ne garde en mémoire que
        // ce qui est proche de l'écran, sans quoi le défilement saccade dès la
        // centième photo.
        initialNumToRender={8}
        windowSize={5}
        removeClippedSubviews
        ListHeaderComponent={
          <View style={{ gap: spacing.md }}>
            <BackBar />
            <Text style={type.title}>Où es-tu déjà allé ?</Text>
            <Text style={type.small}>
              Touche ce que tu reconnais. Rien n'est enregistré tant que tu n'as pas
              validé en bas. Un appui long ouvre la fiche.
            </Text>
            <SegmentedControl
              options={[
                { value: 'a-reconnaitre' as Mode, label: 'À reconnaître' },
                { value: 'valides' as Mode, label: 'Déjà validés' },
              ]}
              value={mode}
              onChange={(suivant) => setMode(suivant)}
            />
            {/* La région avant le thème : on se souvient d'un voyage par où il
                a eu lieu, pas par catégorie. */}
            <ChipRow
              options={[{ value: null, label: 'Toute la France' }, ...regions]}
              value={region}
              onChange={setRegion}
            />
          </View>
        }
        ListEmptyComponent={
          <EmptyState
            title={mode === 'valides' ? 'Aucun lieu validé ici' : 'Plus rien à reconnaître ici'}
            body={
              mode === 'valides'
                ? 'Les lieux que tu valides apparaîtront ici, pour pouvoir te dédire.'
                : 'Change de région, ou reviens quand le catalogue aura grandi.'
            }
          />
        }
        renderItem={renderTile}
      />

      {choisis.size > 0 ? (
        <Pressable
          style={[styles.barre, { paddingBottom: insets.bottom + spacing.md }]}
          onPress={enregistrer}
          accessibilityRole="button"
        >
          <Text style={styles.barreTexte}>
            {mode === 'valides'
              ? `Retirer ${choisis.size} lieu${choisis.size > 1 ? 'x' : ''}`
              : `J'y suis allé — ${choisis.size} lieu${choisis.size > 1 ? 'x' : ''}`}
          </Text>
        </Pressable>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  tuile: { gap: spacing.xs },
  nom: { marginTop: spacing.xs },
  voile: {
    position: 'absolute',
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: radius.md,
    backgroundColor: 'rgba(47, 111, 78, 0.72)',
  },
  coche: { fontSize: 44, color: '#FFFFFF', fontWeight: '700' },
  barre: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    paddingTop: spacing.md,
    paddingHorizontal: spacing.lg,
    backgroundColor: colors.primary,
  },
  barreTexte: {
    color: '#FFFFFF',
    fontSize: 16,
    fontWeight: '700',
    textAlign: 'center',
  },
});
