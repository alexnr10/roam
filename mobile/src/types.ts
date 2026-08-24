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
  /**
   * Codes des territoires auxquels le lieu appartient.
   *
   * Ce sont des CLÉS, là où `departement` n'est qu'un libellé : la carte de
   * conquête regroupe par territoire, et deux communes françaises peuvent
   * porter le même nom.
   */
  departementCode: string | null;
  regionCode: string | null;
  communeCode?: string | null;
  communeName?: string | null;
  summary?: string | null;
  imageUrl?: string | null;
  /** Source de la description : l'écran du lieu doit y renvoyer (CC BY-SA). */
  wikipediaUrl?: string | null;
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

/** Les quatre échelles de la carte de conquête. */
export type AreaLevel = 'commune' | 'departement' | 'region' | 'country';

export type Area = {
  code: string;
  name: string;
  /** « du Cantal », « de l'Eure » — le français ne se dérive pas d'une règle. */
  deForm?: string;
  /** Territoire englobant : le département d'une commune, la région d'un département. */
  parentCode?: string | null;
};

export type Catalog = {
  places: Place[];
  collections: Collection[];
  themes: Theme[];
  /**
   * Répertoire des territoires occupés par le catalogue, par échelle.
   *
   * Seulement ceux qui contiennent au moins un lieu : nommer les mille
   * communes du catalogue ne demande pas d'embarquer les trente-cinq mille
   * communes de France.
   */
  areas: Record<AreaLevel, Area[]>;
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
