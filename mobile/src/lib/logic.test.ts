import { distanceM, formatDistance, placesNear, regionAround } from './geo';
import { APPROACH_FACTOR, evaluateCheckIn, suggestCheckIn } from './checkin';
import {
  BADGE_THRESHOLDS,
  computeProgress,
  describeCheckIn,
  earnedBadges,
  nextMilestone,
} from './progress';
import { makeVisit } from './visit';
import type { Collection, Place, Tier, Visit } from '../types';

const place = (over: Partial<Place> = {}): Place => ({
  id: 'Q1',
  slug: 'lieu',
  name: 'Lieu',
  themeId: 'chateaux',
  lat: 45,
  lon: 2,
  radiusM: 150,
  score: 100,
  departement: 'Cantal',
  departementCode: '15',
  regionCode: '84',
  ...over,
});

const collection = (members: Array<[string, Tier]>): Collection => ({
  slug: 'theme-chateaux',
  name: 'Châteaux',
  kind: 'theme',
  placeCount: members.length,
  tierCounts: [
    members.filter(([, t]) => t === 1).length,
    members.filter(([, t]) => t === 2).length,
    members.filter(([, t]) => t === 3).length,
  ],
  places: members.map(([placeId, tier], index) => ({ placeId, tier, rank: index + 1 })),
});

const visit = (placeId: string, verified = true): Visit => ({
  placeId,
  method: verified ? 'gps' : 'declared',
  verified,
  visitedAt: '2026-01-01T00:00:00.000Z',
});

describe('geo', () => {
  it('mesure une distance connue', () => {
    // Paris → Lyon ≈ 392 km
    expect(distanceM(48.8566, 2.3522, 45.764, 4.8357) / 1000).toBeCloseTo(392, -1);
  });

  it('renvoie zéro pour un point sur lui-même', () => {
    expect(distanceM(45, 2, 45, 2)).toBe(0);
  });

  it('formate sans décimale inutile', () => {
    expect(formatDistance(243)).toBe('240 m');
    expect(formatDistance(3210)).toBe('3,2 km');
    expect(formatDistance(87_400)).toBe('87 km');
    expect(formatDistance(NaN)).toBe('—');
  });

  it('trie les lieux proches par distance croissante', () => {
    const near = placesNear(
      [
        place({ id: 'loin', lat: 45.5, lon: 2 }),
        place({ id: 'proche', lat: 45.01, lon: 2 }),
      ],
      { latitude: 45, longitude: 2 },
      100_000,
    );
    expect(near.map((entry) => entry.place.id)).toEqual(['proche', 'loin']);
  });

  it('exclut les lieux hors rayon', () => {
    const near = placesNear([place({ lat: 46, lon: 2 })], { latitude: 45, longitude: 2 }, 1000);
    expect(near).toHaveLength(0);
  });

  it('élargit le delta de longitude avec la latitude', () => {
    const sud = regionAround(43, 2, 1000);
    const nord = regionAround(50, 2, 1000);
    expect(nord.longitudeDelta).toBeGreaterThan(sud.longitudeDelta);
  });
});

describe('validation de visite', () => {
  it('autorise la validation dans le rayon', () => {
    const result = evaluateCheckIn(place(), { latitude: 45.0005, longitude: 2, accuracy: 10 });
    expect(result.status).toBe('ready');
    expect(result.canCheckIn).toBe(true);
  });

  it('refuse une position trop imprécise, même sur place', () => {
    // Un faux positif abîme la confiance dans la collection ; mieux vaut attendre.
    const result = evaluateCheckIn(place(), { latitude: 45, longitude: 2, accuracy: 400 });
    expect(result.status).toBe('imprecise');
    expect(result.canCheckIn).toBe(false);
  });

  it('signale l’approche juste hors du rayon', () => {
    const result = evaluateCheckIn(
      place({ radiusM: 150 }),
      { latitude: 45.003, longitude: 2, accuracy: 5 },
    );
    expect(result.status).toBe('approaching');
    expect(result.message).toMatch(/Encore/);
  });

  it('bascule sur « loin » au-delà du facteur d’approche', () => {
    const radiusM = 150;
    const beyond = (radiusM * APPROACH_FACTOR * 2) / 111_320;
    const result = evaluateCheckIn(
      place({ radiusM }),
      { latitude: 45 + beyond, longitude: 2, accuracy: 5 },
    );
    expect(result.status).toBe('far');
  });

  it('gère l’absence de position', () => {
    expect(evaluateCheckIn(place(), null).status).toBe('unknown');
  });

  it('respecte le rayon propre à chaque lieu', () => {
    const position = { latitude: 45.008, longitude: 2, accuracy: 5 };
    expect(evaluateCheckIn(place({ radiusM: 150 }), position).canCheckIn).toBe(false);
    // Un site étendu (gorges, massif) porte sa taille dans son rayon.
    expect(evaluateCheckIn(place({ radiusM: 2000 }), position).canCheckIn).toBe(true);
  });
});

describe('suggestion de validation', () => {
  const position = { latitude: 45, longitude: 2, accuracy: 5 };

  it('propose le lieu le plus proche non visité', () => {
    const suggestion = suggestCheckIn(
      [
        place({ id: 'A', lat: 45.0008, lon: 2 }),
        place({ id: 'B', lat: 45.0002, lon: 2 }),
      ],
      position,
      new Set(),
    );
    expect(suggestion?.id).toBe('B');
  });

  it('ignore les lieux déjà validés', () => {
    const suggestion = suggestCheckIn(
      [place({ id: 'A', lat: 45.0002, lon: 2 })],
      position,
      new Set(['A']),
    );
    expect(suggestion).toBeNull();
  });

  it('ne propose rien hors de portée', () => {
    expect(suggestCheckIn([place({ lat: 46, lon: 2 })], position, new Set())).toBeNull();
  });
});

describe('progression', () => {
  const sample = collection([
    ['t1a', 1], ['t1b', 1],
    ['t2a', 2], ['t2b', 2],
    ['t3a', 3],
  ]);

  it('compte les visites et le pourcentage', () => {
    const progress = computeProgress(sample, [visit('t1a'), visit('t2a')]);
    expect(progress.visited).toBe(2);
    expect(progress.total).toBe(5);
    expect(progress.pct).toBe(40);
  });

  it('distingue les visites vérifiées des visites déclarées', () => {
    const progress = computeProgress(sample, [visit('t1a', true), visit('t1b', false)]);
    expect(progress.visited).toBe(2);
    expect(progress.verified).toBe(1);
  });

  it('garde le niveau 2 verrouillé tant que le niveau 1 n’est pas fini', () => {
    const progress = computeProgress(sample, [visit('t1a')]);
    expect(progress.tiers[0].unlocked).toBe(true);
    expect(progress.tiers[1].unlocked).toBe(false);
    expect(progress.currentTier).toBe(1);
  });

  it('débloque le niveau suivant à la complétion du précédent', () => {
    const progress = computeProgress(sample, [visit('t1a'), visit('t1b')]);
    expect(progress.tiers[0].complete).toBe(true);
    expect(progress.tiers[1].unlocked).toBe(true);
    expect(progress.currentTier).toBe(2);
  });

  it('ne bloque pas sur un niveau vide', () => {
    const sparse = collection([['t1a', 1], ['t3a', 3]]);
    const progress = computeProgress(sparse, [visit('t1a')]);
    expect(progress.tiers[2].unlocked).toBe(true);
  });

  it('gère une collection vide sans division par zéro', () => {
    const progress = computeProgress(collection([]), []);
    expect(progress.pct).toBe(0);
    expect(progress.complete).toBe(false);
  });

  it('marque la collection complète', () => {
    const progress = computeProgress(sample, ['t1a', 't1b', 't2a', 't2b', 't3a'].map((id) => visit(id)));
    expect(progress.complete).toBe(true);
    expect(progress.pct).toBe(100);
  });
});

describe('le niveau en cours', () => {
  const sample = collection([
    ['t1a', 1], ['t1b', 1],
    ['t2a', 2], ['t2b', 2],
    ['t3a', 3],
  ]);

  it('démarre au niveau 1, à zéro', () => {
    const { stage } = computeProgress(sample, []);
    expect(stage).toMatchObject({ tier: 1, visited: 0, total: 2, remaining: 2, pct: 0 });
  });

  it('mesure le niveau, pas la collection entière', () => {
    // Un lieu sur cinq au total, mais un sur deux au niveau 1 : c'est cette
    // seconde lecture qu'on montre.
    const { stage, pct } = computeProgress(sample, [visit('t1a')]);
    expect(pct).toBe(20);
    expect(stage).toMatchObject({ tier: 1, visited: 1, total: 2, pct: 50 });
  });

  it('passe au niveau suivant une fois le précédent bouclé', () => {
    const { stage } = computeProgress(sample, [visit('t1a'), visit('t1b')]);
    expect(stage).toMatchObject({ tier: 2, visited: 0, total: 2, remaining: 2 });
  });

  it('ignore un niveau vide', () => {
    const sparse = collection([['t1a', 1], ['t3a', 3]]);
    const { stage } = computeProgress(sparse, [visit('t1a')]);
    expect(stage.tier).toBe(3);
  });

  it('reste sur le dernier niveau quand tout est fini', () => {
    const visits = ['t1a', 't1b', 't2a', 't2b', 't3a'].map((id) => visit(id));
    const { stage } = computeProgress(sample, visits);
    expect(stage).toMatchObject({ tier: 3, complete: true, pct: 100, remaining: 0 });
  });

  it('ne divise pas par zéro sur une collection vide', () => {
    expect(computeProgress(collection([]), []).stage).toMatchObject({
      tier: 1, total: 0, pct: 0,
    });
  });
});

describe('badges', () => {
  const sample = collection([
    ['t1a', 1], ['t1b', 1], ['t2a', 2], ['t2b', 2],
  ]);

  it('attribue les paliers de pourcentage franchis', () => {
    const progress = computeProgress(sample, [visit('t1a'), visit('t1b')]);
    const labels = earnedBadges(sample, progress).map((badge) => badge.label);
    expect(labels).toContain('25 %');
    expect(labels).toContain('50 %');
    expect(labels).not.toContain('75 %');
  });

  it('attribue un badge de niveau terminé', () => {
    const progress = computeProgress(sample, [visit('t1a'), visit('t1b')]);
    expect(earnedBadges(sample, progress).map((b) => b.label)).toContain('Niveau 1 terminé');
  });

  it('n’attribue aucun badge à zéro visite', () => {
    expect(earnedBadges(sample, computeProgress(sample, []))).toHaveLength(0);
  });

  it('donne tous les paliers à 100 %', () => {
    const progress = computeProgress(
      sample,
      ['t1a', 't1b', 't2a', 't2b'].map((id) => visit(id)),
    );
    const badges = earnedBadges(sample, progress);
    for (const threshold of BADGE_THRESHOLDS) {
      expect(badges.some((badge) => badge.value === threshold && badge.kind === 'threshold')).toBe(true);
    }
  });
});

describe('récompense de validation', () => {
  const sample = collection([
    ['a', 1], ['b', 1], ['c', 2], ['d', 2],
  ]);
  const other = { ...collection([['x', 1], ['y', 1]]), slug: 'theme-cascades', name: 'Cascades' };
  const target = place({ id: 'b' });

  const run = (before: Visit[]) =>
    describeCheckIn([sample, other], target, before, [...before, makeVisit(target, 'gps')]);

  it('ne retient que les collections où le lieu compte', () => {
    expect(run([]).advances.map((a) => a.collection.slug)).toEqual(['theme-chateaux']);
  });

  it('expose l’avant et l’après pour animer le mouvement', () => {
    const [advance] = run([visit('a')]).advances;
    expect(advance.before.pct).toBe(25);
    expect(advance.after.pct).toBe(50);
  });

  it('signale les badges décrochés par cette validation, pas les précédents', () => {
    const reward = run([visit('a')]);
    const labels = reward.newBadges.map((badge) => badge.label);
    expect(labels).toContain('50 %');
    // Le palier 25 % était déjà acquis avant.
    expect(labels).not.toContain('25 %');
  });

  it('signale un niveau terminé', () => {
    const reward = run([visit('a')]);
    expect(reward.tierUps).toEqual([{ collection: sample, tier: 1 }]);
  });

  it('ne signale aucun niveau quand il en reste', () => {
    expect(run([]).tierUps).toEqual([]);
  });

  it('classe la collection la plus avancée en premier', () => {
    const wide = { ...collection([['b', 1], ['p', 1], ['q', 2], ['r', 3]]), slug: 'geo-country-fr' };
    const reward = describeCheckIn(
      [sample, wide],
      target,
      [visit('a')],
      [visit('a'), makeVisit(target, 'gps')],
    );
    expect(reward.advances[0].collection.slug).toBe('theme-chateaux');
  });
});

describe('prochain objectif', () => {
  const sample = collection([['a', 1], ['b', 1], ['c', 2]]);

  it('vise d’abord le niveau en cours', () => {
    expect(nextMilestone(computeProgress(sample, [visit('a')]))).toEqual({
      label: 'Niveau 1',
      remaining: 1,
    });
  });

  it('ne renvoie rien sur une collection terminée', () => {
    const progress = computeProgress(sample, ['a', 'b', 'c'].map((id) => visit(id)));
    expect(nextMilestone(progress)).toBeNull();
  });
});
