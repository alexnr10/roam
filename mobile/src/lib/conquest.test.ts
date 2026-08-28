import {
  PLAYABLE_MIN,
  buildUnits,
  conquestByZone,
  shadeOf,
  unitState,
  zoneCodeOf,
} from './conquest';
import type { Area, Place, Visit } from '../types';

const place = (over: Partial<Place> & { id: string }): Place => ({
  slug: over.id.toLowerCase(),
  name: over.id,
  themeId: 'chateaux',
  lat: 45,
  lon: 2,
  radiusM: 150,
  score: 100,
  departement: 'Cantal',
  departementCode: '15',
  regionCode: '84',
  communeCode: '15014',
  communeName: 'Aurillac',
  ...over,
});

const visit = (placeId: string): Visit => ({
  placeId,
  method: 'gps',
  verified: true,
  visitedAt: '2026-01-01T00:00:00.000Z',
});

const cantal: Area = { code: '15', name: 'Cantal', deForm: 'du Cantal' };

/** Trois châteaux et deux musées dans le Cantal, scores décroissants. */
const catalogue = (): Place[] => [
  place({ id: 'C1', score: 100 }),
  place({ id: 'C2', score: 90 }),
  place({ id: 'C3', score: 80 }),
  place({ id: 'M1', themeId: 'musees', score: 70 }),
  place({ id: 'M2', themeId: 'musees', score: 60 }),
];

describe('découpage en unités de conquête', () => {
  it('produit une unité par thème et une unité tous thèmes confondus', () => {
    const units = buildUnits(catalogue(), 'departement');
    const themes = units.filter((unit) => unit.themeId !== null).map((u) => u.themeId);
    const overall = units.filter((unit) => unit.themeId === null);

    expect(themes.sort()).toEqual(['chateaux', 'musees']);
    expect(overall).toHaveLength(1);
    expect(overall[0].placeIds).toHaveLength(5);
  });

  it('classe les lieux du meilleur au moins bon dans le territoire', () => {
    const units = buildUnits(catalogue(), 'departement');
    const chateaux = units.find((unit) => unit.themeId === 'chateaux')!;
    expect(chateaux.placeIds).toEqual(['C1', 'C2', 'C3']);
  });

  it('donne à un lieu un niveau propre au territoire regardé', () => {
    // Le même château est le meilleur du Cantal et le quatrième de France :
    // c'est le niveau LOCAL qui colore, sinon la carte n'aurait aucun sens à
    // l'échelle départementale.
    const places = [
      ...catalogue(),
      place({ id: 'X1', departementCode: '27', communeCode: '27285', score: 200 }),
      place({ id: 'X2', departementCode: '27', communeCode: '27285', score: 190 }),
      place({ id: 'X3', departementCode: '27', communeCode: '27285', score: 180 }),
    ];
    const cantalUnit = buildUnits(places, 'departement').find(
      (unit) => unit.code === '15' && unit.themeId === 'chateaux',
    )!;
    const franceUnit = buildUnits(places, 'country').find(
      (unit) => unit.themeId === 'chateaux',
    )!;

    expect(cantalUnit.tiers[cantalUnit.placeIds.indexOf('C1')]).toBe(1);
    expect(franceUnit.tiers[franceUnit.placeIds.indexOf('C1')]).toBe(2);
  });

  it('déclare non jouable un thème sous le seuil, mais jamais le territoire entier', () => {
    // Un département avec un seul château se colorerait en une visite.
    const maigre = [place({ id: 'C1' }), place({ id: 'M1', themeId: 'musees' })];
    const units = buildUnits(maigre, 'departement');

    expect(units.find((u) => u.themeId === 'chateaux')!.playable).toBe(false);
    // L'unité « tous thèmes » échappe au seuil : une commune d'un seul lieu se
    // conquiert en une visite, et c'est l'effet voulu.
    expect(units.find((u) => u.themeId === null)!.playable).toBe(true);
    expect(PLAYABLE_MIN).toBeGreaterThan(1);
  });

  it('ignore un lieu dont le code de territoire manque', () => {
    // Un phare en mer n'a pas de commune : il ne doit pas créer une zone vide.
    const enMer = place({ id: 'P1', communeCode: null });
    expect(buildUnits([enMer], 'commune')).toHaveLength(0);
    expect(buildUnits([enMer], 'departement')).toHaveLength(2);
  });

  it('rattache tout lieu retenu au pays', () => {
    expect(zoneCodeOf(place({ id: 'C1' }), 'country')).toBe('FR');
  });

  it("sépare deux thèmes dont l'identifiant contient une espace", () => {
    // Le regroupement passe par une clé composite : elle ne doit pas se
    // désassembler au premier espace du nom de thème.
    const units = buildUnits(
      [place({ id: 'A', themeId: 'maisons d artistes' })],
      'departement',
    );
    const themed = units.find((unit) => unit.themeId !== null)!;
    expect(themed.code).toBe('15');
    expect(themed.themeId).toBe('maisons d artistes');
  });
});

describe('niveau atteint sur une unité', () => {
  const unit = () =>
    buildUnits(
      [
        place({ id: 'A', score: 100 }),
        place({ id: 'B', score: 90 }),
        place({ id: 'C', score: 80 }),
        place({ id: 'D', score: 70 }),
      ],
      'departement',
    ).find((u) => u.themeId === 'chateaux')!;

  it('ne donne aucun niveau tant que le premier palier est incomplet', () => {
    const state = unitState(unit(), new Set(['A', 'B']));
    expect(state.tier).toBe(0);
    expect(state.visited).toBe(2);
  });

  it('donne le niveau 1 quand les trois meilleurs sont validés', () => {
    const state = unitState(unit(), new Set(['A', 'B', 'C']));
    expect(state.tier).toBe(1);
    expect(state.complete).toBe(false);
  });

  it('donne le niveau supérieur quand tout est validé', () => {
    const state = unitState(unit(), new Set(['A', 'B', 'C', 'D']));
    expect(state.tier).toBe(2);
    expect(state.complete).toBe(true);
    expect(state.pct).toBe(100);
  });

  it('plafonne le niveau à la profondeur du territoire', () => {
    // Trois châteaux dans le département : les faire tous, c'est le niveau 1
    // et la collection complète — pas le niveau 3. Sinon un territoire pauvre
    // vaudrait autant qu'un département de quatre-vingts châteaux.
    const petit = buildUnits(
      [
        place({ id: 'A', score: 100 }),
        place({ id: 'B', score: 90 }),
        place({ id: 'C', score: 80 }),
      ],
      'departement',
    ).find((u) => u.themeId === 'chateaux')!;

    const state = unitState(petit, new Set(['A', 'B', 'C']));
    expect(state.tier).toBe(1);
    expect(state.complete).toBe(true);
  });

  it('exige les niveaux inférieurs : ils sont cumulatifs', () => {
    // D est de niveau 2 ; le valider sans les trois premiers ne donne rien.
    const state = unitState(unit(), new Set(['D']));
    expect(state.tier).toBe(0);
  });
});

describe('conquête par territoire', () => {
  it('distingue « une collection finie » de « tout le territoire fini »', () => {
    const places = catalogue();
    const visits = ['C1', 'C2', 'C3'].map(visit);
    const [zone] = conquestByZone(places, [cantal], 'departement', visits);

    // Les trois châteaux du Cantal : la collection est finie, pas le territoire.
    expect(zone.anyThemeComplete).toBe(true);
    expect(zone.allComplete).toBe(false);
    expect(shadeOf(zone).kind).toBe('theme');

    const tout = conquestByZone(places, [cantal], 'departement', [
      ...visits,
      ...['M1', 'M2'].map(visit),
    ]);
    expect(tout[0].allComplete).toBe(true);
    expect(shadeOf(tout[0]).kind).toBe('total');
  });

  it('ne compte pas un thème non jouable dans « une collection finie »', () => {
    // Deux musées seulement : les finir ne doit pas colorer le département,
    // sinon le seuil de jouabilité ne servirait à rien.
    const places = catalogue();
    const zones = conquestByZone(places, [cantal], 'departement', ['M1', 'M2'].map(visit));
    expect(zones[0].anyThemeComplete).toBe(false);
    expect(zones[0].themes.map((entry) => entry.themeId)).toEqual(['chateaux']);
    expect(shadeOf(zones[0]).kind).toBe('started');
  });

  it('rend un territoire vierge sans le colorer', () => {
    const zones = conquestByZone(catalogue(), [cantal], 'departement', []);
    expect(zones[0].overall.visited).toBe(0);
    expect(shadeOf(zones[0])).toEqual({ kind: 'empty' });
  });

  it('ignore un territoire absent du répertoire', () => {
    // Sans nom, une zone ne peut ni s'afficher ni se dessiner.
    expect(conquestByZone(catalogue(), [], 'departement', [])).toHaveLength(0);
  });

  it('classe les territoires les plus avancés en premier', () => {
    const eure: Area = { code: '27', name: 'Eure', deForm: "de l'Eure" };
    const places = [
      ...catalogue(),
      place({ id: 'E1', departementCode: '27', score: 50 }),
      place({ id: 'E2', departementCode: '27', score: 40 }),
    ];
    const zones = conquestByZone(places, [cantal, eure], 'departement', [visit('C1')]);
    expect(zones.map((zone) => zone.area.code)).toEqual(['15', '27']);
  });
});

describe('conquête filtrée par thème', () => {
  const eure: Area = { code: '27', name: 'Eure', deForm: "de l'Eure" };

  /** Trois châteaux dans le Cantal, un seul dans l'Eure, deux musées. */
  const catalogue = (): Place[] => [
    place({ id: 'C1', score: 100 }),
    place({ id: 'C2', score: 90 }),
    place({ id: 'C3', score: 80 }),
    place({ id: 'M1', themeId: 'musees', score: 70 }),
    place({ id: 'M2', themeId: 'musees', score: 60 }),
    place({ id: 'E1', departementCode: '27', communeCode: '27285', score: 50 }),
  ];

  it('colore le territoire quand le thème filtré y est fini', () => {
    // « J'ai fini les châteaux du Cantal » est une conquête en soi, même s'il
    // reste des musées à y faire.
    const visits = ['C1', 'C2', 'C3'].map(visit);
    const [zone] = conquestByZone(catalogue(), [cantal], 'departement', visits, 'chateaux');
    expect(zone.allComplete).toBe(true);
    expect(shadeOf(zone).kind).toBe('total');

    // Sans filtre, le même état ne donne que « une collection finie ».
    const [sans] = conquestByZone(catalogue(), [cantal], 'departement', visits);
    expect(sans.allComplete).toBe(false);
    expect(shadeOf(sans).kind).toBe('theme');
  });

  it('ignore les lieux des autres thèmes', () => {
    const zones = conquestByZone(catalogue(), [cantal], 'departement', [], 'chateaux');
    expect(zones[0].overall.total).toBe(3);
  });

  it('laisse neutre un territoire trop pauvre dans le thème', () => {
    // Un seul château dans l'Eure : le colorier en une visite ne
    // récompenserait rien, et c'est tout l'objet du seuil de jouabilité.
    const zones = conquestByZone(catalogue(), [eure], 'departement', [visit('E1')], 'chateaux');
    expect(zones[0].playable).toBe(false);
    expect(zones[0].overall.complete).toBe(true);
    expect(shadeOf(zones[0])).toEqual({ kind: 'empty' });
  });

  it("n'impose pas ce seuil quand aucun filtre n'est posé", () => {
    // La carte générale se remplit vite : une commune d'un seul lieu se
    // conquiert en une visite, et c'est l'effet voulu.
    const zones = conquestByZone(catalogue(), [eure], 'departement', [visit('E1')]);
    expect(zones[0].playable).toBe(true);
    expect(shadeOf(zones[0]).kind).toBe('total');
  });
});
