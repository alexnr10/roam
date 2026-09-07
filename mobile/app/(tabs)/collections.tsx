import { useRouter } from 'expo-router';
import React, { useMemo, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import {
  areas,
  collections,
  getPlacesInCollection,
  places as toutes,
} from '../../src/data/catalog';
import { autourDeToi, chercheCollections, parRegion, territoireDe } from '../../src/lib/explorer';
import { useLocation } from '../../src/lib/useLocation';
import { LARGEUR_MAX, colors, radius, spacing, type } from '../../src/theme';
import { Photo, SearchField } from '../../src/ui/components';
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
  const router = useRouter();
  const { position } = useLocation();
  const [query, setQuery] = useState('');
  const [region, setRegion] = useState<string | null>(null);

  const ici = useMemo(() => territoireDe(toutes, position), [position]);
  const proches = useMemo(
    () => autourDeToi(collections, ici.departement, ici.region),
    [ici.departement, ici.region],
  );
  const territoires = useMemo(
    () => parRegion(collections, areas.region, areas.departement),
    [],
  );
  const trouvees = useMemo(() => chercheCollections(collections, query), [query]);
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

          <Text style={type.heading}>Par région</Text>
          <Text style={[type.small, { marginBottom: spacing.md }]}>
            Pour préparer un voyage — touche une région pour voir ses collections
          </Text>
          {territoires.map((territoire) => (
            <View key={territoire.code}>
              <Pressable
                style={styles.region}
                onPress={() =>
                  setRegion(region === territoire.code ? null : territoire.code)
                }
              >
                <Text style={type.subheading}>{territoire.nom}</Text>
                <Text style={type.small}>
                  {territoire.collections.length} · {region === territoire.code ? '▾' : '▸'}
                </Text>
              </Pressable>
              {region === territoire.code
                ? territoire.collections.map((collection) => (
                    <Carte key={collection.slug} collection={collection} router={router} />
                  ))
                : null}
            </View>
          ))}
        </>
      )}
    </ScrollView>
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
  region: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: spacing.md,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.border,
  },
});
