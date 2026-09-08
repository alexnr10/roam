import { places } from '../data/catalog';
import {
  REGIONS,
  anneauDuMonde,
  centreDe,
  cheminSvg,
  contient,
  emprise,
  lieuxDe,
  niveauxDe,
  prochaineOuverture,
  rangDepuisLeCentre,
  regionAu,
  regionDuCadre,
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

describe('regionDuCadre', () => {
  /** Le cadre qu'on obtient en cadrant une région, marge comprise. */
  const cadrer = (code: string, marge = 0.06): [[number, number], [number, number]] => {
    const bornes = emprise(REGIONS.get(code)!.geometry);
    const dx = (bornes[1][0] - bornes[0][0]) * marge;
    const dy = (bornes[1][1] - bornes[0][1]) * marge;
    return [
      [bornes[0][0] - dx, bornes[0][1] - dy],
      [bornes[1][0] + dx, bornes[1][1] + dy],
    ];
  };

  it('ouvre CHAQUE région une fois cadrée sur elle', () => {
    // Le vrai défaut n'était pas d'ouvrir la mauvaise région, mais de la
    // refermer aussitôt : les lieux apparaissaient puis disparaissaient.
    for (const code of REGIONS.keys()) {
      expect([code, regionDuCadre(cadrer(code))]).toEqual([code, code]);
    }
  });

  it('ouvre la Guadeloupe, dont le centre du cadre tombe en pleine mer', () => {
    // Un archipel n'a pas de terre en son milieu : de Marie-Galante aux
    // Saintes, le point central est de l'eau. Le test point-dans-polygone seul
    // ne trouvait rien, et la région se refermait sur place.
    const cadre = cadrer('01');
    const [lon, lat] = centreDe(cadre);
    expect(regionAu(lon, lat)).toBeNull();
    expect(regionDuCadre(cadre)).toBe('01');
  });

  it('ne trouve rien sur une vue de la France entière', () => {
    // Aucune région ne remplit l'écran : on regarde le pays, pas un endroit.
    expect(
      regionDuCadre([
        [-5.2, 41.3],
        [9.6, 51.2],
      ]),
    ).toBeNull();
  });
});

describe('prochaineOuverture', () => {
  it('ouvre ce que la caméra montre quand rien n’est ouvert', () => {
    expect(prochaineOuverture({ region: null, ancre: null }, '75', 5.6)).toEqual({
      region: '75',
      ancre: 5.6,
    });
  });

  it('ne défait JAMAIS le clic qui vient d’atterrir', () => {
    // C'est tout le défaut : le vol se termine, la règle géométrique est
    // réévaluée, et elle referme la région que l'utilisateur vient d'ouvrir.
    // Les lieux apparaissaient puis disparaissaient — il fallait zoomer pour
    // les faire revenir.
    expect(prochaineOuverture({ region: '75', ancre: null }, null, 5.57)).toEqual({
      region: '75',
      ancre: 5.57,
    });
  });

  it('ne referme pas sans dézoom, quoi que dise la géométrie', () => {
    // Une région tout juste cadrée peut ne pas « remplir l'écran » d'un
    // cheveu. Tant que la caméra n'a pas reculé, ce n'est pas au calcul de
    // décider.
    expect(prochaineOuverture({ region: '75', ancre: 5.57 }, null, 5.57).region).toBe('75');
  });

  it('referme dès que le dézoom sort la région du cadre', () => {
    expect(prochaineOuverture({ region: '75', ancre: 5.6 }, null, 5.1)).toEqual({
      region: null,
      ancre: null,
    });
  });

  it('passe à la voisine quand c’est elle qui remplit l’écran', () => {
    expect(prochaineOuverture({ region: '75', ancre: 6 }, '76', 6.4)).toEqual({
      region: '76',
      ancre: 6.4,
    });
  });

  it('retient le plus haut zoom atteint', () => {
    // Zoomer sur un village puis ressortir au cadrage d'arrivée n'est pas un
    // dézoom : sans cette mémoire, la région se refermerait au retour.
    const apresZoom = prochaineOuverture({ region: '75', ancre: 5.6 }, '75', 11);
    expect(apresZoom.ancre).toBe(11);
    expect(prochaineOuverture(apresZoom, '75', 5.7).region).toBe('75');
  });

  it('reste ouverte en dérivant vers la mer, sans dézoom', () => {
    expect(prochaineOuverture({ region: '75', ancre: 6 }, null, 6).region).toBe('75');
  });
});

describe('cheminSvg', () => {
  it('tient dans la boîte demandée', () => {
    const chemin = cheminSvg(REGIONS.get('53')!.geometry, 30);
    const nombres = chemin.match(/-?\d+(\.\d+)?/g)!.map(Number);
    expect(Math.min(...nombres)).toBeGreaterThanOrEqual(0);
    expect(Math.max(...nombres)).toBeLessThanOrEqual(30.01);
  });

  it('ne déforme pas la silhouette', () => {
    // Une région étirée pour remplir le carré ne se reconnaîtrait plus : le
    // facteur d'échelle est commun aux deux axes, donc le plus grand côté du
    // tracé touche la boîte et l'autre non.
    const chemin = cheminSvg(REGIONS.get('94')!.geometry, 30);
    const points = chemin.match(/-?\d+(\.\d+)?\s-?\d+(\.\d+)?/g)!.map((p) => p.split(' ').map(Number));
    const largeur = Math.max(...points.map((p) => p[0])) - Math.min(...points.map((p) => p[0]));
    const hauteur = Math.max(...points.map((p) => p[1])) - Math.min(...points.map((p) => p[1]));
    // La Corse est bien plus haute que large : c'est la hauteur qui remplit.
    expect(hauteur).toBeCloseTo(30, 1);
    expect(largeur).toBeLessThan(24);
  });

  it('dessine CHAQUE région, outre-mer compris', () => {
    for (const code of REGIONS.keys()) {
      expect([code, cheminSvg(REGIONS.get(code)!.geometry, 30).startsWith('M')]).toEqual([
        code,
        true,
      ]);
    }
  });

  it('n’oublie aucune île', () => {
    // Onze polygones pour la Bretagne : autant de sous-tracés, sinon Belle-Île
    // et Ouessant disparaissent de la silhouette.
    const chemin = cheminSvg(REGIONS.get('53')!.geometry, 30);
    expect((chemin.match(/M/g) ?? []).length).toBeGreaterThan(10);
  });
});
