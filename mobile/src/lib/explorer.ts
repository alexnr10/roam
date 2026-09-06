import { fold } from './search';
import type { Area, Collection, Coordinates, Place } from '../types';

/**
 * Ranger deux cents collections pour qu'elles servent à quelqu'un.
 *
 * « Le meilleur du Cantal » n'intéresse que deux personnes : celle qui y
 * habite, et celle qui prépare d'y aller. Les afficher toutes, à plat, ne
 * s'adresse donc à personne — cent soixante-dix cartes géographiques que
 * personne ne parcourt jusqu'au bout.
 *
 * D'où trois portes, et une seule liste exhaustive :
 *
 * 1. **Là où tu es.** Déduit du lieu le plus proche, pas d'un service tiers :
 *    le catalogue sait déjà dans quel département tombe chaque lieu.
 * 2. **Là où tu vas.** Une recherche par nom — on tape « Cantal » quand on
 *    prépare le Cantal.
 * 3. **Le reste, par région.** Dix-huit portes au lieu de cent soixante-dix.
 */

export type Territoire = { code: string; nom: string; collections: Collection[] };

/** Le département et la région du lieu le plus proche. */
export function territoireDe(
  places: Place[],
  position: Coordinates | null,
): { departement: string | null; region: string | null } {
  if (!position) return { departement: null, region: null };
  let proche: Place | null = null;
  let meilleure = Infinity;
  for (const place of places) {
    // Distance au carré en degrés : on cherche un rang, pas une mesure, et
    // parcourir deux mille lieux à chaque rendu doit rester gratuit.
    const d = (place.lat - position.latitude) ** 2 + (place.lon - position.longitude) ** 2;
    if (d < meilleure) {
      meilleure = d;
      proche = place;
    }
  }
  return {
    departement: proche?.departementCode ?? null,
    region: proche?.regionCode ?? null,
  };
}

/**
 * Les collections qui parlent d'ici : celles du département d'abord, puis
 * celles de la région. Le département avant la région parce qu'on cherche
 * d'abord ce qui est à portée de voiture.
 */
export function autourDeToi(
  collections: Collection[],
  departement: string | null,
  region: string | null,
): Collection[] {
  if (!departement && !region) return [];
  const dedans = (niveau: string, code: string | null) =>
    code
      ? collections.filter((c) => c.geoLevel === niveau && c.geoCode === code)
      : [];
  return [...dedans('departement', departement), ...dedans('region', region)];
}

/**
 * Les collections géographiques rangées par région.
 *
 * Une collection départementale rejoint la région de son département : sans
 * quoi « Châteaux du Cantal » serait introuvable pour qui cherche l'Auvergne.
 */
export function parRegion(
  collections: Collection[],
  regions: Area[],
  departements: Area[],
): Territoire[] {
  const regionDuDept = new Map(departements.map((d) => [d.code, d.parentCode ?? null]));
  const paniers = new Map<string, Collection[]>();

  for (const collection of collections) {
    if (collection.kind !== 'geo' || !collection.geoCode) continue;
    const code =
      collection.geoLevel === 'region'
        ? collection.geoCode
        : collection.geoLevel === 'departement'
          ? regionDuDept.get(collection.geoCode) ?? null
          : null;
    if (!code) continue;
    const panier = paniers.get(code) ?? [];
    panier.push(collection);
    paniers.set(code, panier);
  }

  return regions
    .filter((region) => paniers.has(region.code))
    .map((region) => ({
      code: region.code,
      nom: region.name,
      // Les collections de la région entière avant celles d'un seul de ses
      // départements : on descend l'échelle, on ne la mélange pas.
      collections: (paniers.get(region.code) ?? []).sort(
        (a, b) =>
          Number(a.geoLevel !== 'region') - Number(b.geoLevel !== 'region') ||
          b.placeCount - a.placeCount,
      ),
    }))
    .sort((a, b) => a.nom.localeCompare(b.nom, 'fr'));
}

/** Recherche par nom, accents et casse ignorés — « cantal » trouve le Cantal. */
export function chercheCollections(collections: Collection[], query: string): Collection[] {
  const q = fold(query).trim();
  if (q.length < 2) return [];
  return collections
    .filter((collection) => fold(collection.name).includes(q))
    .sort((a, b) => b.placeCount - a.placeCount);
}
