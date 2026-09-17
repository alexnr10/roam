import { areas, places, surChangement } from '../data/catalog';
import { outlinesFor } from '../data/outlines';

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

/** Les contours de région, indexés par code INSEE. */
export let REGIONS = new Map<string, GeoJSON.Feature<Geometrie, { code: string; nom: string }>>();

/**
 * Le code de la région d'un pays qui n'en a pas : le pays lui-même.
 *
 * La carte n'affiche les pastilles que DANS une région ouverte. C'est la bonne
 * mécanique pour la France et l'Italie — dix-huit et vingt aplats qu'on ouvre
 * un par un — et c'est une carte vide pour le Vatican, qui fait quarante-quatre
 * hectares et n'a aucune subdivision : `regionAu` ne répond jamais, rien ne
 * s'ouvre, et la source des lieux reste vide. Mesuré sur le catalogue servi :
 * dix-neuf lieux, zéro contour, zéro lieu ouvrable.
 *
 * Un pays qui tient dans un écran n'a rien à ouvrir : il EST ouvert. Ce code
 * est la région que ce pays-là présente, et `lieuxDe` lui rend tout le
 * catalogue. Aucune donnée à télécharger — c'est l'absence de contour qui le
 * déclenche, et c'est elle qui décrit le cas.
 */
export const PAYS_ENTIER = '__pays__';

/** Le pays regardé n'a aucun contour de région : il est d'un seul tenant. */
export function dUnSeulTenant(): boolean {
  return REGIONS.size === 0;
}

/**
 * Ce code désigne-t-il une région qu'on peut ouvrir ICI ?
 *
 * `REGIONS.has` seul disait non à `PAYS_ENTIER`, et trois gardes l'employaient :
 * celui qui referme une région quand le pays change sous elle, et les deux qui
 * ouvrent la région au DÉPART d'un vol. Au Vatican, la carte ouvrait donc le
 * pays au `moveend` et le refermait dans la foulée — mesuré : les pastilles
 * apparaissaient puis disparaissaient, et un vol atterrissait sur du vide.
 */
export function regionConnue(code: string | null): boolean {
  if (!code) return false;
  return REGIONS.has(code) || (code === PAYS_ENTIER && dUnSeulTenant());
}

/** Ce lieu est-il dans la région ouverte ? */
export function dansLaRegion(place: { regionCode?: string | null }, code: string): boolean {
  return code === PAYS_ENTIER || place.regionCode === code;
}

let nomsDeRegion = new Map<string, string>();
let regionParDepartement = new Map<string, string>();

/**
 * Tout ce que ce module dérive du catalogue, refait quand le catalogue change.
 *
 * Un pays a ses régions, ses départements et ses contours : garder ceux du
 * précédent après un changement de pays donnerait une carte française avec des
 * lieux italiens dessus.
 */
function indexer(): void {
  const contours = outlinesFor('region');
  REGIONS = new Map(
    (contours?.features ?? []).map((feature) => [feature.properties.code, feature]),
  );
  nomsDeRegion = new Map(areas.region.map((area) => [area.code, area.name]));
  regionParDepartement = new Map(
    areas.departement
      .filter((area) => area.parentCode)
      .map((area) => [area.code, area.parentCode as string]),
  );
}

indexer();
surChangement(indexer);

export const nomDeRegion = (code: string): string =>
  (code === PAYS_ENTIER ? areas.country[0]?.name : undefined) ??
  nomsDeRegion.get(code) ??
  REGIONS.get(code)?.properties.nom ??
  code;

/**
 * La région sous un point — celle qu'on ouvre.
 *
 * `regionOuverte` est dérivé du zoom autant que du clic : au-delà du seuil,
 * c'est la région qui remplit l'écran qui s'ouvre. Le clic n'est qu'un
 * raccourci vers cet état, et dézoomer referme. C'est le geste que tout le
 * monde tente en premier, et il ne s'apprend pas.
 */
export function regionAu(lon: number, lat: number): string | null {
  if (dUnSeulTenant()) return PAYS_ENTIER;
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
  if (dUnSeulTenant()) return PAYS_ENTIER;
  const [lon, lat] = centreDe(cadre);
  const dessus = regionAu(lon, lat);
  if (dessus) {
    const feature = REGIONS.get(dessus);
    if (feature && remplitLEcran(emprise(feature.geometry), cadre)) return dessus;
  }

  // Le centre n'est sur AUCUNE région : on demande aux lieux.
  //
  // Ce cas n'est pas rare — 130 lieux italiens et 147 français tombent hors de
  // tout contour, parce que les tracés sont simplifiés et que la mer les
  // rogne : le Mont Saint-Michel, l'île de Sein, le phare de Cordouan. Et
  // Saint-Marin, qui n'est dans aucune région italienne pour une raison
  // autrement meilleure : c'est un autre pays.
  //
  // Les LIEUX du cadre savent mieux que les polygones ce qu'on regarde. Le
  // repli sur la plus petite emprise, lui, ne savait que deviner : au-dessus
  // de Saint-Marin il choisissait les Marches parce que leur rectangle est
  // plus petit que celui de l'Émilie-Romagne, à laquelle les lieux de
  // Saint-Marin sont rattachés. On ouvrait donc une région, et on filtrait les
  // lieux d'une autre — elles ne se rencontraient jamais.
  //
  // Mesuré sur les deux catalogues, en cadrant successivement sur chacun des
  // 4 156 lieux : 24 lieux dont le cadre ouvrait une autre région que la leur,
  // 7 après cette règle. Et elle ne s'applique QU'ICI, en repli : essayée
  // partout, elle faisait passer l'Italie de 14 injoignables à 39, car elle
  // écrasait alors des réponses justes.
  const parLesLieux = regionLaMieuxRepresentee(cadre);
  if (parLesLieux) return parLesLieux;

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

/**
 * La région dont le cadre montre le plus de lieux, ou `null` s'il n'en montre
 * aucun.
 *
 * Une égalité se tranche par le code, pour que deux appels sur le même cadre
 * rendent toujours la même chose : une région qui changerait d'un rendu à
 * l'autre ferait clignoter le bandeau.
 */
export function regionLaMieuxRepresentee(cadre: Emprise): string | null {
  const compte = new Map<string, number>();
  for (const place of places) {
    if (!place.regionCode) continue;
    if (place.lon < cadre[0][0] || place.lon > cadre[1][0]) continue;
    if (place.lat < cadre[0][1] || place.lat > cadre[1][1]) continue;
    compte.set(place.regionCode, (compte.get(place.regionCode) ?? 0) + 1);
  }
  let meilleure: string | null = null;
  let plus = 0;
  for (const [code, combien] of [...compte].sort((a, b) => a[0].localeCompare(b[0]))) {
    if (combien <= plus) continue;
    // La même condition que pour l'autre repli, et elle n'est pas
    // facultative : une région doit REMPLIR l'écran pour être dite ouverte.
    // Sans elle, une vue de la France entière ouvrait l'Occitanie — celle qui
    // porte le plus de lieux — au lieu de ne rien ouvrir du tout. Regarder un
    // pays n'est pas regarder un endroit.
    const feature = REGIONS.get(code);
    if (!feature || !remplitLEcran(emprise(feature.geometry), cadre)) continue;
    plus = combien;
    meilleure = code;
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
  // Un pays sans contour perçait le monde de RIEN : le voile couvrait alors la
  // carte entière, le pays compris. Son emprise fait le trou — un rectangle
  // plutôt qu'une frontière, ce qui suffit à quarante-quatre hectares et ne
  // demande aucune donnée de plus.
  if (dUnSeulTenant()) {
    const bornes = bornesDuPays();
    if (bornes) {
      const [[ouest, sud], [est, nord]] = bornes;
      anneaux.push([
        [ouest, sud],
        [est, sud],
        [est, nord],
        [ouest, nord],
        [ouest, sud],
      ]);
    }
    return {
      type: 'Feature',
      properties: {},
      geometry: { type: 'Polygon', coordinates: anneaux },
    };
  }
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

/**
 * La part des lieux que la vue de départ doit contenir.
 *
 * Pas cent pour cent, et c'est tout le point. L'union BRUTE des contours
 * français va de la Guadeloupe à La Réunion : une vue de départ qui montre le
 * globe entier pour quatre lieux à l'autre bout du monde n'est pas une vue de
 * départ. On cadre là où le catalogue est, et l'outre-mer se découvre en
 * dérivant — un trou net apparaît dans le voile, ce qu'aucun encart n'aurait
 * dit aussi bien.
 */
const PART_CADREE = 0.95;

/**
 * L'emprise du pays regardé — ce que la caméra doit cadrer.
 *
 * Elle était une CONSTANTE, et cette constante était la France. En changeant de
 * pays depuis « Moi », la carte gardait donc son cadrage français : l'Italie
 * apparaissait en morceau, contre le bord droit de l'écran, ce qui se lit comme
 * une carte cassée. La pastille de retour ramenait au même endroit.
 *
 * Les contours d'abord, région par région, des plus peuplées en lieux aux
 * moins peuplées, jusqu'à en couvrir `PART_CADREE`. À défaut de contours — un
 * pays peut très bien arriver sans — l'étendue de ses lieux, qui n'est pas la
 * frontière mais cadre ce qu'on est venu voir. Et `null` si on ne sait rien :
 * l'appelant garde alors son cadrage de départ plutôt que de sauter sur le
 * méridien de Greenwich.
 */
export function bornesDuPays(): Emprise | null {
  let ouest = 180;
  let sud = 90;
  let est = -180;
  let nord = -90;
  let vu = false;

  const elargir = (o: number, s: number, e: number, n: number) => {
    if (o < ouest) ouest = o;
    if (s < sud) sud = s;
    if (e > est) est = e;
    if (n > nord) nord = n;
    vu = true;
  };

  const parRegion = new Map<string, number>();
  for (const lieu of places) {
    if (!lieu.regionCode) continue;
    parRegion.set(lieu.regionCode, (parRegion.get(lieu.regionCode) ?? 0) + 1);
  }

  if (REGIONS.size > 0) {
    const total = [...parRegion.values()].reduce((somme, n) => somme + n, 0);
    // Sans aucun rattachement, on ne peut pas trier : on prend tout.
    const classees = [...REGIONS.keys()].sort(
      (a, b) => (parRegion.get(b) ?? 0) - (parRegion.get(a) ?? 0) || a.localeCompare(b),
    );
    let couverts = 0;
    for (const code of classees) {
      const feature = REGIONS.get(code);
      if (!feature) continue;
      const [[o, s], [e, n]] = emprise(feature.geometry);
      elargir(o, s, e, n);
      couverts += parRegion.get(code) ?? 0;
      if (total > 0 && couverts >= total * PART_CADREE) break;
    }
    if (vu) return [[ouest, sud], [est, nord]];
  }

  for (const lieu of places) elargir(lieu.lon, lieu.lat, lieu.lon, lieu.lat);
  return vu ? [[ouest, sud], [est, nord]] : null;
}

/**
 * Qui touche qui, parmi les régions dessinées.
 *
 * Les contours sont JOINTIFS par construction — le pipeline les découpe en arcs
 * partagés, simplifie chaque arc une seule fois, puis recoud. Deux régions
 * voisines portent donc EXACTEMENT les mêmes sommets sur leur frontière
 * commune, et il suffit de les compter : aucune géométrie à intersecter.
 *
 * Sert au coloriage — quatre sables, et jamais le même de part et d'autre
 * d'une frontière, sans quoi la frontière disparaît.
 */
export function voisinage(): Map<string, Set<string>> {
  return voisinageDe(REGIONS.values());
}

/** La même chose sur une collection quelconque — c'est ce qui la rend testable. */
export function voisinageDe(
  features: Iterable<GeoJSON.Feature<Geometrie, { code: string; nom: string }>>,
): Map<string, Set<string>> {
  const parSommet = new Map<string, string[]>();
  const voisins = new Map<string, Set<string>>();

  for (const feature of features) {
    const code = feature.properties.code;
    voisins.set(code, new Set());
    for (const polygone of polygones(feature.geometry)) {
      for (const anneau of polygone) {
        for (const [lon, lat] of anneau) {
          const cle = `${lon},${lat}`;
          const ici = parSommet.get(cle);
          if (ici) { if (!ici.includes(code)) ici.push(code); }
          else parSommet.set(cle, [code]);
        }
      }
    }
  }

  for (const codes of parSommet.values()) {
    if (codes.length < 2) continue;
    for (const un of codes) {
      for (const autre of codes) if (un !== autre) voisins.get(un)?.add(autre);
    }
  }
  return voisins;
}

/** Deux emprises se touchent-elles ? */
function chevauche(a: Emprise, b: Emprise): boolean {
  return a[0][0] <= b[1][0] && a[1][0] >= b[0][0]
      && a[0][1] <= b[1][1] && a[1][1] >= b[0][1];
}

/**
 * Les régions qui tiennent dans le cadre du pays — ce que montre la vignette.
 *
 * C'était une LISTE DE CODES : 01 à 04 et 06, les cinq régions d'outre-mer,
 * sorties d'une vignette qu'elles auraient étirée sur deux océans. Ces mêmes
 * codes, en Italie, sont le Piémont, le Val d'Aoste, la Lombardie, le Trentin
 * et le Frioul : la vignette italienne perdait tout son nord, sans un mot.
 * Même accident que le coloriage, même cause — une table écrite pour un pays,
 * appliquée à un autre.
 *
 * La règle est donc géométrique, et c'est le cadre de `bornesDuPays` : le même
 * que celui sur lequel la carte s'ouvre.
 */
export function regionsDuCadre(cadre: Emprise | null = bornesDuPays()): string[] {
  return [...REGIONS.keys()].filter(
    (code) => !cadre || chevauche(emprise(REGIONS.get(code)!.geometry), cadre),
  );
}

/** Région d'un département, par son code. */
export const regionDuDepartement = (code: string): string | null =>
  regionParDepartement.get(code) ?? null;

/** Les lieux d'une région. Le catalogue porte déjà le rattachement. */
export function lieuxDe(regionCode: string) {
  if (regionCode === PAYS_ENTIER) return places;
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

/**
 * La latitude, projetée comme sur la carte.
 *
 * C'est la formule de Mercator, celle qu'emploie MapLibre : plus on monte vers
 * le pôle, plus un degré de latitude occupe de place à l'écran. Sans elle, un
 * croquis dessiné à partir de degrés bruts est écrasé en hauteur — et il ne
 * ressemble plus à la carte dont il est censé être la vignette.
 */
function mercator(lat: number): number {
  const borne = Math.max(-85, Math.min(85, lat));
  return (180 / Math.PI) * Math.log(Math.tan(Math.PI / 4 + (borne * Math.PI) / 360));
}

/**
 * La silhouette d'une région, en tracé SVG.
 *
 * Une liste de dix-huit noms se lit ; une liste de dix-huit FORMES se
 * reconnaît. C'est ce qui permet de trouver la Bretagne sans lire, et
 * accessoirement de comprendre que les cinq d'outre-mer sont des régions comme
 * les autres — elles y figurent avec leur dessin, pas avec un astérisque.
 *
 * Les latitudes sont inversées : en SVG l'axe vertical descend, et sans cette
 * inversion la France se dessinerait la tête en bas.
 */
export function cheminSvg(geometry: Geometrie, taille: number): string {
  return cheminSvgDans(geometry, emprise(geometry), taille);
}

/**
 * Le même tracé, mais projeté dans une emprise IMPOSÉE.
 *
 * C'est ce qui permet de dessiner treize régions dans une seule vignette : sans
 * cadre commun, chacune remplirait la boîte pour son compte et la France
 * deviendrait un tas de formes empilées.
 */
export function cheminSvgDans(
  geometry: Geometrie,
  bornes: Emprise,
  taille: number,
): string {
  // Mercator, comme la carte.
  //
  // Porter les latitudes telles quelles APLATIT le dessin : à la hauteur de la
  // France, un degré de longitude ne vaut que 0,69 degré de latitude sur le
  // terrain. La France y perdait un tiers de sa hauteur, et le croquis ne
  // ressemblait plus à la carte qu'il ouvre.
  const bas = mercator(bornes[0][1]);
  const haut = mercator(bornes[1][1]);
  const largeur = bornes[1][0] - bornes[0][0];
  const hauteur = haut - bas;
  if (largeur <= 0 || hauteur <= 0) return '';
  // Le facteur commun aux deux axes : une région étirée pour remplir le carré
  // ne se reconnaîtrait plus.
  const echelle = taille / Math.max(largeur, hauteur);
  const margeX = (taille - largeur * echelle) / 2;
  const margeY = (taille - hauteur * echelle) / 2;
  const x = (lon: number) => margeX + (lon - bornes[0][0]) * echelle;
  const y = (lat: number) => margeY + (haut - mercator(lat)) * echelle;

  const morceaux: string[] = [];
  for (const polygone of polygones(geometry)) {
    for (const anneau of polygone) {
      if (anneau.length < 3) continue;
      const points = anneau.map(
        ([lon, lat]) => `${x(lon).toFixed(2)} ${y(lat).toFixed(2)}`,
      );
      morceaux.push(`M${points[0]}L${points.slice(1).join('L')}Z`);
    }
  }
  return morceaux.join('');
}

/** Le centre d'une emprise. */
export function centreDe(bornes: Emprise): [number, number] {
  return [(bornes[0][0] + bornes[1][0]) / 2, (bornes[0][1] + bornes[1][1]) / 2];
}
