import { places } from '../data/catalog';
import {
  PAYS_ENTIER,
  REGIONS,
  anneauDuMonde,
  bornesDuPays,
  centreDe,
  cheminSvg,
  cheminSvgDans,
  contient,
  dUnSeulTenant,
  dansLaRegion,
  empriseDeLaRegion,
  regionConnue,
  emprise,
  lieuxDe,
  nomDeRegion,
  prochaineOuverture,
  rangDepuisLeCentre,
  regionAu,
  regionDuCadre,
  regionDuDepartement,
  regionLaMieuxRepresentee,
  remplitLEcran,
  voile,
} from './regions';
import type { Emprise } from './regions';
import { chargerContours } from '../data/outlines';
import { chargerCatalogue } from '../data/catalog';

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

describe('bornesDuPays', () => {
  it('cadre la métropole, pas le globe', () => {
    // L'union BRUTE des contours français va de la Guadeloupe (-61,8) à La
    // Réunion (55,8) : une vue de départ montrant un hémisphère pour quelques
    // lieux à l'autre bout du monde n'est pas une vue de départ. Le premier
    // jet faisait exactement ça — mesuré, pas supposé.
    const bornes = bornesDuPays();
    expect(bornes).not.toBeNull();
    const [[ouest, sud], [est, nord]] = bornes!;
    expect(ouest).toBeGreaterThan(-10);
    expect(est).toBeLessThan(12);
    expect(sud).toBeGreaterThan(40);
    expect(nord).toBeLessThan(52);
  });

  it("contient Brest, Menton et la pointe corse", () => {
    const [[ouest, sud], [est, nord]] = bornesDuPays()!;
    for (const [lon, lat] of [[-4.486, 48.39], [7.503, 43.775], [9.36, 41.39]]) {
      expect(lon).toBeGreaterThanOrEqual(ouest);
      expect(lon).toBeLessThanOrEqual(est);
      expect(lat).toBeGreaterThanOrEqual(sud);
      expect(lat).toBeLessThanOrEqual(nord);
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

describe('la projection du croquis', () => {
  it('donne à la France la proportion de la carte, pas celle des degrés bruts', () => {
    // Porter les latitudes telles quelles aplatit le dessin : à la hauteur de
    // la France, un degré de longitude ne vaut que 0,69 degré de latitude sur
    // le terrain. Le croquis y perdait un tiers de sa hauteur et ne
    // ressemblait plus à la carte qu'il ouvre.
    const metropole = [...REGIONS.keys()].filter((code) => code.length === 2 && code >= '11');
    const bornes = metropole.reduce(
      (acc, code) => {
        const b = emprise(REGIONS.get(code)!.geometry);
        return [
          [Math.min(acc[0][0], b[0][0]), Math.min(acc[0][1], b[0][1])],
          [Math.max(acc[1][0], b[1][0]), Math.max(acc[1][1], b[1][1])],
        ] as [[number, number], [number, number]];
      },
      [
        [180, 90],
        [-180, -90],
      ] as [[number, number], [number, number]],
    );
    const chemin = cheminSvgDans(REGIONS.get('11')!.geometry, bornes, 100);
    const points = chemin
      .match(/-?\d+(\.\d+)?\s-?\d+(\.\d+)?/g)!
      .map((p) => p.split(' ').map(Number));
    const xs = points.map((p) => p[0]);
    const ys = points.map((p) => p[1]);
    // L'Île-de-France est un peu plus large que haute, mais de peu : à plat,
    // elle paraissait deux fois plus large.
    const rapport = (Math.max(...ys) - Math.min(...ys)) / (Math.max(...xs) - Math.min(...xs));
    expect(rapport).toBeGreaterThan(0.75);
    expect(rapport).toBeLessThan(1.3);
  });
});

describe('regionDuCadre, quand le centre n’est sur aucune région', () => {
  // Deux régions voisines, et entre elles un TROU — Saint-Marin, qui n'est
  // dans aucune région italienne parce que c'est un autre pays. Le repli sur
  // la plus petite emprise y choisissait la mauvaise : celle dont le rectangle
  // est le plus petit, sans regarder ce qu'il y a dessous.
  const carre = (x: number, y: number, c: number): number[][] => [
    [x, y], [x + c, y], [x + c, y + c], [x, y + c], [x, y],
  ];
  const contours = {
    attribution: '',
    region: {
      type: 'FeatureCollection',
      features: [
        // « Grande » : un carré de dix, au nord du trou.
        { type: 'Feature', properties: { code: 'G', nom: 'Grande' },
          geometry: { type: 'Polygon', coordinates: [carre(0, 2, 10)] } },
        // « Petite » : un carré de trois, au sud du trou. Emprise plus petite.
        { type: 'Feature', properties: { code: 'P', nom: 'Petite' },
          geometry: { type: 'Polygon', coordinates: [carre(3, -4, 3)] } },
      ],
    },
  };

  it('ouvre la région des LIEUX qu’on regarde, pas celle au plus petit cadre', () => {
    chargerContours(contours as never);
    chargerCatalogue({
      places: [
        // Trois lieux dans le trou, rattachés à la GRANDE région.
        { id: 'a', name: 'a', lat: 0.5, lon: 4.5, regionCode: 'G' },
        { id: 'b', name: 'b', lat: 0.6, lon: 4.6, regionCode: 'G' },
        { id: 'c', name: 'c', lat: 0.4, lon: 4.4, regionCode: 'G' },
        // Un seul rattaché à la petite, et plus loin.
        { id: 'd', name: 'd', lat: -3.5, lon: 4.5, regionCode: 'P' },
      ],
      collections: [], themes: [], areas: { region: [], departement: [], commune: [], country: [] },
    } as never);
    // Un cadre centré dans le trou, sur les trois lieux.
    const cadre: Emprise = [[4.0, 0.0], [5.0, 1.0]];
    expect(regionAu(4.5, 0.5)).toBeNull();
    expect(regionLaMieuxRepresentee(cadre)).toBe('G');
    expect(regionDuCadre(cadre)).toBe('G');
  });

  it('ne dit rien quand le cadre ne montre aucun lieu', () => {
    chargerContours(contours as never);
    chargerCatalogue({
      places: [], collections: [], themes: [],
      areas: { region: [], departement: [], commune: [], country: [] },
    } as never);
    expect(regionLaMieuxRepresentee([[4.0, 0.0], [5.0, 1.0]])).toBeNull();
  });
});


/**
 * Un pays sans contour de région — le Vatican, Saint-Marin.
 *
 * La mécanique d'ouverture est faite pour la France : dix-huit aplats qu'on
 * ouvre un par un, et les pastilles n'apparaissent que DANS celui qui est
 * ouvert. Appliquée telle quelle à un État de quarante-quatre hectares, elle
 * rendait une carte vide — mesuré sur `catalogues/va.json` : dix-neuf lieux,
 * zéro contour, zéro lieu ouvrable, et un voile sans trou par-dessus.
 */
describe('un pays d’un seul tenant', () => {
  const sansContour = { attribution: '', region: { type: 'FeatureCollection', features: [] } };
  const vatican = {
    places: [
      { id: 'Q12512', name: 'Basilique Saint-Pierre', lat: 41.9022, lon: 12.4534, regionCode: null },
      { id: 'Q2943', name: 'Chapelle Sixtine', lat: 41.9030, lon: 12.4544, regionCode: null },
    ],
    collections: [],
    themes: [],
    areas: { region: [], departement: [], commune: [], country: [{ code: 'VA', name: 'Vatican' }] },
  };

  beforeEach(() => {
    chargerContours(sansContour as never);
    chargerCatalogue(vatican as never);
  });

  it('se reconnaît à l’absence de contour', () => {
    expect(REGIONS.size).toBe(0);
    expect(dUnSeulTenant()).toBe(true);
  });

  it('est ouvert partout : la carte ne peut pas rester vide', () => {
    expect(regionAu(12.4534, 41.9022)).toBe(PAYS_ENTIER);
    expect(regionDuCadre([[12.44, 41.89], [12.46, 41.91]])).toBe(PAYS_ENTIER);
  });

  it('rend TOUT le catalogue à la région ouverte', () => {
    expect(lieuxDe(PAYS_ENTIER)).toHaveLength(2);
    // Les lieux n'ont aucun code de région : c'est le test qui échouait avant.
    expect(places.every((lieu) => !lieu.regionCode)).toBe(true);
    expect(places.every((lieu) => dansLaRegion(lieu, PAYS_ENTIER))).toBe(true);
  });

  it('porte le nom du pays, pas le code interne', () => {
    expect(nomDeRegion(PAYS_ENTIER)).toBe('Vatican');
  });

  it('a une emprise à cadrer : sans elle, le premier retour ne faisait rien', () => {
    // Les deux cartes cadrent par `REGIONS.get(code)`, qui ne répond rien pour
    // le pays entier : au Vatican, la pastille de retour désélectionnait le
    // lieu SANS reculer la caméra, et il fallait l'actionner deux fois.
    expect(empriseDeLaRegion(PAYS_ENTIER)).toEqual(bornesDuPays());
    expect(empriseDeLaRegion(PAYS_ENTIER)).not.toBeNull();
    expect(empriseDeLaRegion('12')).toBeNull();
    expect(empriseDeLaRegion(null)).toBeNull();
  });

  it('est une région CONNUE : sinon la carte la referme aussitôt ouverte', () => {
    // Le garde-fou « cette région n'existe pas dans ce pays » est écrit sur
    // `REGIONS.has`, qui dit non au pays entier. La carte ouvrait donc le
    // Vatican au `moveend` et le refermait dans la foulée : les pastilles
    // apparaissaient puis disparaissaient, et un vol atterrissait sur du vide.
    expect(REGIONS.has(PAYS_ENTIER)).toBe(false);
    expect(regionConnue(PAYS_ENTIER)).toBe(true);
    expect(regionConnue(null)).toBe(false);
    expect(regionConnue('12')).toBe(false);
  });

  it('perce le voile de son emprise, au lieu de se couvrir lui-même', () => {
    const anneaux = voile().geometry.coordinates;
    expect(anneaux).toHaveLength(2);
    const [[ouest, sud]] = [anneaux[1][0]];
    expect(ouest).toBeCloseTo(12.4534, 3);
    expect(sud).toBeCloseTo(41.9022, 3);
  });
});

describe('un pays QUI a des régions n’est pas touché', () => {
  it('ne rend pas le code de pays hors de tout contour', () => {
    chargerContours({
      attribution: '',
      region: {
        type: 'FeatureCollection',
        features: [
          { type: 'Feature', properties: { code: 'G', nom: 'Grande' },
            geometry: { type: 'Polygon', coordinates: [[[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]] } },
        ],
      },
    } as never);
    chargerCatalogue({
      places: [], collections: [], themes: [],
      areas: { region: [], departement: [], commune: [], country: [] },
    } as never);
    expect(dUnSeulTenant()).toBe(false);
    expect(regionAu(5, 5)).toBe('G');
    expect(regionAu(50, 50)).toBeNull();
    // Et le pays entier n'y est PAS une région ouvrable : le garde-fou qui
    // referme une région absente doit continuer de le faire.
    expect(regionConnue('G')).toBe(true);
    expect(regionConnue(PAYS_ENTIER)).toBe(false);
  });
});
