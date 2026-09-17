import { useLocalSearchParams, useRouter } from 'expo-router';
import React, { useMemo, useRef, useState } from 'react';
import {
  FlatList,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  useWindowDimensions,
  View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { places as allPlaces, nomDuPays, themeLabel, themes } from '../../src/data/catalog';
import { useCatalogue } from '../../src/lib/useCatalogue';
import { usePays } from '../../src/store/pays';
import { bandeau } from '../../src/lib/carte';
import { etoilesDe } from '../../src/lib/etoiles';
import { attributionDesContours } from '../../src/data/outlines';
import { dansLaRegion as estDansLaRegion, nomDeRegion } from '../../src/lib/regions';
import { evaluateCheckIn, suggestCheckIn } from '../../src/lib/checkin';
import { distanceToPlace, formatDistance } from '../../src/lib/geo';
import { useCheckIn } from '../../src/lib/useCheckIn';
import { useLocation } from '../../src/lib/useLocation';
import { useRoulette } from '../../src/lib/roulette';
import { MIN_CARACTERES } from '../../src/lib/search';
import { useRechercheMondiale } from '../../src/lib/rechercheMondiale';
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
import { ATTRIBUTION_DU_FOND } from '../../src/ui/mapStyle';
import { IconeChevron, IconeCroix } from '../../src/ui/icons';
import { ThemeIcon } from '../../src/ui/themeIcons';
import { Etoiles } from '../../src/ui/Etoiles';
import type { Place } from '../../src/types';

/** Combien de vignettes dans le bandeau. Au-delà, on fait défiler pour rien. */
const BANDEAU = 30;
/**
 * La vignette est une RANGÉE, pas une colonne — et c'est ce qui règle les deux
 * plaintes d'un coup.
 *
 * La colonne empilait photo, nom, infos : cent quarante-sept points de haut
 * pour cent trente-huit de large. Le nom n'avait donc qu'une ligne de seize
 * caractères là où la médiane des noms français est à dix-huit — mesuré sur
 * les 2 080 lieux, UN NOM SUR DEUX était coupé. Et pour l'élargir il aurait
 * fallu prendre encore de la carte, qui en perdait déjà un quart.
 *
 * Couchée, la même matière tient dans quatre-vingt-huit points : la photo et
 * le texte se partagent la largeur au lieu de s'empiler. Le nom reçoit deux
 * cent dix-sept points sur deux lignes — 98,8 % des noms du catalogue passent
 * entiers — et la carte récupère cinquante-neuf points.
 *
 * Ce qu'on perd : trois photos d'un coup d'œil, contre une seule. C'est un
 * arbitrage assumé — les points sont tous sur la carte, et le bandeau sert à
 * savoir CE QU'ON REGARDE, pas à feuilleter un album.
 */
const RANGEE_PHOTO = 72;
/**
 * Ce qui dépasse de la rangée suivante, en points.
 *
 * Une rangée pleine largeur ne dit pas qu'il y en a d'autres : elle a l'air
 * d'être seule. Ce débord est la seule chose qui annonce le geste — il faut
 * qu'il se voie sans découper le contenu de la suivante.
 */
const RANGEE_DEBORD = 28;

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
  /** Le cran d'avant : revenir à la région sans quitter la région. */
  const [retourRegion, setRetourRegion] = useState(0);
  /**
   * La largeur d'une rangée se DÉDUIT de l'écran, elle n'est pas constante.
   *
   * Le bandeau est borné à `LARGEUR_MAX` et retranche ses marges ; ce qui
   * reste, moins le débord, est la rangée. Une largeur fixe aurait laissé un
   * vide à droite sur un grand écran et débordé sur un petit.
   */
  const { width: largeurEcran } = useWindowDimensions();
  const RANGEE = Math.max(
    220,
    Math.min(largeurEcran, LARGEUR_MAX) - 2 * spacing.lg - RANGEE_DEBORD,
  );
  const rail = useRef<FlatList<Place> | null>(null);
  // Sur un ordinateur, la molette ne défile que verticalement : le bandeau
  // restait bloqué sur les trois vignettes visibles, sans indice qu'il y en
  // avait trente.
  useRoulette(rail);

  // Le catalogue peut changer de pays sous nos pieds — c'est même le but :
  // on se promène, on passe la frontière, il suit. `version` entre donc dans
  // les dépendances de tout ce qui en dérive.
  const version = useCatalogue();
  const { pays, disponibles, regarder, choisir } = usePays();
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
    () => (regionOuverte ? visible.filter((p) => estDansLaRegion(p, regionOuverte)) : visible),
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
  // La recherche traverse les frontières, la carte non : on cherche un nom
  // qu'on a en tête, sans se demander d'abord dans quel pays il se trouve.
  const { resultats, chargement: chargeAilleurs } = useRechercheMondiale(
    query, pays, version, disponibles,
  );
  const enRecherche = query.trim().length >= MIN_CARACTERES;

  /**
   * Aller à un résultat — d'ici ou d'ailleurs, et de la même façon.
   *
   * On NE VA PAS sur la fiche. La carte voyage jusqu'au lieu et pose sa
   * vignette en bas ; ouvrir la fiche reste un second geste, que l'utilisateur
   * fait s'il le veut. Un résultat de recherche répond d'abord à « où est-ce,
   * au juste ? » — et la fiche, qui couvre la carte, escamotait la réponse.
   *
   * Un lieu d'un autre pays demande d'abord que son catalogue devienne actif,
   * et l'attente n'est pas facultative : sans elle, la vignette porterait un
   * identifiant que le catalogue courant ne connaît pas. La bascule se fait
   * SANS recadrage — recadrer sur l'Italie entière effacerait le voyage en le
   * remplaçant par un saut.
   */
  const ouvrirResultat = async (resultat: (typeof resultats)[number]) => {
    setQuery('');
    if (resultat.pays !== pays) await choisir(resultat.pays, false);
    setChoisi(resultat.place);
  };

  // La validation vient à l'utilisateur, pas l'inverse.
  const suggestion = useMemo(
    () => suggestCheckIn(allPlaces, position, visitedIds),
    [position, visitedIds],
  );

  const openPlace = (place: Place) => router.push(`/place/${place.id}`);

  const enAvant = choisi ?? auMilieu ?? null;
  /**
   * Un lieu est mis en avant DANS une région ouverte : la carte est zoomée sur
   * lui, et le premier retour doit rendre la région, pas le pays.
   */
  const surUnLieu = Boolean(enAvant && regionOuverte);
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
          recadrer={retourRegion}
          ouvrir={regionDemandee ? `${regionDemandee}#${n ?? ''}` : null}
          highlightedId={enAvant?.id ?? suggestion?.id ?? null}
          // La région vient du LIEU : lui seul sait où il est rattaché.
          focus={
            enAvant
              ? { lat: enAvant.lat, lon: enAvant.lon, regionCode: enAvant.regionCode }
              : null
          }
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
          {/* DEUX CRANS, PAS UN SAUT. Toucher un lieu zoome dessus ; la
              pastille ramenait alors au pays entier, et on perdait la région
              qu'on venait d'ouvrir. Elle défait maintenant un geste à la fois
              — le lieu, puis la région — et change de nom entre les deux.

              La grammaire ne bouge pas : le premier mot est toujours la
              DESTINATION, le second l'endroit où l'on est.

                  ‹ Bretagne │ Cathédrale Saint-Vincent
                  ‹ France   │ Bretagne                  */}
          {!enRecherche && regionOuverte ? (
            <Pressable
              style={styles.retourRegion}
              onPress={
                surUnLieu
                  ? () => {
                      // Les deux, sinon le lieu du bandeau reprendrait la main
                      // et la caméra repartirait sur lui.
                      setChoisi(null);
                      setAuMilieu(null);
                      setRetourRegion(retourRegion + 1);
                    }
                  : () => setRetourFrance(retourFrance + 1)
              }
              accessibilityRole="button"
              accessibilityLabel={
                surUnLieu
                  ? `Revenir à ${nomDeRegion(regionOuverte)}, en entier`
                  : `Revenir à ${nomDuPays() || 'la carte'}, en entier`
              }
            >
              <IconeChevron size={17} color={colors.surface} />
              {/* Le pays vient du CATALOGUE, pas d'une constante : la pastille
                  annonçait « France | Toscane » dès qu'on ouvrait une région
                  italienne. */}
              <Text style={styles.retourFrance}>
                {surUnLieu ? nomDeRegion(regionOuverte) : nomDuPays() || 'Pays'}
              </Text>
              <View style={styles.retourFilet} />
              <Text style={styles.retourNom} numberOfLines={1}>
                {surUnLieu && enAvant ? enAvant.name : nomDeRegion(regionOuverte)}
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
                {chargeAilleurs ? ' · RECHERCHE DANS LES AUTRES PAYS…' : ''}
              </Text>
            }
            ListEmptyComponent={
              <EmptyState
                title="Aucun lieu ne répond"
                body="Essaie le nom de la commune, ou du département — beaucoup de lieux sont fichés sous un nom qu'on n'emploie jamais."
              />
            }
            renderItem={({ item }) => (
              <Pressable style={styles.ligne} onPress={() => void ouvrirResultat(item)}>
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
                {/* Le pays ne se dit que lorsqu'il SURPREND : l'écrire sur
                    chaque ligne française serait un rappel inutile, l'omettre
                    sur une ligne italienne ferait croire à un lieu d'à côté. */}
                {item.pays !== pays ? <Pill label={item.nomDuPays} /> : null}
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
              snapToInterval={RANGEE + spacing.sm}
              decelerationRate="fast"
              contentContainerStyle={{ paddingHorizontal: spacing.lg, gap: spacing.sm }}
              onMomentumScrollEnd={(event) => {
                const index = Math.round(
                  event.nativeEvent.contentOffset.x / (RANGEE + spacing.sm),
                );
                setAuMilieu(vignettes[index] ?? null);
              }}
              renderItem={({ item }) => (
                <Pressable
                  style={[styles.rangee, { width: RANGEE }]}
                  onPress={() => openPlace(item)}
                >
                  <Photo
                    url={item.imageUrl}
                    themeId={item.themeId}
                    width={RANGEE_PHOTO}
                    height={RANGEE_PHOTO}
                  />
                  {/* `flex: 1` et `minWidth: 0` : sans le second, un nom long
                      pousse la colonne au-delà de la rangée au lieu de passer
                      à la ligne — la photo se trouve alors rognée à gauche. */}
                  <View style={styles.rangeeTexte}>
                    <Text style={type.subheading} numberOfLines={2}>
                      {item.name}
                    </Text>
                    <View style={styles.ligneVignette}>
                      <Etoiles note={etoilesDe(item.id)} taille={12} />
                      <Text style={type.small} numberOfLines={1}>
                        {distance(item) ?? item.communeName ?? item.departement ?? ''}
                      </Text>
                    </View>
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

          {/* La seule mention d'attribution de l'application, et elle porte
              les trois sources : le FOND (ODbL d'OpenStreetMap), les CONTOURS
              (Licence ouverte) et les PHOTOS (Commons).

              Le fond y est venu parce que le contrôle de MapLibre s'ouvrait
              tout seul au premier rendu, par-dessus cette ligne — deux textes
              superposés à l'ouverture de l'application. Une ligne qui ne se
              replie jamais tient l'obligation mieux qu'une pastille.

              Les contours suivent le PAYS : la ligne était écrite en dur, elle
              créditait donc l'IGN sous des contours italiens, qui viennent de
              l'ISTAT et demandent leur propre mention. */}
          <Text style={styles.credit} numberOfLines={3}>
            {[ATTRIBUTION_DU_FOND, attributionDesContours(), 'Photos Wikimedia Commons']
              .filter(Boolean)
              .join(' · ')}
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
  rangee: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    padding: spacing.sm,
    borderWidth: 1,
    borderColor: colors.border,
  },
  rangeeTexte: { flex: 1, minWidth: 0, gap: 4 },
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
