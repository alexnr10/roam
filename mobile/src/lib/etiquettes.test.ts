import fs from 'node:fs';
import path from 'node:path';

import { pointsDeNom } from './etiquettes';
import type { OutlineCollection } from '../data/outlines';

/** Un carré, donné par son coin bas-gauche et son côté. */
const carre = (x: number, y: number, c: number): number[][] => [
  [x, y], [x + c, y], [x + c, y + c], [x, y + c], [x, y],
];

const collection = (
  geometries: Array<GeoJSON.Polygon | GeoJSON.MultiPolygon>,
): OutlineCollection => ({
  type: 'FeatureCollection',
  features: geometries.map((geometry, i) => ({
    type: 'Feature',
    geometry,
    properties: { code: `0${i + 1}`, nom: `Territoire ${i + 1}` },
  })),
});

describe('pointsDeNom', () => {
  it('rend UN point par territoire, quel que soit son nombre de morceaux', () => {
    // Le cas qui a motivé la fonction : la province de Lecce est un
    // `MultiPolygon` de trois morceaux, et son nom s'écrivait trois fois.
    const points = pointsDeNom(
      collection([
        { type: 'Polygon', coordinates: [carre(0, 0, 2)] },
        {
          type: 'MultiPolygon',
          coordinates: [[carre(10, 10, 4)], [carre(20, 20, 1)], [carre(30, 30, 1)]],
        },
      ]),
    );
    expect(points.features).toHaveLength(2);
    expect(points.features.every((f) => f.geometry.type === 'Point')).toBe(true);
  });

  it('pose le point sur le plus GRAND morceau, pas sur le premier', () => {
    // Le premier morceau du Finistère est une île de Molène : poser le nom là
    // l'envoyait en mer, à cinquante kilomètres du département.
    const points = pointsDeNom(
      collection([
        {
          type: 'MultiPolygon',
          // L'îlot d'abord, le continent ensuite.
          coordinates: [[carre(0, 0, 1)], [carre(100, 100, 20)]],
        },
      ]),
    );
    expect(points.features[0].geometry.coordinates[0]).toBeCloseTo(110, 6);
    expect(points.features[0].geometry.coordinates[1]).toBeCloseTo(110, 6);
  });

  it('pondère par la SURFACE et non par le nombre de sommets', () => {
    // Un tracé côtier porte cent points sur une baie et trois sur une plaine :
    // la moyenne des sommets partirait dans la baie. Ici, un côté densément
    // échantillonné ne doit pas déplacer le centre du carré.
    const dense: number[][] = [];
    for (let i = 0; i <= 50; i++) dense.push([i / 50, 0]);
    dense.push([1, 1], [0, 1], [0, 0]);
    const points = pointsDeNom(collection([{ type: 'Polygon', coordinates: [dense] }]));
    expect(points.features[0].geometry.coordinates[0]).toBeCloseTo(0.5, 6);
    expect(points.features[0].geometry.coordinates[1]).toBeCloseTo(0.5, 6);
  });

  it('recopie les propriétés : la couche filtre sur `code` et écrit `nom`', () => {
    const points = pointsDeNom(collection([{ type: 'Polygon', coordinates: [carre(0, 0, 1)] }]));
    expect(points.features[0].properties).toEqual({ code: '01', nom: 'Territoire 1' });
  });

  it('ne rend rien plutôt que de planter quand il n’y a pas de contours', () => {
    // Un pays sans découpage n'est pas une erreur : la carte retombe sur la
    // liste, et la couche doit simplement rester vide.
    expect(pointsDeNom(null).features).toEqual([]);
    expect(pointsDeNom(collection([])).features).toEqual([]);
    // Un anneau dégénéré ne doit ni diviser par zéro ni produire un NaN.
    const degenere = pointsDeNom(
      collection([{ type: 'Polygon', coordinates: [[[5, 5], [5, 5], [5, 5]]] }]),
    );
    expect(degenere.features[0].geometry.coordinates).toEqual([5, 5]);
  });
});

/**
 * L'épreuve sur les VRAIS contours, et pas sur des carrés.
 *
 * Deux garanties, et ce sont les deux seules qui comptent : autant
 * d'étiquettes que de territoires — jamais une de plus — et chacune POSÉE
 * DANS le sien. La première est le défaut corrigé, la seconde est le piège de
 * la correction : un centre de gravité sort d'un croissant.
 */
describe('pointsDeNom, sur les contours publiés', () => {
  const dedans = ([x, y]: number[], anneau: number[][]): boolean => {
    let vrai = false;
    for (let i = 0, j = anneau.length - 1; i < anneau.length; j = i++) {
      const [xi, yi] = anneau[i];
      const [xj, yj] = anneau[j];
      if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) vrai = !vrai;
    }
    return vrai;
  };
  const aire = (a: number[][]): number => {
    let s = 0;
    for (let i = 0, j = a.length - 1; i < a.length; j = i++) s += a[j][0] * a[i][1] - a[i][0] * a[j][1];
    return Math.abs(s / 2);
  };
  const anneaux = (g: GeoJSON.Polygon | GeoJSON.MultiPolygon): number[][][] =>
    g.type === 'Polygon'
      ? [g.coordinates[0] as number[][]]
      : (g.coordinates as number[][][][]).map((p) => p[0] as number[][]);

  // Les contours d'un pays peuvent être absents — la branche `v0.1-france`
  // retire ceux de l'Italie à dessein. Un fichier manquant n'est pas un échec.
  for (const pays of ['fr', 'it']) {
    const chemin = path.join(__dirname, '..', '..', '..', 'catalogues', `${pays}-contours.json`);
    const test = fs.existsSync(chemin) ? it : it.skip;
    test(`${pays} : une étiquette par territoire, et dans le territoire`, () => {
      const contours = JSON.parse(fs.readFileSync(chemin, 'utf8'));
      for (const niveau of ['region', 'departement'] as const) {
        const collection = contours[niveau];
        if (!collection?.features?.length) continue;
        const points = pointsDeNom(collection);
        expect(points.features).toHaveLength(collection.features.length);
        const dehors = points.features.filter((point) => {
          const entite = collection.features.find(
            (f: { properties: { code: string } }) => f.properties.code === point.properties.code,
          );
          const parties = anneaux(entite.geometry).filter((a) => a.length >= 3);
          const grand = parties.reduce((a, b) => (aire(b) > aire(a) ? b : a));
          const [x, y] = point.geometry.coordinates;
          return !Number.isFinite(x) || !Number.isFinite(y) || !dedans([x, y], grand);
        });
        expect(dehors.map((d) => d.properties.nom)).toEqual([]);
      }
    });
  }
});
