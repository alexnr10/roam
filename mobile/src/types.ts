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
  /**
   * Le crédit de la photo. Une image de Commons n'est pas libre de droits :
   * la plupart des licences exigent de citer l'auteur, et le catalogue en
   * publie deux mille. `null` = Commons ne le documente pas.
   */
  imageAuthor?: string | null;
  imageLicence?: string | null;
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
  /**
   * Le nom court, pour les rangées de pastilles où la place manque.
   *
   * « Monuments et édifices remarquables » dit ce que contient la collection,
   * et c'est le bon nom sur sa page. Dans le filtre au-dessus de la carte, il
   * en occupe la largeur entière : on voyait deux thèmes sur vingt-trois.
   */
  nameShort?: string;
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

/**
 * Un lieu qu'on s'est promis d'aller voir.
 *
 * Roam est un guide avant d'être une collection : le carnet de visites dit
 * d'où l'on vient, celui-ci dit où l'on va. Les deux ne se mélangent jamais —
 * une envie réalisée SORT de la liste, elle n'y reste pas cochée.
 */
export type Envie = {
  placeId: string;
  /** Sert à montrer les dernières envies en premier. */
  addedAt: string;
};

export type Coordinates = {
  latitude: number;
  longitude: number;
  /** Précision annoncée par le téléphone, en mètres. */
  accuracy?: number | null;
};
