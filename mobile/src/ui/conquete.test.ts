import { validateStyleMin } from '@maplibre/maplibre-gl-style-spec';

import { conquest } from '../theme';
import {
  DONE_OPACITY,
  EMPTY_OPACITY,
  STARTED_MAX_OPACITY,
  couleurDe,
  couleurDesTerritoires,
  couleurDesTerritoiresNative,
  opaciteDe,
  opaciteDesTerritoires,
  opaciteDesTerritoiresNative,
  type Peint,
} from './conquete';

const PEINTS: Peint[] = [
  { code: '75', shade: 'total', pct: 100 },
  { code: '2A', shade: 'theme', pct: 60 },
  { code: '29', shade: 'started', pct: 50 },
  { code: '15', shade: 'empty', pct: 0 },
];

/** Un style minimal portant les couches de conquête, pour le validateur. */
function styleAvec(couleur: unknown, opacite: unknown) {
  return {
    version: 8 as const,
    sources: {
      territoires: {
        type: 'geojson' as const,
        data: { type: 'FeatureCollection' as const, features: [] },
      },
    },
    layers: [
      {
        id: 'territoire',
        type: 'fill' as const,
        source: 'territoires',
        paint: { 'fill-color': couleur, 'fill-opacity': opacite },
      },
    ],
  };
}

describe('les couleurs de la conquête', () => {
  it('donne au territoire entamé la couleur du total, pâlie', () => {
    // Une quatrième couleur pour « entamé » ferait un nuancier ; c'est
    // l'opacité qui dit la progression, pas la teinte.
    expect(couleurDe('started')).toBe(conquest.total);
    expect(couleurDe('total')).toBe(conquest.total);
    expect(couleurDe('theme')).toBe(conquest.theme);
    expect(couleurDe('empty')).toBe(conquest.empty);
  });

  it('fait pâlir un territoire entamé à proportion de ce qu’il reste', () => {
    // Sans ce dégradé la carte serait binaire : aucune progression visible
    // entre le premier lieu validé et le dernier.
    const rien = opaciteDe('started', 0);
    const moitie = opaciteDe('started', 50);
    const presque = opaciteDe('started', 100);
    expect(rien).toBeLessThan(moitie);
    expect(moitie).toBeLessThan(presque);
    expect(presque).toBeCloseTo(STARTED_MAX_OPACITY, 10);
    // Un lieu validé doit se voir : le plancher n'est jamais zéro.
    expect(rien).toBeGreaterThan(0);
  });

  it('borne un pourcentage aberrant', () => {
    expect(opaciteDe('started', -10)).toBe(opaciteDe('started', 0));
    expect(opaciteDe('started', 300)).toBe(opaciteDe('started', 100));
  });

  it('garde le vierge en retrait et l’achevé en avant', () => {
    expect(opaciteDe('empty', 0)).toBe(EMPTY_OPACITY);
    expect(opaciteDe('total', 100)).toBe(DONE_OPACITY);
    expect(opaciteDe('theme', 60)).toBe(DONE_OPACITY);
    expect(EMPTY_OPACITY).toBeLessThan(DONE_OPACITY);
  });
});

describe('les expressions natives', () => {
  // `feature-state` n'existe que dans la version web de MapLibre : la nuance
  // se lit alors dans une table indexée par le code du territoire.

  it('ne mentionne jamais `feature-state`', () => {
    expect(JSON.stringify(couleurDesTerritoiresNative(PEINTS))).not.toContain('feature-state');
    expect(JSON.stringify(opaciteDesTerritoiresNative(PEINTS))).not.toContain('feature-state');
  });

  it('donne une entrée par territoire, et un défaut', () => {
    const table = couleurDesTerritoiresNative(PEINTS) as unknown[];
    expect(table[0]).toBe('match');
    expect(table[1]).toEqual(['get', 'code']);
    // deux éléments de tête, une paire par territoire, un défaut à la fin.
    expect(table).toHaveLength(2 + PEINTS.length * 2 + 1);
    expect(table[table.length - 1]).toBe(conquest.empty);
  });

  it('peint chaque territoire de la couleur de sa nuance', () => {
    const table = couleurDesTerritoiresNative(PEINTS) as unknown[];
    for (const { code, shade } of PEINTS) {
      const rang = table.indexOf(code);
      expect(rang).toBeGreaterThan(1);
      expect(table[rang + 1]).toBe(couleurDe(shade));
    }
  });

  it('rend une valeur SIMPLE quand rien n’est peint', () => {
    // Un `match` sans une seule paire est refusé par le format de style — et
    // refusé en silence, comme toujours : la couche manquerait sans un mot.
    expect(couleurDesTerritoiresNative([])).toBe(conquest.empty);
    expect(opaciteDesTerritoiresNative([])).toBe(EMPTY_OPACITY);
  });

  it('dit la même chose que la version web, nuance par nuance', () => {
    // Les deux plateformes doivent colorier la France pareil. Ce qui diffère
    // est d'où vient la nuance, jamais ce qu'on en fait.
    const opacites = opaciteDesTerritoiresNative(PEINTS) as unknown[];
    for (const { code, shade, pct } of PEINTS) {
      const rang = opacites.indexOf(code);
      expect(opacites[rang + 1]).toBeCloseTo(opaciteDe(shade, pct), 10);
    }
  });
});

describe('le format de style accepte les deux versions', () => {
  // Le validateur de MapLibre, celui-là même qui refusait `place-highlight` en
  // silence sur la carte principale.
  const cas: [string, unknown, unknown][] = [
    ['web', couleurDesTerritoires(), opaciteDesTerritoires()],
    ['natif, peint', couleurDesTerritoiresNative(PEINTS), opaciteDesTerritoiresNative(PEINTS)],
    ['natif, vierge', couleurDesTerritoiresNative([]), opaciteDesTerritoiresNative([])],
  ];

  for (const [nom, couleur, opacite] of cas) {
    it(`— ${nom}`, () => {
      const erreurs = validateStyleMin(styleAvec(couleur, opacite) as never);
      expect(erreurs.map((e) => e.message)).toEqual([]);
    });
  }
});
