import type { Area, AreaLevel, Place, Tier, Visit } from '../types';

/**
 * La carte de conquête : quels territoires sont acquis, et à quel point.
 *
 * Une collection cochée est une liste. Un département colorié est un
 * territoire. C'est la même donnée, mais seule la seconde donne une raison
 * d'aller dans la Creuse.
 *
 * Deux états se distinguent, et ce sont les deux couleurs de la carte :
 *
 * - **une collection terminée** — tous les lieux d'un thème dans la zone ;
 * - **la zone terminée** — tous les lieux de la zone, tous thèmes confondus.
 *
 * Le second implique le premier pour chaque thème : c'est une conquête totale,
 * et elle doit se voir comme telle.
 */

/** Les quatre échelles de la carte, de la plus fine à la plus large. */
export const CONQUEST_LEVELS: AreaLevel[] = [
  'commune',
  'departement',
  'region',
  'country',
];

/**
 * En deçà, un territoire n'est pas jouable pour un thème donné.
 *
 * Sans ce garde-fou, un département contenant UN château se colore au premier
 * château visité, et la couleur ne veut plus rien dire. Les collections
 * n'existent qu'à partir de huit lieux ; ce seuil-là est trop haut pour la
 * carte, qui resterait vide.
 *
 * L'unité « tous thèmes confondus » n'y est pas soumise : une commune d'un
 * seul lieu se conquiert en une visite, et c'est exactement l'effet voulu —
 * la carte générale se remplit vite, les cartes de thème sont le jeu long.
 */
export const PLAYABLE_MIN = 3;

/** Paliers de conquête, en nombre de lieux — plus serrés que ceux des collections. */
const TIER_SIZES: [number, number] = [3, 8];

export type ConquestUnit = {
  level: AreaLevel;
  code: string;
  /** `null` pour l'unité « tous thèmes confondus » du territoire. */
  themeId: string | null;
  /** Lieux du territoire, du meilleur au moins bon. */
  placeIds: string[];
  /** Niveau de chaque lieu DANS ce territoire, même indice que `placeIds`. */
  tiers: Tier[];
  playable: boolean;
};

export type ConquestState = {
  visited: number;
  total: number;
  pct: number;
  /** Plus haut niveau entièrement validé, 0 si aucun. */
  tier: 0 | Tier;
  complete: boolean;
};

export type ZoneConquest = {
  area: Area;
  /** Le territoire entier, tous thèmes confondus. */
  overall: ConquestState;
  /** Par thème jouable, du plus avancé au moins avancé. */
  themes: Array<{ themeId: string; state: ConquestState }>;
  /** Au moins une collection thématique terminée : première couleur. */
  anyThemeComplete: boolean;
  /** Tous les lieux du territoire validés : seconde couleur. */
  allComplete: boolean;
};

export function zoneCodeOf(place: Place, level: AreaLevel): string | null {
  switch (level) {
    case 'commune':
      return place.communeCode ?? null;
    case 'departement':
      return place.departementCode ?? null;
    case 'region':
      return place.regionCode ?? null;
    case 'country':
      // Le catalogue est national : tout lieu retenu est en France.
      return 'FR';
  }
}

/**
 * Découpe les lieux en unités de conquête pour une échelle donnée.
 *
 * Le niveau d'un lieu est calculé DANS chaque territoire, et non repris de sa
 * collection : le même château est le meilleur du Cantal et le trentième de
 * France. C'est ce qui correspond à l'intuition — « j'ai fait les trois
 * meilleurs châteaux du Cantal, donc le Cantal est acquis ».
 */
export function buildUnits(places: Place[], level: AreaLevel): ConquestUnit[] {
  const byZone = new Map<string, Place[]>();
  const byZoneTheme = new Map<string, Place[]>();

  for (const place of places) {
    const code = zoneCodeOf(place, level);
    if (!code) continue;
    push(byZone, code, place);
    push(byZoneTheme, `${code} ${place.themeId}`, place);
  }

  const units: ConquestUnit[] = [];
  for (const [code, members] of byZone) {
    units.push(makeUnit(level, code, null, members));
  }
  for (const [key, members] of byZoneTheme) {
    const separator = key.indexOf(' ');
    units.push(
      makeUnit(level, key.slice(0, separator), key.slice(separator + 1), members),
    );
  }
  return units;
}

function push<T>(map: Map<string, T[]>, key: string, value: T): void {
  const list = map.get(key);
  if (list) list.push(value);
  else map.set(key, [value]);
}

function makeUnit(
  level: AreaLevel,
  code: string,
  themeId: string | null,
  members: Place[],
): ConquestUnit {
  const ordered = [...members].sort(
    (a, b) => b.score - a.score || a.name.localeCompare(b.name, 'fr'),
  );
  return {
    level,
    code,
    themeId,
    placeIds: ordered.map((place) => place.id),
    tiers: ordered.map((_, index) => localTier(index)),
    // Le seuil ne vaut que pour un thème : voir PLAYABLE_MIN.
    playable: themeId === null || ordered.length >= PLAYABLE_MIN,
  };
}

/** Niveau d'un lieu selon son rang dans le territoire (indice à partir de 0). */
function localTier(index: number): Tier {
  if (index < TIER_SIZES[0]) return 1;
  if (index < TIER_SIZES[1]) return 2;
  return 3;
}

export function unitState(unit: ConquestUnit, visited: Set<string>): ConquestState {
  const total = unit.placeIds.length;
  const done = unit.placeIds.filter((id) => visited.has(id)).length;

  // Le niveau atteint est le plus haut dont TOUS les lieux sont validés, et
  // les niveaux sont cumulatifs : on ne tient pas le niveau 2 sans le 1.
  //
  // Le plafond est le niveau le plus profond que le territoire CONTIENT, et
  // non 3 : un département de trois châteaux serait sinon « niveau 3 » pour
  // trois visites, à égalité avec un département qui en compte quatre-vingts.
  // Le niveau dit la profondeur atteinte ; `complete` dit qu'on a tout fait.
  const deepest = unit.tiers.reduce<Tier>((top, value) => (value > top ? value : top), 1);
  let tier: 0 | Tier = 0;
  for (const candidate of [1, 2, 3] as Tier[]) {
    if (candidate > deepest) break;
    const required = unit.placeIds.filter((_, index) => unit.tiers[index] <= candidate);
    if (required.length === 0) continue;
    if (!required.every((id) => visited.has(id))) break;
    tier = candidate;
  }

  return {
    visited: done,
    total,
    pct: total === 0 ? 0 : Math.round((done / total) * 1000) / 10,
    tier,
    complete: total > 0 && done === total,
  };
}

/**
 * État de conquête de chaque territoire d'une échelle.
 *
 * Les territoires sans aucune visite sont renvoyés eux aussi : la carte a
 * besoin de savoir qu'ils existent pour les dessiner en neutre, et l'écran de
 * conquête doit pouvoir montrer ce qu'il reste à faire.
 */
export function conquestByZone(
  places: Place[],
  areas: Area[],
  level: AreaLevel,
  visits: Visit[],
): ZoneConquest[] {
  const visited = new Set(visits.map((visit) => visit.placeId));
  const byCode = new Map(areas.map((area) => [area.code, area]));
  const units = buildUnits(places, level);

  const zones = new Map<string, ZoneConquest>();
  for (const unit of units) {
    const area = byCode.get(unit.code);
    if (!area) continue;

    const state = unitState(unit, visited);
    const zone = zones.get(unit.code) ?? {
      area,
      overall: state,
      themes: [],
      anyThemeComplete: false,
      allComplete: false,
    };

    if (unit.themeId === null) {
      zone.overall = state;
      zone.allComplete = state.complete;
    } else if (unit.playable) {
      zone.themes.push({ themeId: unit.themeId, state });
      zone.anyThemeComplete = zone.anyThemeComplete || state.complete;
    }
    zones.set(unit.code, zone);
  }

  const out = [...zones.values()];
  for (const zone of out) {
    zone.themes.sort(
      (a, b) => b.state.pct - a.state.pct || a.themeId.localeCompare(b.themeId),
    );
  }
  // Les territoires les plus avancés d'abord : c'est là qu'il reste peu à faire.
  out.sort(
    (a, b) =>
      Number(b.allComplete) - Number(a.allComplete) ||
      Number(b.anyThemeComplete) - Number(a.anyThemeComplete) ||
      b.overall.pct - a.overall.pct ||
      a.area.name.localeCompare(b.area.name, 'fr'),
  );
  return out;
}

/**
 * Comment colorier un territoire.
 *
 * Deux couleurs, comme demandé, et un dégradé pour ce qui est entamé — sans
 * quoi la carte resterait binaire et ne montrerait aucune progression.
 */
export type ZoneShade =
  | { kind: 'empty' }
  | { kind: 'started'; pct: number }
  | { kind: 'theme'; tier: Tier }
  | { kind: 'total'; tier: Tier };

export function shadeOf(zone: ZoneConquest): ZoneShade {
  if (zone.allComplete) return { kind: 'total', tier: zone.overall.tier || 1 };
  if (zone.anyThemeComplete) {
    const best = zone.themes
      .filter((entry) => entry.state.complete)
      .reduce((top, entry) => Math.max(top, entry.state.tier || 1), 1 as number);
    return { kind: 'theme', tier: best as Tier };
  }
  if (zone.overall.visited > 0) return { kind: 'started', pct: zone.overall.pct };
  return { kind: 'empty' };
}
