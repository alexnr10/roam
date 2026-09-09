import embarque from './catalog.json';
import type { Area, AreaLevel, Catalog, Collection, Place, Theme } from '../types';

/**
 * Accès au catalogue — d'UN pays à la fois.
 *
 * `catalog.json` est produit par `roam_pipeline export-app` : c'est le
 * catalogue EMBARQUÉ, celui du pays de départ, disponible sans réseau au
 * premier lancement. Les autres se chargent à la demande et remplacent
 * celui-ci.
 *
 * Pourquoi un seul à la fois plutôt que tous ensemble ? Parce qu'une étoile
 * dit un rang dans une collection NATIONALE : mélanger deux pays ferait
 * disputer au Colisée la place du Pont du Gard, et l'utilisateur qui prépare
 * un voyage en Italie se moque des plages françaises. C'est la même règle que
 * côté pipeline, où l'entonnoir tourne une fois par pays.
 *
 * ⚠️ Les quatre tableaux ci-dessous sont des `let` EXPORTÉS, et c'est
 * délibéré : en modules ES, une importation est un lien vivant, pas une copie.
 * Les quinze modules qui écrivent `import { places } from '../data/catalog'`
 * voient donc le nouveau catalogue sans qu'aucun d'eux ne change d'une ligne.
 * Ce qui NE suit pas tout seul, ce sont les valeurs qu'un module a dérivées
 * une fois pour toutes au chargement — d'où `surChangement`, auquel ces
 * modules-là s'abonnent pour se reconstruire.
 */

let catalogue = embarque as unknown as Catalog;

export let places: Place[] = catalogue.places;
export let collections: Collection[] = catalogue.collections;
export let themes: Theme[] = catalogue.themes;

/**
 * Territoires occupés par le catalogue, par échelle.
 *
 * Le repli sur des listes vides couvre un catalogue produit avant que le
 * pipeline n'exporte ce répertoire : la carte de conquête se montre alors
 * vide plutôt que de faire planter l'application.
 */
export let areas: Record<AreaLevel, Area[]> = niveaux(catalogue);

function niveaux(source: Catalog): Record<AreaLevel, Area[]> {
  return {
    commune: source.areas?.commune ?? [],
    departement: source.areas?.departement ?? [],
    region: source.areas?.region ?? [],
    country: source.areas?.country ?? [],
  };
}

let placeById = new Map<string, Place>();
let themeById = new Map<string, Theme>();
let collectionBySlug = new Map<string, Collection>();
let collectionsByPlace = new Map<string, Collection[]>();

function indexer(): void {
  placeById = new Map(places.map((place) => [place.id, place]));
  themeById = new Map(themes.map((theme) => [theme.id, theme]));
  collectionBySlug = new Map(collections.map((c) => [c.slug, c]));
  collectionsByPlace = new Map<string, Collection[]>();
  for (const collection of collections) {
    for (const member of collection.places) {
      const list = collectionsByPlace.get(member.placeId) ?? [];
      list.push(collection);
      collectionsByPlace.set(member.placeId, list);
    }
  }
}

indexer();

/** Les modules qui dérivent du catalogue et doivent se refaire quand il change. */
const abonnes = new Set<() => void>();

export function surChangement(refaire: () => void): () => void {
  abonnes.add(refaire);
  return () => abonnes.delete(refaire);
}

/**
 * Remplace le catalogue courant. C'est le seul chemin par lequel il change.
 *
 * L'ordre importe : on réindexe AVANT de prévenir, sinon un abonné qui
 * interroge `getPlace` pendant sa reconstruction lirait l'ancien catalogue.
 */
export function chargerCatalogue(source: Catalog): void {
  catalogue = source;
  places = source.places;
  collections = source.collections;
  themes = source.themes;
  areas = niveaux(source);
  indexer();
  for (const refaire of abonnes) refaire();
}

/** Le code du pays courant — « FR », « IT ». Vide si le catalogue n'en dit rien. */
export const paysCourant = (): string => areas.country[0]?.code ?? '';

/** Le nom du pays courant, tel qu'il s'affiche. */
export const nomDuPays = (): string => areas.country[0]?.name ?? '';

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

/** Le nom court d'un thème, ou son nom complet quand il tient déjà. */
export const themeLabelCourt = (themeId: string): string => {
  const theme = themeById.get(themeId);
  return theme?.nameShort || theme?.name || themeId;
};
