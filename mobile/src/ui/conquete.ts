import { conquest } from '../theme';
import type { ZoneConquest } from '../lib/conquest';
import { shadeOf } from '../lib/conquest';

/**
 * Les couleurs de la carte de conquête, pour les deux plateformes.
 *
 * Une collection cochée est une liste ; un département colorié est un
 * territoire. Tout l'écart entre les deux tient dans ces quelques expressions.
 *
 * Elles existent en deux versions, comme les aplats de régions de la carte
 * principale, et pour la même raison : `feature-state` n'existe que dans la
 * version web de MapLibre. Le web s'en sert parce qu'il le peut — recolorier
 * cent un départements y coûte cent une paires clé-valeur, sans qu'aucune
 * géométrie ne reparte au moteur. Le natif pose la même question autrement,
 * en comparant le code de chaque polygone à une table.
 *
 * Le coût est le même dans les deux cas : ce qui change à chaque visite
 * validée est une propriété de peinture, jamais la géométrie.
 */

/** Opacité maximale d'un territoire entamé, avant d'avoir fini quoi que ce soit. */
export const STARTED_MAX_OPACITY = 0.55;

/** Opacité d'un territoire vierge : présent, mais en retrait. */
export const EMPTY_OPACITY = 0.45;

/** Opacité d'un territoire achevé — par thème ou en entier. */
export const DONE_OPACITY = 0.85;

/** L'opacité minimale d'un territoire entamé : un lieu validé doit se voir. */
const STARTED_MIN_OPACITY = 0.08;

export type Peint = { code: string; shade: string; pct: number };

/** Ce que la carte doit peindre, tiré des zones. */
export function aPeindre(zones: ZoneConquest[]): Peint[] {
  return zones.map((zone) => ({
    code: zone.area.code,
    shade: shadeOf(zone).kind,
    pct: zone.overall.pct,
  }));
}

/** La couleur d'une nuance. `started` emprunte celle du total, et pâlit. */
export function couleurDe(shade: string): string {
  if (shade === 'total') return conquest.total;
  if (shade === 'theme') return conquest.theme;
  if (shade === 'started') return conquest.total;
  return conquest.empty;
}

/**
 * L'opacité d'un territoire entamé, à proportion de ce qu'il reste.
 *
 * Sans ce dégradé la carte serait binaire et ne montrerait aucune progression
 * entre le premier lieu et le dernier.
 */
export function opaciteDe(shade: string, pct: number): number {
  if (shade === 'started') {
    const part = Math.max(0, Math.min(100, pct)) / 100;
    return STARTED_MIN_OPACITY + (STARTED_MAX_OPACITY - STARTED_MIN_OPACITY) * part;
  }
  if (shade === 'empty') return EMPTY_OPACITY;
  return DONE_OPACITY;
}

/** La nuance d'un territoire, lue dans son état. La version WEB. */
const NUANCE = ['coalesce', ['feature-state', 'shade'], 'empty'];

export function couleurDesTerritoires(): unknown[] {
  return [
    'match',
    NUANCE,
    'total',
    couleurDe('total'),
    'theme',
    couleurDe('theme'),
    'started',
    couleurDe('started'),
    couleurDe('empty'),
  ];
}

export function opaciteDesTerritoires(): unknown[] {
  return [
    'case',
    ['==', NUANCE, 'started'],
    [
      'interpolate',
      ['linear'],
      ['coalesce', ['feature-state', 'pct'], 0],
      0,
      STARTED_MIN_OPACITY,
      100,
      STARTED_MAX_OPACITY,
    ],
    ['==', NUANCE, 'empty'],
    EMPTY_OPACITY,
    DONE_OPACITY,
  ];
}

/**
 * Les mêmes, sans `feature-state` : la version NATIVE.
 *
 * Une table de correspondance sur le code du territoire. Cent une entrées pour
 * les départements, dix-huit pour les régions — c'est une expression courte,
 * et changer une couleur ne renvoie au moteur que cette expression.
 *
 * Le dégradé des territoires entamés est calculé ICI plutôt que confié à une
 * interpolation : le pourcentage est connu au moment où l'on écrit la table,
 * et une valeur toute faite se lit mieux qu'une interpolation imbriquée — la
 * même prudence que sur les aplats de régions, où une interpolation mal placée
 * fait refuser la couche en silence.
 */
export function couleurDesTerritoiresNative(peints: Peint[]): unknown[] | string {
  if (peints.length === 0) return couleurDe('empty');
  const table: unknown[] = ['match', ['get', 'code']];
  for (const { code, shade } of peints) table.push(code, couleurDe(shade));
  table.push(couleurDe('empty'));
  return table;
}

export function opaciteDesTerritoiresNative(peints: Peint[]): unknown[] | number {
  if (peints.length === 0) return EMPTY_OPACITY;
  const table: unknown[] = ['match', ['get', 'code']];
  for (const { code, shade, pct } of peints) table.push(code, opaciteDe(shade, pct));
  table.push(EMPTY_OPACITY);
  return table;
}
