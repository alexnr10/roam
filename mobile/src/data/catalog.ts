import raw from './catalog.json';
import type { Catalog, Collection, Place, Theme } from '../types';

/**
 * Accès au catalogue.
 *
 * `catalog.json` est produit par `roam_pipeline export-app`. Tant que le
 * pipeline n'a pas tourné, il contient un jeu de démonstration de la même
 * forme. Le passage à un appel réseau borné à l'emprise de la carte ne
 * touchera que ce module.
 */

const catalog = raw as unknown as Catalog;

export const places: Place[] = catalog.places;
export const collections: Collection[] = catalog.collections;
export const themes: Theme[] = catalog.themes;

const placeById = new Map(places.map((place) => [place.id, place]));
const themeById = new Map(themes.map((theme) => [theme.id, theme]));
const collectionBySlug = new Map(collections.map((c) => [c.slug, c]));

/** Collections auxquelles appartient un lieu — plusieurs, c'est tout le produit. */
const collectionsByPlace = new Map<string, Collection[]>();
for (const collection of collections) {
  for (const member of collection.places) {
    const list = collectionsByPlace.get(member.placeId) ?? [];
    list.push(collection);
    collectionsByPlace.set(member.placeId, list);
  }
}

export const getPlace = (id: string): Place | undefined => placeById.get(id);
export const getTheme = (id: string): Theme | undefined => themeById.get(id);
export const getCollection = (slug: string): Collection | undefined =>
  collectionBySlug.get(slug);

export const getCollectionsForPlace = (id: string): Collection[] =>
  collectionsByPlace.get(id) ?? [];

export const getPlacesInCollection = (collection: Collection): Place[] =>
  collection.places
    .map((member) => placeById.get(member.placeId))
    .filter((place): place is Place => Boolean(place));

export const getTierForPlace = (collection: Collection, placeId: string) =>
  collection.places.find((member) => member.placeId === placeId)?.tier ?? null;

export const themeLabel = (themeId: string): string =>
  themeById.get(themeId)?.name ?? themeId;
