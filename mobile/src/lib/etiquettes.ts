import type { OutlineCollection } from '../data/outlines';

/**
 * UN point de nom par territoire, et pas un par morceau de territoire.
 *
 * MapLibre pose une étiquette au centre de CHAQUE polygone d'une géométrie.
 * Nos contours sont des `MultiPolygon` dès qu'un territoire a une île, une
 * presqu'île détachée ou une enclave — et l'application écrivait alors son nom
 * autant de fois qu'il a de morceaux.
 *
 * Ce n'est pas un cas rare, c'est la règle sur une côte. Compté sur les
 * contours publiés :
 *
 *     FR départements   24 territoires morcelés → 124 étiquettes en trop
 *     FR régions        11 →  117   (la Bretagne : 49 morceaux)
 *     IT provinces      33 →   96   (Olbia-Tempio : 19)
 *     IT régions        12 →   84   (la Sardaigne : 30)
 *
 * La collision de MapLibre en cache une partie, mais pas toutes, et celles
 * qu'elle laisse passer chassent des étiquettes utiles : « Lecce » s'écrivait
 * trois fois au-dessus des Pouilles, « Finistère » aurait pu s'écrire dix-neuf
 * fois — une par île.
 *
 * Le remède est de ne plus donner de polygone à l'étiquette : une source de
 * POINTS, un par territoire, posé sur son plus grand morceau. Le plus grand et
 * non le premier : celui du Finistère est une île de Molène, et le nom du
 * département serait parti en mer.
 */
export type PointsDeNom = GeoJSON.FeatureCollection<
  GeoJSON.Point,
  { code: string; nom: string }
>;

/** L'aire algébrique d'un anneau, en degrés carrés. Le signe ne nous sert pas. */
function aire(anneau: number[][]): number {
  let somme = 0;
  for (let i = 0, j = anneau.length - 1; i < anneau.length; j = i++) {
    somme += anneau[j][0] * anneau[i][1] - anneau[i][0] * anneau[j][1];
  }
  return Math.abs(somme / 2);
}

/**
 * Le centre de gravité d'un anneau.
 *
 * La moyenne des sommets ne convient pas : un tracé côtier porte cent points
 * sur une baie et trois sur une plaine, et le centre partirait dans la baie.
 * La formule de l'aire pondère par la SURFACE, ce que l'œil attend.
 *
 * Un anneau d'aire nulle — un tracé dégénéré — rendrait une division par zéro :
 * on retombe alors sur la moyenne des sommets, qui est au moins un point du
 * bon endroit.
 */
function centre(anneau: number[][]): [number, number] {
  let x = 0;
  let y = 0;
  let deux = 0;
  for (let i = 0, j = anneau.length - 1; i < anneau.length; j = i++) {
    const croix = anneau[j][0] * anneau[i][1] - anneau[i][0] * anneau[j][1];
    deux += croix;
    x += (anneau[j][0] + anneau[i][0]) * croix;
    y += (anneau[j][1] + anneau[i][1]) * croix;
  }
  if (deux === 0) {
    const n = anneau.length || 1;
    return [
      anneau.reduce((s, p) => s + p[0], 0) / n,
      anneau.reduce((s, p) => s + p[1], 0) / n,
    ];
  }
  return [x / (3 * deux), y / (3 * deux)];
}

/** Le point est-il à l'intérieur de l'anneau ? Lancer de rayon horizontal. */
function dedans([x, y]: [number, number], anneau: number[][]): boolean {
  let vrai = false;
  for (let i = 0, j = anneau.length - 1; i < anneau.length; j = i++) {
    const [xi, yi] = anneau[i];
    const [xj, yj] = anneau[j];
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) vrai = !vrai;
  }
  return vrai;
}

/**
 * Un point GARANTI dans le territoire, et pas seulement à son centre.
 *
 * Le centre de gravité sort d'une forme concave : mesuré sur les contours
 * publiés, quatre territoires sur 249 le voient tomber dehors — les
 * Hauts-de-Seine, qui font un croissant autour de Paris, la Ligurie, qui suit
 * un arc de côte, Verceil et Rimini. Une étiquette « Hauts-de-Seine » posée
 * dans Paris désigne le mauvais département.
 *
 * Quand le centre est dehors, on coupe le territoire par une horizontale à sa
 * hauteur et on se pose au milieu du plus large segment intérieur. C'est ce
 * que fait `ST_PointOnSurface` : moins joli qu'un vrai pôle d'inaccessibilité,
 * mais toujours dedans, et en vingt lignes.
 */
function surLaSurface(anneau: number[][]): [number, number] {
  const centreG = centre(anneau);
  if (dedans(centreG, anneau)) return centreG;

  const y = centreG[1];
  const passages: number[] = [];
  for (let i = 0, j = anneau.length - 1; i < anneau.length; j = i++) {
    const [xi, yi] = anneau[i];
    const [xj, yj] = anneau[j];
    if (yi > y !== yj > y) passages.push(((xj - xi) * (y - yi)) / (yj - yi) + xi);
  }
  passages.sort((a, b) => a - b);

  let meilleur: [number, number] | null = null;
  let large = -1;
  // Les segments INTÉRIEURS sont les paires : entre le 1er et le 2e passage,
  // entre le 3e et le 4e, et ainsi de suite.
  for (let i = 0; i + 1 < passages.length; i += 2) {
    const largeur = passages[i + 1] - passages[i];
    if (largeur > large) {
      large = largeur;
      meilleur = [(passages[i] + passages[i + 1]) / 2, y];
    }
  }
  return meilleur ?? centreG;
}

/** Les anneaux EXTÉRIEURS d'une géométrie, un par morceau. */
function morceaux(geometrie: GeoJSON.Polygon | GeoJSON.MultiPolygon): number[][][] {
  return geometrie.type === 'Polygon'
    ? [geometrie.coordinates[0] as number[][]]
    : (geometrie.coordinates as number[][][][]).map((p) => p[0] as number[][]);
}

/**
 * Un point par territoire, posé sur son plus grand morceau.
 *
 * Les propriétés sont recopiées telles quelles : la couche d'étiquettes filtre
 * sur `code` et écrit `nom`, exactement comme lorsqu'elle lisait les polygones.
 */
export function pointsDeNom(contours: OutlineCollection | null): PointsDeNom {
  const features = (contours?.features ?? []).flatMap((entite) => {
    const anneaux = morceaux(entite.geometry).filter((a) => a.length >= 3);
    if (anneaux.length === 0) return [];
    const plusGrand = anneaux.reduce((a, b) => (aire(b) > aire(a) ? b : a));
    return [
      {
        type: 'Feature' as const,
        geometry: { type: 'Point' as const, coordinates: surLaSurface(plusGrand) },
        properties: entite.properties,
      },
    ];
  });
  return { type: 'FeatureCollection', features };
}
