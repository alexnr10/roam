import { places } from '../data/catalog';
import {
  REGIONS,
  anneauDuMonde,
  centreDe,
  contient,
  emprise,
  lieuxDe,
  niveauxDe,
  rangDepuisLeCentre,
  regionAu,
  regionDuDepartement,
  remplitLEcran,
  voile,
} from './regions';

describe('emprise', () => {
  it('encadre un polygone simple', () => {
    expect(
      emprise({
        type: 'Polygon',
        coordinates: [
          [
            [1, 2],
            [5, 2],
            [5, 9],
            [1, 9],
            [1, 2],
          ],
        ],
      }),
    ).toEqual([
      [1, 2],
      [5, 9],
    ]);
  });

  it('encadre TOUTES les parties d’un multipolygone', () => {
    // La Bretagne porte onze polygones : cadrer sur le premier laisserait
    // Ouessant et Belle-Île hors de l'écran.
    const bornes = emprise(REGIONS.get('53')!.geometry);
    expect(bornes[0][0]).toBeLessThan(-4.5);
    expect(bornes[1][0]).toBeGreaterThan(-1.5);
  });
});

describe('contient', () => {
  const carre: GeoJSON.Polygon = {
    type: 'Polygon',
    coordinates: [
      [
        [0, 0],
        [10, 0],
        [10, 10],
        [0, 10],
        [0, 0],
      ],
      [
        [4, 4],
        [6, 4],
        [6, 6],
        [4, 6],
        [4, 4],
      ],
    ],
  };

  it('accepte un point dedans', () => {
    expect(contient(carre, 2, 2)).toBe(true);
  });

  it('refuse un point dehors', () => {
    expect(contient(carre, 12, 2)).toBe(false);
  });

  it('refuse un point dans un trou', () => {
    // Une enclave n'appartient pas à la région qui l'entoure : l'ignorer
    // ouvrirait une région sur un territoire qui n'est pas le sien.
    expect(contient(carre, 5, 5)).toBe(false);
  });
});

describe('regionAu', () => {
  it('reconnaît Paris comme Île-de-France', () => {
    expect(regionAu(2.3488, 48.8534)).toBe('11');
  });

  it('reconnaît Ajaccio comme la Corse', () => {
    expect(regionAu(8.7369, 41.9192)).toBe('94');
  });

  it('ne trouve rien au milieu de l’Atlantique', () => {
    expect(regionAu(-30, 45)).toBeNull();
  });
});

describe('voile', () => {
  const percé = voile();

  it('a le monde pour anneau extérieur', () => {
    expect(percé.geometry.coordinates[0]).toEqual(anneauDuMonde());
  });

  it('perce un trou par polygone de région, outre-mer compris', () => {
    // Dix-huit régions, mais cinquante-trois polygones : les îles comptent.
    // C'est ce percement qui fait apparaître Mayotte quand on dérive vers
    // l'océan Indien, sans qu'aucun encart n'ait à l'annoncer.
    expect(percé.geometry.coordinates.length).toBeGreaterThan(REGIONS.size);
  });
});

describe('niveauxDe', () => {
  it('classe l’Occitanie par sa collection régionale', () => {
    const niveaux = niveauxDe('76');
    const lieux = lieuxDe('76');
    const premiers = lieux.filter((place) => niveaux.get(place.id) === 1).length;
    // Une dizaine d'incontournables sur deux cent soixante-douze. Prendre le
    // meilleur niveau toutes collections confondues en donnerait quatre-vingt-
    // seize, c'est-à-dire aucun.
    expect(premiers).toBeGreaterThan(5);
    expect(premiers).toBeLessThan(20);
  });

  it('classe Mayotte malgré l’absence de collection régionale', () => {
    const niveaux = niveauxDe('06');
    const lieux = lieuxDe('06');
    expect(lieux.length).toBeGreaterThan(0);
    expect(lieux.some((place) => niveaux.has(place.id))).toBe(true);
  });

  it('donne un niveau à au moins un lieu de CHAQUE région', () => {
    for (const code of REGIONS.keys()) {
      const lieux = lieuxDe(code);
      if (lieux.length === 0) continue;
      const niveaux = niveauxDe(code);
      expect(lieux.some((place) => niveaux.has(place.id))).toBe(true);
    }
  });
});

describe('regionDuDepartement', () => {
  it('rattache le Gard à l’Occitanie', () => {
    expect(regionDuDepartement('30')).toBe('76');
  });

  it('rattache Mayotte à sa région', () => {
    expect(regionDuDepartement('976')).toBe('06');
  });
});

describe('rangDepuisLeCentre', () => {
  it('numérote du plus proche au plus lointain', () => {
    const rangs = rangDepuisLeCentre(
      [
        { lat: 0, lon: 10 },
        { lat: 0, lon: 1 },
        { lat: 0, lon: 5 },
      ],
      [0, 0],
    );
    expect(rangs).toEqual([2, 0, 1]);
  });
});

describe('centreDe', () => {
  it('prend le milieu de l’emprise', () => {
    expect(
      centreDe([
        [0, 0],
        [10, 20],
      ]),
    ).toEqual([5, 10]);
  });
});

describe('rattachement des lieux', () => {
  it('donne une région à tous les lieux sauf une poignée', () => {
    const sans = places.filter((place) => !place.regionCode);
    expect(sans.length).toBe(0);
  });
});

describe('remplitLEcran', () => {
  const vue: [[number, number], [number, number]] = [
    [0, 0],
    [10, 10],
  ];

  it('ouvre une région qui occupe la moitié du cadre', () => {
    expect(
      remplitLEcran(
        [
          [2, 2],
          [8, 4],
        ],
        vue,
      ),
    ).toBe(true);
  });

  it('laisse fermée une région perdue dans le cadre', () => {
    expect(
      remplitLEcran(
        [
          [4, 4],
          [6, 6],
        ],
        vue,
      ),
    ).toBe(false);
  });

  it('ouvre l’Occitanie une fois cadrée, ce qu’un palier de zoom ratait', () => {
    // Cadrée sur un téléphone, l'Occitanie atterrit vers le zoom 6,6 — sous le
    // palier de 7,2 du livrable. C'est la place qu'elle prend à l'écran qui
    // décide, pas le zoom, sans quoi les grandes régions ne s'ouvraient jamais.
    const occitanie = emprise(REGIONS.get('76')!.geometry);
    const large: [[number, number], [number, number]] = [
      [occitanie[0][0] - 0.4, occitanie[0][1] - 0.4],
      [occitanie[1][0] + 0.4, occitanie[1][1] + 0.4],
    ];
    expect(remplitLEcran(occitanie, large)).toBe(true);
  });
});
