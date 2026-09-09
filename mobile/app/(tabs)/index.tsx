import { useLocalSearchParams, useRouter } from 'expo-router';
import React, { useMemo, useRef, useState } from 'react';
import { FlatList, Platform, Pressable, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { places as allPlaces, themeLabel, themes } from '../../src/data/catalog';
import { useCatalogue } from '../../src/lib/useCatalogue';
import { usePays } from '../../src/store/pays';
import { bandeau } from '../../src/lib/carte';
import { etoilesDe } from '../../src/lib/etoiles';
import { nomDeRegion } from '../../src/lib/regions';
import { evaluateCheckIn, suggestCheckIn } from '../../src/lib/checkin';
import { distanceToPlace, formatDistance } from '../../src/lib/geo';
import { useCheckIn } from '../../src/lib/useCheckIn';
import { useLocation } from '../../src/lib/useLocation';
import { useRoulette } from '../../src/lib/roulette';
import { MIN_CARACTERES, search } from '../../src/lib/search';
import { useVisits } from '../../src/store/visits';
import { LARGEUR_MAX, colors, elevation, fonts, spacing, radius, type } from '../../src/theme';
import {
  Button,
  ChipRow,
  EmptyState,
  Photo,
  Pill,
  SearchField,
} from '../../src/ui/components';
import { MapCanvas } from '../../src/ui/MapCanvas';
import { IconeChevron, IconeCroix } from '../../src/ui/icons';
import { ThemeIcon } from '../../src/ui/themeIcons';
import { Etoiles } from '../../src/ui/Etoiles';
import type { Place } from '../../src/types';

/** Combien de vignettes dans le bandeau. Au-delà, on fait défiler pour rien. */
const BANDEAU = 30;
/**
 * Largeur d'une vignette du bandeau, points, et hauteur de sa photo.
 *
 * Le bandeau flotte AU-DESSUS de la carte : chaque point qu'il prend est un
 * point de carte en moins. À cent quatre-vingt-dix de large et cent vingt de
 * photo, il mangeait un tiers de la hauteur utile — la France y tenait à peine,
 * et on ne voyait que deux lieux.
 *
 * Cent cinquante-six et quatre-vingt-huit : trois vignettes visibles, un tiers
 * de hauteur rendu à la carte, et une photo qui reste assez grande pour qu'on
 * reconnaisse un lieu — c'est tout ce qu'on lui demande.
 */
const VIGNETTE = 156;
const VIGNETTE_PHOTO = 88;
/**
 * La largeur RÉELLEMENT disponible pour la photo, dans la vignette.
 *
 * La vignette fait cent cinquante-six points de large, mais elle a huit points
 * de marge intérieure de chaque côté et un filet d'un point : il ne reste que
 * cent trente-huit. Demander la photo à cent cinquante-six la faisait déborder
 * à droite, et l'image paraissait décalée dans son cadre.
 */
const VIGNETTE_LARGEUR_PHOTO = VIGNETTE - 2 * spacing.sm - 2;

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
  // Une région demandée depuis Explorer : « touche une région, elle s'ouvre sur
  // la carte ». Le nonce distingue deux appuis sur la MÊME région — sans lui,
  // rouvrir la Bretagne après l'avoir refermée ne changerait aucun paramètre.
  const { region: regionDemandee, n } = useLocalSearchParams<{
    region?: string;
    n?: string;
  }>();
  const insets = useSafeAreaInsets();
  const { visitedIds } = useVisits();
  const checkIn = useCheckIn();
  const { position, simulated } = useLocation();
  const [theme, setTheme] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [choisi, setChoisi] = useState<Place | null>(null);
  const [auMilieu, setAuMilieu] = useState<Place | null>(null);
  /**
   * La région ouverte sur la carte — la carte en décide, l'écran s'y adapte.
   *
   * C'est elle qui titre le bandeau et fait paraître la pastille de retour.
   * Sans ça, l'écran continuait d'annoncer « autour de toi » en montrant les
   * lieux d'une région où l'on n'est pas.
   */
  const [regionOuverte, setRegionOuverte] = useState<string | null>(null);
  /** Un compteur, pas un booléen : chaque incrément est UN retour demandé. */
  const [retourFrance, setRetourFrance] = useState(0);
  const rail = useRef<FlatList<Place> | null>(null);
  // Sur un ordinateur, la molette ne défile que verticalement : le bandeau
  // restait bloqué sur les trois vignettes visibles, sans indice qu'il y en
  // avait trente.
  useRoulette(rail);

  // Le catalogue peut changer de pays sous nos pieds — c'est même le but :
  // on se promène, on passe la frontière, il suit. `version` entre donc dans
  // les dépendances de tout ce qui en dérive.
  const version = useCatalogue();
  const { regarder } = usePays();
  const visible = useMemo(
    () => (theme ? allPlaces.filter((p) => p.themeId === theme) : allPlaces),
    [theme, version],
  );

  const themeOptions = useMemo(
    () => [
      // Le nom COURT : « Monuments et édifices remarquables » occupait la
      // largeur d'un téléphone à lui seul, et on voyait deux thèmes sur
      // vingt-trois. Le nom complet reste sur la page de la collection.
      { value: null, label: 'Tous' },
      ...themes
        .map((entry) => ({
          value: entry.id,
          label: entry.nameShort || entry.name,
          // Vingt-trois icônes dessinées, au même gabarit : un emoji est rendu
          // par le système, donc jamais deux fois pareil, et « ⛪ » servait à la
          // fois pour les abbayes et pour les cathédrales.
          icone: (couleur: string) => (
            <ThemeIcon themeId={entry.id} size={19} color={couleur} />
          ),
        }))
        .sort((a, b) => a.label.localeCompare(b.label, 'fr')),
    ],
    [],
  );

  /**
   * Ce que le bandeau montre.
   *
   * Une région ouverte, ce sont SES lieux : la carte et le bandeau doivent
   * raconter la même chose, sans quoi on fait défiler des vignettes qui ne
   * correspondent à rien de ce qu'on regarde. Sinon, le plus proche d'abord —
   * ou le mieux classé quand on ne sait pas où est l'utilisateur.
   */
  const dansLaRegion = useMemo(
    () => (regionOuverte ? visible.filter((p) => p.regionCode === regionOuverte) : visible),
    [visible, regionOuverte],
  );
  const vignettes = useMemo(
    () => bandeau(dansLaRegion, position, BANDEAU),
    [dansLaRegion, position],
  );

  /** Le titre du bandeau : ce qu'on regarde, en toutes lettres. */
  const titreDuBandeau = regionOuverte
    ? `${dansLaRegion.length} LIEU${dansLaRegion.length > 1 ? 'X' : ''} EN ${nomDeRegion(
        regionOuverte,
      ).toUpperCase()}`
    : 'AUTOUR DE TOI';

  /**
   * La recherche ignore le thème : quelqu'un qui tape « etretat » ne veut pas
   * s'entendre dire que ce lieu est hors du thème choisi trois écrans plus tôt.
   */
  const resultats = useMemo(() => search(allPlaces, query), [query, version]);
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
          // Toucher la carte à côté d'un point rend le bandeau : sans ce
          // retour, la fiche restait ouverte pour de bon et les lieux voisins
          // disparaissaient jusqu'au changement d'onglet.
          onDeselect={() => setChoisi(null)}
          onRegionChange={setRegionOuverte}
          onCentre={regarder}
          retour={retourFrance}
          ouvrir={regionDemandee ? `${regionDemandee}#${n ?? ''}` : null}
          highlightedId={enAvant?.id ?? suggestion?.id ?? null}
          focus={enAvant ? { lat: enAvant.lat, lon: enAvant.lon } : null}
        />
      </View>

      <View style={[styles.haut, { paddingTop: insets.top + spacing.sm }]}>
        <View style={styles.colonne}>
          <SearchField
            value={query}
            onChange={setQuery}
            placeholder="Un lieu, une commune, un département"
          />
          {enRecherche ? null : (
            <ChipRow options={themeOptions} value={theme} onChange={setTheme} />
          )}
          {/* La pastille de retour n'existe qu'une fois une région ouverte.
              Dézoomer referme aussi — mais un chemin qu'on VOIT vaut mieux
              qu'un geste qu'il faut deviner. */}
          {!enRecherche && regionOuverte ? (
            <Pressable
              style={styles.retourRegion}
              onPress={() => setRetourFrance(retourFrance + 1)}
              accessibilityRole="button"
              accessibilityLabel="Revenir à la France entière"
            >
              <IconeChevron size={17} color={colors.surface} />
              <Text style={styles.retourFrance}>France</Text>
              <View style={styles.retourFilet} />
              <Text style={styles.retourNom} numberOfLines={1}>
                {nomDeRegion(regionOuverte)}
              </Text>
            </Pressable>
          ) : null}
        </View>
      </View>

      {/* Pendant une recherche, les résultats couvrent la carte : elle ne
          répond pas à la question posée. */}
      {enRecherche ? (
        <View style={[styles.resultats, { top: insets.top + 108 }]}>
          <FlatList
            data={resultats}
            keyExtractor={(entry) => entry.place.id}
            contentContainerStyle={{ width: '100%', maxWidth: LARGEUR_MAX, alignSelf: 'center' }}
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
          <View style={styles.colonne}>
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
                width={84}
                height={84}
              />
              <View style={{ flex: 1, gap: 2 }}>
                <Text style={type.subheading} numberOfLines={2}>
                  {choisi.name}
                </Text>
                <Etoiles note={etoilesDe(choisi.id)} taille={13} />
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
                <IconeCroix size={18} color={colors.muted} />
              </Pressable>
            </Pressable>
          ) : (
            <>
            <Text style={[type.kicker, styles.titreBandeau]}>{titreDuBandeau}</Text>
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
                    width={VIGNETTE_LARGEUR_PHOTO}
                    height={VIGNETTE_PHOTO}
                  />
                  <Text style={[type.body, styles.nom]} numberOfLines={1}>
                    {item.name}
                  </Text>
                  <View style={styles.ligneVignette}>
                    <Etoiles note={etoilesDe(item.id)} taille={12} />
                    <Text style={type.small} numberOfLines={1}>
                      {distance(item) ?? item.communeName ?? item.departement ?? ''}
                    </Text>
                  </View>
                </Pressable>
              )}
            />
            </>
          )}

          {Platform.OS === 'web' && simulated ? (
            <Text style={[type.tiny, styles.avis]}>
              Mode démo : ta position est simulée.
            </Text>
          ) : null}

          {/* La Licence ouverte exige la mention des contours, et les licences
              de Commons celle des photos. Ce n'est pas une politesse. */}
          <Text style={styles.credit} numberOfLines={2}>
            Contours IGN Admin Express — Licence ouverte (Etalab) · Photos Wikimedia
            Commons
          </Text>
          </View>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  retourRegion: {
    flexDirection: 'row',
    alignItems: 'center',
    alignSelf: 'flex-start',
    gap: 6,
    height: 42,
    paddingHorizontal: 14,
    marginHorizontal: spacing.md,
    borderRadius: radius.pill,
    backgroundColor: colors.primary,
    ...elevation.flottant,
  },
  retourFrance: { fontSize: 15, fontWeight: '600', color: colors.surface },
  retourFilet: {
    width: 1,
    height: 18,
    backgroundColor: colors.surface,
    opacity: 0.4,
    marginHorizontal: 2,
  },
  retourNom: {
    fontSize: 16,
    fontFamily: fonts.display,
    color: colors.surface,
    flexShrink: 1,
  },
  titreBandeau: { paddingHorizontal: spacing.lg, paddingBottom: 4 },
  ligneVignette: { flexDirection: 'row', alignItems: 'center', gap: 5 },
  credit: {
    fontSize: 10,
    color: '#7A6E5C',
    textAlign: 'center',
    paddingHorizontal: spacing.lg,
    paddingTop: 6,
  },
  // Un cadre pleine largeur, une colonne bornée au milieu : `alignSelf` ne
  // centre RIEN sur un élément posé en absolu — `left: 0` et `right: 0` gagnent,
  // et la barre restait collée au bord gauche d'un écran d'ordinateur.
  haut: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    alignItems: 'center',
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
  // Centré et borné sur grand écran : la recherche et le bandeau appartiennent
  // à une application de téléphone, pas à un tableau de bord de deux mètres.
  bas: { position: 'absolute', left: 0, right: 0, bottom: 0, alignItems: 'center' },
  colonne: { width: '100%', maxWidth: LARGEUR_MAX, gap: spacing.sm },
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
  // Une croix de seize points dans huit de marge se rate : trente-deux points
  // de cible au total, pour un geste qu'on fait à chaque lieu regardé.
  fermer: { padding: spacing.md, marginRight: -spacing.xs },
  fermerTexte: { fontSize: 20, color: colors.muted },
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
