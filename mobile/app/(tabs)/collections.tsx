import { useRouter } from 'expo-router';
import React, { useMemo, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import {
  collections,
  getPlacesInCollection,
  places as toutes,
} from '../../src/data/catalog';
import { autourDeToi, chercheCollections, territoireDe } from '../../src/lib/explorer';
import { useCatalogue } from '../../src/lib/useCatalogue';
import { useLocation } from '../../src/lib/useLocation';
import { LARGEUR_MAX, colors, radius, spacing, type } from '../../src/theme';
import { Photo, SearchField } from '../../src/ui/components';
import { IconeChevronDroit } from '../../src/ui/icons';
import { SilhouetteRegion } from '../../src/ui/regionShape';
import { REGIONS, nomDeRegion } from '../../src/lib/regions';
import type { Collection } from '../../src/types';

/**
 * Explorer : trouver quoi faire ici, ou là où l'on va.
 *
 * L'écran affichait deux cents collections à plat, dont cent soixante-dix
 * géographiques. « Le meilleur du Cantal » n'intéresse que deux personnes :
 * celle qui y habite et celle qui prépare d'y aller — les montrer toutes ne
 * s'adresse donc à personne.
 *
 * Trois portes remplacent la liste : là où tu es, là où tu vas (par le nom),
 * et le reste par région — dix-huit portes au lieu de cent soixante-dix.
 *
 * La progression n'apparaît plus ici. Elle a sa place dans « Moi » : c'est une
 * récompense, et ce n'est pas ce qu'on vient chercher quand on cherche où
 * aller ce week-end.
 */
export default function ExplorerScreen() {
  // Le catalogue peut changer de pays sous nos pieds : on s'y abonne.
  const catalogue = useCatalogue();
  const router = useRouter();
  const { position } = useLocation();
  const [query, setQuery] = useState('');

  const ici = useMemo(() => territoireDe(toutes, position), [position, catalogue]);
  const proches = useMemo(
    () => autourDeToi(collections, ici.departement, ici.region),
    [ici.departement, ici.region],
  );
  const trouvees = useMemo(
    () => chercheCollections(collections, query),
    [query, catalogue],
  );

  /**
   * Les régions, avec leur nombre de lieux — et l'outre-mer à part.
   *
   * À part dans la LISTE, pas dans le traitement : même ligne, même
   * silhouette, même geste. L'intertitre ne fait que les rendre trouvables.
   */
  const regionsCarte = useMemo(() => {
    const compte = new Map<string, number>();
    for (const lieu of toutes) {
      if (!lieu.regionCode) continue;
      compte.set(lieu.regionCode, (compte.get(lieu.regionCode) ?? 0) + 1);
    }
    return [...REGIONS.keys()]
      .map((code) => ({ code, nom: nomDeRegion(code), lieux: compte.get(code) ?? 0 }))
      .filter((entree) => entree.lieux > 0)
      .sort((a, b) => a.nom.localeCompare(b.nom, 'fr'));
  }, []);
  const metropole = regionsCarte.filter((entree) => !OUTRE_MER.has(entree.code));
  const outreMer = regionsCarte.filter((entree) => OUTRE_MER.has(entree.code));

  /** Le retour sur la carte, région ouverte. Le nonce distingue deux appuis. */
  const ouvrirSurLaCarte = (code: string) =>
    router.push({ pathname: '/', params: { region: code, n: String(Date.now()) } });
  const enRecherche = query.trim().length >= 2;

  const themes = collections.filter((c) => c.kind === 'theme');
  const labels = collections.filter((c) => c.kind === 'label');

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
      keyboardShouldPersistTaps="handled"
    >
      <SearchField
        value={query}
        onChange={setQuery}
        placeholder="Une région, un département, un thème"
      />

      {enRecherche ? (
        <Bloc
          titre={`${trouvees.length} collection${trouvees.length > 1 ? 's' : ''}`}
          items={trouvees}
          router={router}
        />
      ) : (
        <>
          {proches.length ? (
            <Bloc
              titre="Autour de toi"
              blurb="Ce qu'il y a à voir dans ton département, puis dans ta région"
              items={proches}
              router={router}
            />
          ) : null}

          <Bloc
            titre="Par thème"
            blurb="Châteaux, cascades, sommets — la colonne vertébrale du guide"
            items={themes}
            router={router}
          />

          <Bloc
            titre="Les listes officielles"
            blurb="Déjà curées par d'autres : Plus Beaux Villages, UNESCO, Grands Sites"
            items={labels}
            router={router}
          />

          <Text style={[type.heading, { marginTop: spacing.xl }]}>Par région</Text>
          <Text style={[type.small, { marginBottom: spacing.md }]}>
            Touche une région : elle s'ouvre sur la carte, cadrée, avec ses lieux
          </Text>
          {metropole.map((entree) => (
            <LigneRegion key={entree.code} entree={entree} onOuvrir={ouvrirSurLaCarte} />
          ))}

          {/* L'outre-mer a sa porte d'entrée, et c'est ICI qu'elle est.
              Sur la carte, cadrée sur la métropole, ces cinq régions sont hors
              écran : personne ne les trouve en faisant glisser au hasard. Un
              encart dans un coin de la carte aurait menti sur ce qu'elles sont
              — ce sont des régions comme les autres, et elles figurent donc
              dans la même liste, avec leur silhouette et leur décompte. */}
          {outreMer.length ? (
            <>
              <Text style={[type.kicker, { marginTop: spacing.xl }]}>Outre-mer</Text>
              <Text style={[type.small, { marginBottom: spacing.md }]}>
                Cinq régions comme les autres — la seule porte d'entrée qui ne demande
                pas de savoir qu'elles existent
              </Text>
              {outreMer.map((entree) => (
                <LigneRegion key={entree.code} entree={entree} onOuvrir={ouvrirSurLaCarte} />
              ))}
            </>
          ) : null}
        </>
      )}
    </ScrollView>
  );
}

/** Les cinq régions d'outre-mer, par leur code INSEE. */
const OUTRE_MER = new Set(['01', '02', '03', '04', '06']);

/**
 * Une région, en une ligne.
 *
 * Une liste de dix-huit noms se lit ; une liste de dix-huit FORMES se
 * reconnaît. La silhouette porte le sable de la région sur la carte : on la
 * retrouve d'un écran à l'autre sans avoir à la nommer.
 */
function LigneRegion({
  entree,
  onOuvrir,
}: {
  entree: { code: string; nom: string; lieux: number };
  onOuvrir: (code: string) => void;
}) {
  return (
    <Pressable
      style={styles.ligneRegion}
      onPress={() => onOuvrir(entree.code)}
      accessibilityRole="button"
      accessibilityLabel={`Ouvrir ${entree.nom} sur la carte`}
    >
      <SilhouetteRegion code={entree.code} />
      <Text style={[type.subheading, { flex: 1 }]} numberOfLines={1}>
        {entree.nom}
      </Text>
      <Text style={type.small}>{entree.lieux} lieux</Text>
      <IconeChevronDroit size={16} color={colors.locked} />
    </Pressable>
  );
}

function Bloc({
  titre,
  blurb,
  items,
  router,
}: {
  titre: string;
  blurb?: string;
  items: Collection[];
  router: ReturnType<typeof useRouter>;
}) {
  if (items.length === 0) return null;
  return (
    <View style={{ marginTop: spacing.xl }}>
      <Text style={type.heading}>{titre}</Text>
      {blurb ? <Text style={[type.small, { marginBottom: spacing.md }]}>{blurb}</Text> : null}
      {items.map((collection) => (
        <Carte key={collection.slug} collection={collection} router={router} />
      ))}
    </View>
  );
}

/**
 * Une collection se montre par une photo, pas par une barre de progression.
 *
 * On choisit d'aller quelque part parce qu'on a vu à quoi ça ressemble. La
 * vignette est celle du lieu le mieux classé — c'est aussi la promesse la plus
 * honnête qu'une collection puisse faire.
 */
function Carte({
  collection,
  router,
}: {
  collection: Collection;
  router: ReturnType<typeof useRouter>;
}) {
  const tete = useMemo(() => {
    const membres = getPlacesInCollection(collection);
    return membres.find((place) => place.imageUrl) ?? membres[0] ?? null;
  }, [collection]);

  return (
    <Pressable
      style={styles.carte}
      onPress={() => router.push(`/collection/${collection.slug}`)}
    >
      <Photo
        url={tete?.imageUrl}
        themeId={tete?.themeId ?? collection.themeId ?? 'monuments'}
        width={72}
        height={72}
      />
      <View style={{ flex: 1, gap: 2 }}>
        <Text style={type.subheading} numberOfLines={2}>
          {collection.name}
        </Text>
        <Text style={type.small}>
          {collection.placeCount} lieux · {collection.tierCounts[0]} incontournables
        </Text>
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  carte: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.lg,
    padding: spacing.sm,
    marginBottom: spacing.sm,
  },
  ligneRegion: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 13,
    height: 56,
    borderTopWidth: 1,
    borderTopColor: colors.border,
  },
});
