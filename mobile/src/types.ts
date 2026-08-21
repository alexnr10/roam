/**
 * Formes de données du catalogue.
 *
 * Elles reprennent exactement la sortie du pipeline de curation
 * (`pipeline/data/out/places.json` et `collections.json`) : remplacer le
 * catalogue de démonstration par le catalogue réel ne demandera aucun
 * changement de code.
 */

export type Tier = 1 | 2 | 3;

export type Place = {
  /** Identifiant Wikidata — clé stable du catalogue. */
  id: string;
  slug: string;
  name: string;
  themeId: string;
  lat: number;
  lon: number;
  /** Rayon de validation GPS, en mètres. Porte la taille du site. */
  radiusM: number;
  score: number;
  departement: string | null;
  regionCode: string | null;
  summary?: string;
  imageUrl?: string | null;
};

export type CollectionKind = 'theme' | 'geo' | 'label';

export type CollectionMember = {
  placeId: string;
  tier: Tier;
  rank: number;
};

export type Collection = {
  slug: string;
  name: string;
  kind: CollectionKind;
  themeId?: string | null;
  labelId?: string | null;
  geoLevel?: string | null;
  geoCode?: string | null;
  placeCount: number;
  /** Nombre de lieux par niveau : [niveau 1, niveau 2, niveau 3]. */
  tierCounts: [number, number, number];
  places: CollectionMember[];
};

export type Theme = {
  id: string;
  name: string;
  nameSingular: string;
  icon: string;
};

export type Catalog = {
  places: Place[];
  collections: Collection[];
  themes: Theme[];
};

/** Comment une visite a été enregistrée. */
export type VisitMethod = 'gps' | 'declared';

export type Visit = {
  placeId: string;
  method: VisitMethod;
  /** Vrai uniquement pour une validation GPS sur place : donne le badge « vérifié ». */
  verified: boolean;
  visitedAt: string;
  distanceM?: number;
};

export type Coordinates = {
  latitude: number;
  longitude: number;
  /** Précision annoncée par le téléphone, en mètres. */
  accuracy?: number | null;
};
