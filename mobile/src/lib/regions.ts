import { areas, collections, places } from '../data/catalog';
import { outlinesFor } from '../data/outlines';
import type { Tier } from '../types';

/**
 * Ce qu'il faut savoir d'une région pour la dessiner et l'ouvrir.
 *
 * La carte de Roam n'est plus une pluie de points sur la France : c'est
 * dix-huit aplats qu'on ouvre un par un. Ce module fournit ce que cette
 * mécanique demande et que les données brutes ne disent pas — l'emprise d'une
 * région, la région sous la caméra, le voile qui couvre le hors-périmètre, et
 * le niveau d'un lieu dans la région où on le regarde.
 *
 * Tout y est pur et sans MapLibre : la carte web et la carte native s'en
 * servent pareil, et les tests n'ont besoin d'aucun moteur de rendu.
 */

export type Anneau = [number, number][];
export type Emprise = [[number, number], [number, number]];

type Geometrie = GeoJSON.Polygon | GeoJSON.MultiPolygon;

/** Les polygones d'une géométrie, qu'elle en porte un ou douze. */
function polygones(geometry: Geometrie): GeoJSON.Position[][][] {
  return geometry.type === 'Polygon' ? [geometry.coordinates] : geometry.coordinates;
}

/**
 * L'emprise d'une géométrie : [[ouest, sud], [est, nord]].
 *
 * C'est elle qui donne le zoom d'arrivée, et c'est pour cela qu'il n'est jamais
 * fixe. Mayotte arrive beaucoup plus près que l'Occitanie — un zoom en dur
 * donnerait huit taches perdues dans un aplat vide d'un côté, et deux cent
 * soixante-douze points débordant du cadre de l'autre.
 */
export function emprise(geometry: Geometrie): Emprise {
  let ouest = 180;
  let sud = 90;
  let est = -180;
  let nord = -90;
  for (const polygone of polygones(geometry)) {
    for (const [lon, lat] of polygone[0]) {
      if (lon < ouest) ouest = lon;
      if (lon > est) est = lon;
      if (lat < sud) sud = lat;
      if (lat > nord) nord = lat;
    }
  }
  return [
    [ouest, sud],
    [est, nord],
  ];
}

/** Lancer de rayon : le point est-il dans l'anneau ? */
function dansLAnneau(anneau: GeoJSON.Position[], lon: number, lat: number): boolean {
  let dedans = false;
  for (let i = 0, j = anneau.length - 1; i < anneau.length; j = i++) {
    const [xi, yi] = anneau[i];
    const [xj, yj] = anneau[j];
    if (yi > lat !== yj > lat && lon < ((xj - xi) * (lat - yi)) / (yj - yi) + xi) {
      dedans = !dedans;
    }
  }
  return dedans;
}

/**
 * Le point est-il dans la géométrie ? Les trous comptent.
 *
 * Une région à enclave — l'Auvergne-Rhône-Alpes en porte — a des anneaux
 * intérieurs. Les ignorer ferait « ouvrir » une région sur un territoire qui
 * ne lui appartient pas.
 */
export function contient(geometry: Geometrie, lon: number, lat: number): boolean {
  for (const polygone of polygones(geometry)) {
    if (!dansLAnneau(polygone[0], lon, lat)) continue;
    let troue = false;
    for (let i = 1; i < polygone.length; i += 1) {
      if (dansLAnneau(polygone[i], lon, lat)) {
        troue = true;
        break;
      }
    }
    if (!troue) return true;
  }
  return false;
}

const contours = outlinesFor('region');

/** Les contours de région, indexés par code INSEE. */
export const REGIONS = new Map<string, GeoJSON.Feature<Geometrie, { code: string; nom: string }>>(
  (contours?.features ?? []).map((feature) => [feature.properties.code, feature]),
);

const nomsDeRegion = new Map(areas.region.map((area) => [area.code, area.name]));

export const nomDeRegion = (code: string): string =>
  nomsDeRegion.get(code) ?? REGIONS.get(code)?.properties.nom ?? code;

/**
 * La région sous un point — celle qu'on ouvre.
 *
 * `regionOuverte` est dérivé du zoom autant que du clic : au-delà du seuil,
 * c'est la région qui remplit l'écran qui s'ouvre. Le clic n'est qu'un
 * raccourci vers cet état, et dézoomer referme. C'est le geste que tout le
 * monde tente en premier, et il ne s'apprend pas.
 */
export function regionAu(lon: number, lat: number): string | null {
  for (const [code, feature] of REGIONS) {
    if (contient(feature.geometry, lon, lat)) return code;
  }
  return null;
}

/**
 * La région que le cadre montre — celle qu'on ouvre.
 *
 * D'abord la terre sous le centre du cadre, ce qui règle les treize régions
 * métropolitaines et les trois d'outre-mer d'un seul tenant.
 *
 * Mais un ARCHIPEL n'a pas de terre en son milieu : la Guadeloupe s'étale de
 * Marie-Galante aux Saintes, et une fois cadrée, le centre de l'écran tombe en
 * pleine mer. La région se refermait donc au moment même où on venait de
 * l'ouvrir. On retombe alors sur l'emprise : la plus petite région dont le
 * rectangle contient ce point et qui remplit l'écran.
 */
export function regionDuCadre(cadre: Emprise): string | null {
  const [lon, lat] = centreDe(cadre);
  const dessus = regionAu(lon, lat);
  if (dessus) {
    const feature = REGIONS.get(dessus);
    if (feature && remplitLEcran(emprise(feature.geometry), cadre)) return dessus;
  }

  let meilleure: string | null = null;
  let plusPetite = Infinity;
  for (const [code, feature] of REGIONS) {
    const bornes = emprise(feature.geometry);
    if (lon < bornes[0][0] || lon > bornes[1][0]) continue;
    if (lat < bornes[0][1] || lat > bornes[1][1]) continue;
    if (!remplitLEcran(bornes, cadre)) continue;
    const aire = (bornes[1][0] - bornes[0][0]) * (bornes[1][1] - bornes[0][1]);
    if (aire < plusPetite) {
      plusPetite = aire;
      meilleure = code;
    }
  }
  return meilleure;
}

/** L'anneau du monde, sens direct. L'extérieur du voile. */
export function anneauDuMonde(): Anneau {
  return [
    [-180, -85],
    [180, -85],
    [180, 85],
    [-180, 85],
    [-180, -85],
  ];
}

/**
 * Le voile hors-France : le monde, percé de la France.
 *
 * Le guide s'arrête à la France, la carte non. Plutôt que de brider la
 * navigation — aucune limite d'emprise n'est posée, la carte reste une vraie
 * carte du monde — on décolore ce qui est hors périmètre.
 *
 * Un seul polygone : l'anneau extérieur est le monde, chaque anneau intérieur
 * l'enveloppe d'une région. Les cinq régions d'outre-mer en font partie, et
 * c'est ainsi qu'on découvre Mayotte : en dérivant vers l'océan Indien, un trou
 * net apparaît dans le sable. Aucun encart n'a eu à le dire.
 */
export function voile(): GeoJSON.Feature<GeoJSON.Polygon> {
  const anneaux: GeoJSON.Position[][] = [anneauDuMonde()];
  for (const feature of REGIONS.values()) {
    for (const polygone of polygones(feature.geometry)) {
      anneaux.push(polygone[0]);
    }
  }
  return {
    type: 'Feature',
    properties: {},
    geometry: { type: 'Polygon', coordinates: anneaux },
  };
}

/** Région d'un département, par son code. */
const regionParDepartement = new Map(
  areas.departement
    .filter((area) => area.parentCode)
    .map((area) => [area.code, area.parentCode as string]),
);

export const regionDuDepartement = (code: string): string | null =>
  regionParDepartement.get(code) ?? null;

/**
 * Le niveau d'un lieu DANS la région qu'on regarde.
 *
 * Roam n'a pas de niveau absolu : le niveau est relatif à une collection, et un
 * lieu peut être premier de son département et anonyme à l'échelle du pays.
 * Pour dimensionner une pastille il faut donc choisir un point de vue, et le
 * seul qui ait un sens quand une région est ouverte, c'est cette région.
 *
 * « Le meilleur d'Occitanie » classe quatre-vingts lieux sur deux cent
 * soixante-douze : douze au premier niveau, vingt-sept au deuxième. Les autres
 * restent au troisième. C'est une hiérarchie qui se lit d'un coup d'œil, là où
 * prendre le meilleur niveau toutes collections confondues donnerait quatre-
 * vingt-seize incontournables dans une seule région — donc aucun.
 *
 * Les cinq régions d'outre-mer n'ont pas de collection régionale : on retombe
 * alors sur leurs collections départementales, sans quoi les huit lieux de
 * Mayotte seraient huit points identiques.
 */
const niveauxParRegion = new Map<string, Map<string, Tier>>();

export function niveauxDe(regionCode: string): Map<string, Tier> {
  const connu = niveauxParRegion.get(regionCode);
  if (connu) return connu;

  const niveaux = new Map<string, Tier>();
  const regionale = collections.find(
    (collection) =>
      collection.geoLevel === 'region' &&
      collection.geoCode === regionCode &&
      !collection.themeId,
  );

  if (regionale) {
    for (const membre of regionale.places) niveaux.set(membre.placeId, membre.tier);
  } else {
    for (const collection of collections) {
      if (collection.geoLevel !== 'departement' || collection.themeId) continue;
      if (regionDuDepartement(collection.geoCode ?? '') !== regionCode) continue;
      for (const membre of collection.places) {
        const vu = niveaux.get(membre.placeId);
        if (vu === undefined || membre.tier < vu) niveaux.set(membre.placeId, membre.tier);
      }
    }
  }

  niveauxParRegion.set(regionCode, niveaux);
  return niveaux;
}

/** Les lieux d'une région. Le catalogue porte déjà le rattachement. */
export function lieuxDe(regionCode: string) {
  return places.filter((place) => place.regionCode === regionCode);
}

/**
 * L'ordre d'apparition des pastilles : du centre de la région vers les bords.
 *
 * Douze millisecondes entre deux points ne se comptent pas, mais deux cent
 * soixante-douze pastilles apparaissant d'un coup font un clignotement. En
 * cascade depuis le centre, ça se lit comme un remplissage.
 */
export function rangDepuisLeCentre(
  lieux: { lat: number; lon: number }[],
  centre: [number, number],
): number[] {
  const distances = lieux.map((lieu, index) => ({
    index,
    d: (lieu.lon - centre[0]) ** 2 + (lieu.lat - centre[1]) ** 2,
  }));
  distances.sort((a, b) => a.d - b.d);
  const rangs = new Array<number>(lieux.length);
  distances.forEach((entry, rang) => {
    rangs[entry.index] = rang;
  });
  return rangs;
}

/**
 * La région remplit-elle l'écran ?
 *
 * C'est LA règle d'ouverture, et elle est écrite ainsi dans le livrable : « la
 * région ouverte est celle qui remplit l'écran ». Un seuil de zoom en dur ne
 * peut pas la dire — l'Occitanie cadrée sur un téléphone atterrit vers 6,6 et
 * Mayotte vers 10,5. Le même nombre ne peut pas décrire les deux, et c'est ce
 * qui laissait les grandes régions refuser de s'ouvrir.
 *
 * On compare donc l'emprise de la région à celle de la vue. Au-delà de la
 * moitié du cadre dans un sens ou dans l'autre, on ne regarde plus la France :
 * on regarde un endroit.
 */
export function partDuCadre(region: Emprise, vue: Emprise): number {
  const largeurVue = vue[1][0] - vue[0][0];
  const hauteurVue = vue[1][1] - vue[0][1];
  if (largeurVue <= 0 || hauteurVue <= 0) return 0;
  return Math.max(
    (region[1][0] - region[0][0]) / largeurVue,
    (region[1][1] - region[0][1]) / hauteurVue,
  );
}

export function remplitLEcran(region: Emprise, vue: Emprise, part = 0.5): boolean {
  return partDuCadre(region, vue) >= part;
}

/** L'état d'ouverture : la région, et le plus haut zoom atteint depuis. */
export type Ouverture = { region: string | null; ancre: number | null };

/**
 * De combien le zoom doit baisser pour compter comme un dézoom.
 *
 * Deux fins de mouvement consécutives peuvent rendre des zooms qui diffèrent
 * au millième ; sans ce seuil, cette poussière passerait pour un geste.
 */
export const BRUIT_DE_ZOOM = 0.05;

/**
 * Ce que devient l'ouverture à la fin d'un mouvement de caméra.
 *
 * La règle « la région ouverte est celle qui remplit l'écran » est juste tant
 * qu'on se déplace, et fausse juste après un clic : réévaluée à l'arrivée du
 * vol qu'on vient de déclencher, elle peut DÉFAIRE le geste de l'utilisateur
 * sur un calcul qu'il n'a pas demandé. Les lieux apparaissaient, puis
 * disparaissaient — et il fallait zoomer pour les faire revenir.
 *
 * Deux gestes seulement peuvent donc refermer, et ce sont des gestes :
 *
 * - **dézoomer** jusqu'à ce que la région ne remplisse plus l'écran ;
 * - **se déplacer** jusque chez la voisine, qui prend alors la place.
 *
 * Une caméra qui n'a pas reculé ne referme jamais, quoi que dise la géométrie.
 * C'est ce qui rend la mécanique insensible aux cas limites — une région tout
 * juste cadrée, un archipel, un écran inhabituellement court.
 *
 * `ancre` est le plus haut zoom atteint depuis l'ouverture : sans quoi, zoomer
 * sur un village puis ressortir au cadrage d'arrivée compterait comme un
 * dézoom. `ancre: null` avec une région ouverte signale un clic dont le vol
 * vient d'arriver : on pose l'ancre là, sans rien remettre en cause.
 */
export function prochaineOuverture(
  actuelle: Ouverture,
  vue: string | null,
  zoom: number,
  bruit = BRUIT_DE_ZOOM,
): Ouverture {
  if (!actuelle.region) {
    return { region: vue, ancre: vue ? zoom : null };
  }
  if (actuelle.ancre === null) {
    return { region: actuelle.region, ancre: zoom };
  }
  if (vue && vue !== actuelle.region) {
    return { region: vue, ancre: zoom };
  }
  if (!vue && zoom < actuelle.ancre - bruit) {
    return { region: null, ancre: null };
  }
  return { region: actuelle.region, ancre: Math.max(actuelle.ancre, zoom) };
}

/** Le centre d'une emprise. */
export function centreDe(bornes: Emprise): [number, number] {
  return [(bornes[0][0] + bornes[1][0]) / 2, (bornes[0][1] + bornes[1][1]) / 2];
}
