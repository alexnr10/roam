import { useLocalSearchParams, useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import React, { useMemo } from 'react';
import {
  Linking,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
  useWindowDimensions,
} from 'react-native';

import { getCollectionsForPlace, getPlace, themeLabel } from '../../src/data/catalog';
import { evaluateCheckIn } from '../../src/lib/checkin';
import { etoilesDe } from '../../src/lib/etoiles';
import { formatDistance } from '../../src/lib/geo';
import { setSimulatedPosition } from '../../src/lib/simulation';
import { computeProgress } from '../../src/lib/progress';
import { useCheckIn } from '../../src/lib/useCheckIn';
import { useLocation } from '../../src/lib/useLocation';
import { useEnvies } from '../../src/store/envies';
import { useVisits } from '../../src/store/visits';
import { LARGEUR_MAX, colors, largeurUtile, radius, spacing, type } from '../../src/theme';
import {
  BackBar,
  Button,
  Card,
  Photo,
  Pill,
  ProgressBar,
} from '../../src/ui/components';
import { Etoiles } from '../../src/ui/Etoiles';

export default function PlaceScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { width: ecran } = useWindowDimensions();
  const { visits, visitedIds, removeVisit } = useVisits();
  const { envieIds, basculer } = useEnvies();
  const checkIn = useCheckIn();
  const { position } = useLocation();

  const place = id ? getPlace(id) : undefined;

  const memberships = useMemo(
    () => (place ? getCollectionsForPlace(place.id) : []),
    [place],
  );

  if (!place) {
    return (
      <View style={styles.centered}>
        <Text style={type.subheading}>Lieu introuvable</Text>
      </View>
    );
  }

  const visited = visitedIds.has(place.id);
  const veutVoir = envieIds.has(place.id);
  const visit = visits.find((entry) => entry.placeId === place.id);
  const evaluation = evaluateCheckIn(place, position);

  return (
    <ScrollView
      style={{ backgroundColor: colors.bg }}
      contentContainerStyle={{
        padding: spacing.lg,
        paddingTop: insets.top + spacing.md,
        paddingBottom: spacing.xxl,
        // Sur un grand écran, le contenu se CENTRE au lieu de s'étirer : la
        // photo faisait sinon dix-huit cents pixels de large, et le texte
        // courait d'un bord à l'autre.
        width: '100%',
        maxWidth: LARGEUR_MAX,
        alignSelf: 'center',
      }}
    >
      <BackBar />
      {/* La photo AVANT le nom : on reconnaît un lieu avant de le lire, et
          c'est tout l'objet de cet écran quand on cherche à se rappeler si on
          y est allé. Trois pour deux, le cadrage des photos de paysage. */}
      <Photo
        url={place.imageUrl}
        themeId={place.themeId}
        width={largeurUtile(ecran) - spacing.lg * 2}
        height={Math.round(((largeurUtile(ecran) - spacing.lg * 2) * 2) / 3)}
        round={radius.lg}
      />
      {/* Le crédit de la photo. Une image de Commons n'est pas libre de
          droits : la plupart des licences exigent de citer l'auteur. Tant que
          `enrich --images` n'a pas tourné, on cite au moins le dépôt — c'est
          le minimum honnête, et ça ne prétend pas savoir ce qu'on ignore. */}
      {place.imageUrl ? (
        <Text style={[type.tiny, styles.credit]} numberOfLines={2}>
          Photo :{place.imageAuthor ? ` ${place.imageAuthor} ·` : ''}
          {place.imageLicence ? ` ${place.imageLicence} ·` : ''} Wikimedia
          Commons
        </Text>
      ) : null}
      <Text style={[type.title, { marginTop: spacing.md }]}>{place.name}</Text>
      {/* La note AVANT la ligne de contexte : c'est ce qu'on cherche en
          arrivant sur une fiche — est-ce que ça vaut le déplacement ? */}
      <View style={{ marginTop: spacing.xs }}>
        <Etoiles note={etoilesDe(place.id)} taille={16} mention />
      </View>
      <Text style={[type.small, { marginTop: spacing.xs }]}>
        {themeLabel(place.themeId)}
        {place.departement ? ` · ${place.departement}` : ''}
      </Text>

      {place.summary ? (
        <>
          <Text style={[type.body, styles.summary]}>{place.summary}</Text>
          <Text style={[type.small, { marginTop: spacing.sm }]}>
            D'après{' '}
            {place.wikipediaUrl ? (
              <Text
                style={{ color: colors.primary }}
                onPress={() => Linking.openURL(place.wikipediaUrl as string)}
              >
                Wikipédia
              </Text>
            ) : (
              'Wikipédia'
            )}{' '}
            · CC BY-SA
          </Text>
        </>
      ) : null}

      <Card style={{ marginTop: spacing.lg, gap: spacing.md }}>
        {visited ? (
          <>
            <View style={styles.rowBetween}>
              <Pill
                label={visit?.verified ? 'Visite vérifiée' : 'Visite déclarée'}
                tone={visit?.verified ? 'verified' : 'neutral'}
              />
              {evaluation.distanceM !== null ? (
                <Text style={type.small}>{formatDistance(evaluation.distanceM)}</Text>
              ) : null}
            </View>
            <Button
              label="Retirer cette visite"
              tone="secondary"
              onPress={() => removeVisit(place.id)}
            />
          </>
        ) : (
          <>
            <View style={styles.rowBetween}>
              <Text style={type.body}>{evaluation.message}</Text>
              {/* Le rayon porte la taille du site : 120 m pour une cathédrale,
                  2 km pour des gorges. */}
              <Text style={type.small}>rayon {place.radiusM} m</Text>
            </View>

            <Button
              label={evaluation.canCheckIn ? 'Je suis sur place' : 'Trop loin pour valider'}
              disabled={!evaluation.canCheckIn}
              onPress={() => checkIn(place, 'gps', evaluation.distanceM ?? undefined)}
            />

            {/* Sans ça, l'utilisateur démarre à 0 % partout et décroche. */}
            <Button
              label="J'y suis déjà allé"
              tone="secondary"
              onPress={() => checkIn(place, 'declared')}
            />
            <Text style={[type.small, { textAlign: 'center' }]}>
              Une visite déclarée compte dans tes pourcentages, mais n'est pas
              marquée « vérifiée ».
            </Text>

            {/* L'autre geste possible sur une fiche : pas « j'y étais » mais
                « j'irai ». Il n'apparaît que sur un lieu non visité — une fois
                validé, l'envie n'a plus d'objet et la liste s'en débarrasse
                d'elle-même. */}
            <Button
              label={veutVoir ? 'Retirer de mes envies' : 'Ajouter à mes envies'}
              tone="secondary"
              onPress={() => basculer(place.id)}
            />

            {/* Mode démo, web uniquement : éprouver le moment de validation
                sans faire la route. Jamais embarqué sur téléphone. */}
            {Platform.OS === 'web' ? (
              <Button
                label="Démo : me téléporter ici"
                tone="secondary"
                onPress={() =>
                  setSimulatedPosition({
                    latitude: place.lat,
                    longitude: place.lon,
                    accuracy: 8,
                  })
                }
              />
            ) : null}
          </>
        )}
      </Card>

      <Text style={[type.heading, { marginTop: spacing.xl, marginBottom: spacing.md }]}>
        Compte dans {memberships.length} collection{memberships.length > 1 ? 's' : ''}
      </Text>

      {memberships.map((collection) => {
        const progress = computeProgress(collection, visits);
        return (
          <Pressable
            key={collection.slug}
            style={styles.collectionRow}
            onPress={() => router.push(`/collection/${collection.slug}`)}
          >
            <Text style={type.body} numberOfLines={1}>
              {collection.name}
            </Text>
            {/* Sur la fiche d'un lieu, une collection ne répond qu'à UNE
                question : où j'en suis dedans. Rien d'autre.
                On y montrait le palier en cours — « 0/11 des incontournables »
                — ce qui laissait croire que le lieu en était un, et qu'on ne
                l'avait pas validé. C'est le contraire : la maison du docteur
                Gachet est cent quatrième sur cent cinquante-cinq.
                Le rang du lieu est parti avec : l'étoile, en haut de la fiche,
                dit déjà sa valeur, et deux mesures de la même chose sur un même
                écran ne s'additionnent pas, elles se contredisent. */}
            <ProgressBar pct={progress.pct} color={colors.primaryLight} height={6} />
            <Text style={type.small}>
              {progress.visited} lieu{progress.visited > 1 ? 'x' : ''} validé
              {progress.visited > 1 ? 's' : ''} sur {progress.total}
            </Text>
          </Pressable>
        );
      })}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  centered: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  credit: { marginTop: spacing.xs },
  summary: { marginTop: spacing.md, lineHeight: 22 },
  rowBetween: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: spacing.md,
  },
  collectionRow: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    padding: spacing.md,
    marginBottom: spacing.sm,
    gap: spacing.sm,
  },
});
