import { autourDeToi, chercheCollections, parRegion, territoireDe } from './explorer';
import type { Area, Collection, Place } from '../types';

function col(
  name: string,
  extra: Partial<Collection> = {},
): Collection {
  return {
    slug: name, name, kind: 'geo', geoLevel: 'departement', geoCode: '15',
    placeCount: 10, tierCounts: [1, 2, 3], places: [],
    ...extra,
  } as Collection;
}

function lieu(nom: string, lat: number, lon: number, dept: string, region: string): Place {
  return {
    id: nom, slug: nom, name: nom, themeId: 'monuments', lat, lon, radiusM: 150,
    score: 100, departement: dept, departementCode: dept, regionCode: region,
  } as unknown as Place;
}

const REGIONS: Area[] = [
  { code: '84', name: 'Auvergne-Rhône-Alpes' },
  { code: '11', name: 'Île-de-France' },
];
const DEPTS: Area[] = [
  { code: '15', name: 'Cantal', parentCode: '84' },
  { code: '75', name: 'Paris', parentCode: '11' },
];

describe('territoireDe', () => {
  it('déduit le territoire du lieu le plus proche', () => {
    const lot = [lieu('Paris', 48.85, 2.35, '75', '11'), lieu('Salers', 45.14, 2.49, '15', '84')];
    expect(territoireDe(lot, { latitude: 45.1, longitude: 2.5 }))
      .toEqual({ departement: '15', region: '84' });
  });

  it('ne devine rien sans position', () => {
    const lot = [lieu('Paris', 48.85, 2.35, '75', '11')];
    expect(territoireDe(lot, null)).toEqual({ departement: null, region: null });
  });
});

describe('autourDeToi', () => {
  it('donne le département avant la région : ce qui est à portée de voiture', () => {
    const lot = [
      col('Le meilleur du Cantal', { geoLevel: 'departement', geoCode: '15' }),
      col("Le meilleur d'Auvergne", { geoLevel: 'region', geoCode: '84' }),
      col('Le meilleur de Paris', { geoLevel: 'departement', geoCode: '75' }),
    ];
    expect(autourDeToi(lot, '15', '84').map((c) => c.name))
      .toEqual(['Le meilleur du Cantal', "Le meilleur d'Auvergne"]);
  });

  it('ne rend rien quand on ne sait pas où est le lecteur', () => {
    expect(autourDeToi([col('X')], null, null)).toEqual([]);
  });
});

describe('parRegion', () => {
  it("rattache une collection départementale à la région de son département", () => {
    // Sans quoi « Châteaux du Cantal » serait introuvable pour qui cherche
    // l'Auvergne.
    const lot = [col('Châteaux du Cantal', { geoLevel: 'departement', geoCode: '15' })];
    const range = parRegion(lot, REGIONS, DEPTS);
    expect(range).toHaveLength(1);
    expect(range[0].nom).toBe('Auvergne-Rhône-Alpes');
    expect(range[0].collections.map((c) => c.name)).toEqual(['Châteaux du Cantal']);
  });

  it('met la collection de la région entière avant celles de ses départements', () => {
    const lot = [
      col('Le meilleur du Cantal', { geoLevel: 'departement', geoCode: '15' }),
      col("Le meilleur d'Auvergne", { geoLevel: 'region', geoCode: '84' }),
    ];
    expect(parRegion(lot, REGIONS, DEPTS)[0].collections.map((c) => c.name))
      .toEqual(["Le meilleur d'Auvergne", 'Le meilleur du Cantal']);
  });

  it('ignore les collections qui ne sont pas géographiques', () => {
    const lot = [col('Châteaux', { kind: 'theme', geoLevel: null, geoCode: null })];
    expect(parRegion(lot, REGIONS, DEPTS)).toEqual([]);
  });

  it('ne montre pas une région sans collection', () => {
    const lot = [col('Le meilleur de Paris', { geoLevel: 'departement', geoCode: '75' })];
    expect(parRegion(lot, REGIONS, DEPTS).map((t) => t.nom)).toEqual(['Île-de-France']);
  });
});

describe('chercheCollections', () => {
  it('trouve le Cantal quand on prépare le Cantal, sans accent ni casse', () => {
    const lot = [col('Le meilleur du Cantal'), col('Châteaux de Bretagne')];
    expect(chercheCollections(lot, 'CANTAL').map((c) => c.name))
      .toEqual(['Le meilleur du Cantal']);
    expect(chercheCollections(lot, 'bretagne').map((c) => c.name))
      .toEqual(['Châteaux de Bretagne']);
  });

  it('attend deux caractères avant de répondre', () => {
    expect(chercheCollections([col('Cantal')], 'c')).toEqual([]);
  });

  it('met les collections les plus fournies devant', () => {
    const lot = [col('Cantal petit', { placeCount: 8 }), col('Cantal grand', { placeCount: 40 })];
    expect(chercheCollections(lot, 'cantal').map((c) => c.name))
      .toEqual(['Cantal grand', 'Cantal petit']);
  });
});
