import {
  ALMOST_DONE_REMAINING, NEARBY_RADIUS_M, byProgressThenDistance, formatDistance,
  haversineM, nearestPlaceM, rank, shortlists,
} from './shortlist';
import type { CollectionProgress } from './progress';
import type { Collection } from '../types';

const PARIS = { latitude: 48.8566, longitude: 2.3522 };

function collection(slug: string, total: number): Collection {
  return {
    slug, name: slug, kind: 'geo', placeCount: total, tierCounts: [0, 0, total],
    places: Array.from({ length: total }, (_, i) => ({
      placeId: `${slug}-${i}`, tier: 3 as const, rank: i + 1,
    })),
  } as Collection;
}

function progress(slug: string, visited: number, total: number): CollectionProgress {
  return {
    slug, visited, verified: 0, total,
    pct: total ? Math.round((visited / total) * 100) : 0,
    tiers: [], currentTier: 1, complete: visited >= total,
  } as CollectionProgress;
}

describe('distances', () => {
  it('mesure la distance au lieu le PLUS PROCHE, pas au centre', () => {
    // Le centre d'une collection nationale tombe au milieu de la France et ne
    // veut rien dire ; ce qui compte est le premier lieu atteignable.
    const proche = { lat: 48.86, lon: 2.35 };
    const loin = { lat: 43.3, lon: 5.4 };
    expect(nearestPlaceM([loin, proche], PARIS)).toBeLessThan(1000);
  });

  it('rend null quand la collection est vide', () => {
    expect(nearestPlaceM([], PARIS)).toBeNull();
  });

  it('formate en mètres puis en kilomètres', () => {
    expect(formatDistance(340)).toBe('300 m');
    expect(formatDistance(12_400)).toBe('12 km');
    expect(formatDistance(643_000)).toBe('640 km');
    expect(formatDistance(null)).toBeNull();
  });
});

describe('les trois listes', () => {
  const placesOf = (c: Collection) =>
    c.slug === 'loin'
      ? [{ lat: 43.3, lon: 5.4 }]        // Marseille, ~660 km
      : [{ lat: 48.86, lon: 2.35 }];     // Paris

  function build(etats: Array<[string, number, number]>) {
    const cols = etats.map(([slug, , total]) => collection(slug, total));
    const par = new Map(etats.map(([slug, visited, total]) =>
      [slug, progress(slug, visited, total)]));
    return shortlists(rank(cols, (c) => par.get(c.slug)!, placesOf, PARIS));
  }

  it('remonte une collection lointaine à laquelle il ne manque qu un lieu', () => {
    // C est tout l intérêt : elle donne envie de traverser le pays.
    const { almostDone, nearby } = build([['loin', 9, 10], ['proche', 0, 10]]);
    expect(almostDone.map((r) => r.collection.slug)).toEqual(['loin']);
    expect(nearby.map((r) => r.collection.slug)).toEqual(['proche']);
  });

  it('ne dit pas « presque finie » d une collection jamais commencée', () => {
    // Sans cela, toute collection de deux lieux le serait d emblée.
    const { almostDone } = build([['neuve', 0, ALMOST_DONE_REMAINING]]);
    expect(almostDone).toEqual([]);
  });

  it('écarte les collections terminées des deux listes de tête', () => {
    const { almostDone, nearby, rest } = build([['finie', 10, 10]]);
    expect(almostDone).toEqual([]);
    expect(nearby).toEqual([]);
    expect(rest.map((r) => r.collection.slug)).toEqual(['finie']);
  });

  it('ne met pas dans « près de toi » ce qui est à six cents kilomètres', () => {
    const { nearby, rest } = build([['loin', 0, 10]]);
    expect(nearby).toEqual([]);
    expect(rest.map((r) => r.collection.slug)).toEqual(['loin']);
    expect(NEARBY_RADIUS_M).toBeLessThan(660_000);
  });

  it('ne place jamais la même collection dans deux listes', () => {
    const { almostDone, nearby, rest } = build([
      ['loin', 9, 10], ['proche', 0, 10], ['autre', 0, 10],
    ]);
    const vus = [...almostDone, ...nearby, ...rest].map((r) => r.collection.slug);
    expect(new Set(vus).size).toBe(vus.length);
  });
});

describe('ordre du reste', () => {
  it('la progression prime, la distance départage', () => {
    // C est le point : à 0 %, le tri par progression ne triait RIEN et le
    // nouvel arrivant voyait 253 collections dans l ordre du fichier.
    const a = { progress: progress('a', 0, 10), distanceM: 500_000 } as never;
    const b = { progress: progress('b', 0, 10), distanceM: 10_000 } as never;
    expect(byProgressThenDistance(a, b)).toBeGreaterThan(0);

    const avance = { progress: progress('c', 5, 10), distanceM: 900_000 } as never;
    expect(byProgressThenDistance(avance, b)).toBeLessThan(0);
  });
});

describe('sans position', () => {
  it('classe quand même, sans distance', () => {
    const cols = [collection('a', 10)];
    const par = new Map([['a', progress('a', 0, 10)]]);
    const classe = rank(cols, (c) => par.get(c.slug)!, () => [{ lat: 48, lon: 2 }], null);
    expect(classe[0].distanceM).toBeNull();
    expect(shortlists(classe).nearby).toEqual([]);
    expect(shortlists(classe).rest).toHaveLength(1);
  });
});
