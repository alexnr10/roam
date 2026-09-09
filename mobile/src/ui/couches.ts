import { colors } from '../theme';
import {
  ETOILE_COULEURS,
  OUT_OF_SCOPE_VEIL,
  REGION_LINES,
  TRANSITION,
  mapColors,
  opaciteDesAplats,
  opaciteDesAplatsNative,
  opaciteDesPastilles,
  opaciteDesTraits,
  rayonDesPastilles,
  tailleDesGlyphes,
  tonsDesRegions,
} from './mapStyle';

/**
 * Les couches de la carte, une fois pour les deux plateformes.
 *
 * Elles étaient écrites deux fois — une fois en appels impératifs sur le web,
 * une fois en JSX sur le natif — et deux copies d'une même chose finissent
 * toujours par diverger. Ici, elles ont divergé en silence : la couche
 * `place-highlight` posait son rayon en `["+", rayonDesPastilles(), 4]`, ce qui
 * enferme `["zoom"]` dans une addition. Le format de style l'interdit, MapLibre
 * refuse alors la couche par un ÉVÉNEMENT plutôt que par une exception —
 * l'anneau du lieu qu'on touche n'a jamais existé, et rien ne le disait.
 *
 * Une table plate est aussi ce qu'on peut VALIDER : les tests la passent au
 * validateur du format de style, celui-là même qui refusait cette couche.
 *
 * L'ordre est celui du dessin, du fond vers le doigt.
 */

export const SOURCE_LIEUX = 'places';
export const SOURCE_REGIONS = 'regions';
export const SOURCE_DEPTS = 'departements';
export const SOURCE_VOILE = 'voile';

export type Couche = {
  id: string;
  type: 'fill' | 'line' | 'circle' | 'symbol';
  source: string;
  filter?: unknown[];
  layout?: Record<string, unknown>;
  paint: Record<string, unknown>;
};

export type EtatDeLaCarte = {
  /**
   * Le natif ne connaît pas `feature-state`, et anime par TRANSITIONS.
   *
   * Deux limites du SDK, pas deux choix : la question « est-ce la région
   * ouverte ? » se pose alors dans l'expression, et les fondus sont confiés au
   * moteur plutôt qu'écrits image par image depuis JavaScript.
   */
  natif: boolean;
  /** La région ouverte. Le web la tient aussi par `feature-state`. */
  ouverte?: string | null;
  /** Le lieu mis en avant : celui qu'on touche, ou qu'on propose de valider. */
  misEnAvant?: string | null;
  /** Les départements à tracer : ceux de la région ouverte, et eux seuls. */
  departements?: string[];
  /** Le fond apporte-t-il ses polices ? Sans elles, pas de noms de départements. */
  avecPolices?: boolean;
  /** Ce qu'il reste des AUTRES régions pendant le vol. */
  attenuation?: number;
};

/** Le fondu d'une propriété de peinture, côté natif seulement. */
function transition(natif: boolean, duree: number): Record<string, unknown> {
  return natif ? { duration: duree, delay: 0 } : {};
}

export function couchesDeLaCarte({
  natif,
  ouverte = null,
  misEnAvant = null,
  departements = [],
  avecPolices = true,
  attenuation = 1,
}: EtatDeLaCarte): Couche[] {
  const opacite = opaciteDesPastilles(misEnAvant);
  const fondu = transition(natif, TRANSITION.lieux.apparition);
  const couches: Couche[] = [];

  // ── 1. Le voile hors-France ────────────────────────────────────────────
  // Le monde percé de la France. En dérivant vers l'Atlantique ou l'océan
  // Indien, des trous nets apparaissent dans le sable : c'est ainsi qu'on
  // découvre la Guadeloupe et Mayotte.
  couches.push({
    id: 'voile',
    type: 'fill',
    source: SOURCE_VOILE,
    paint: {
      'fill-color': OUT_OF_SCOPE_VEIL.color,
      'fill-opacity': opaciteDesTraits(OUT_OF_SCOPE_VEIL.opacity),
    },
  });

  // ── 2. L'ombre des régions ─────────────────────────────────────────────
  // MapLibre ne sait faire ni ombre portée, ni filtre, ni mode de fusion sur un
  // polygone. Une seconde couche de contour, large, translucide et décalée est
  // le seul moyen — et il suffit.
  couches.push({
    id: 'region-ombre',
    type: 'line',
    source: SOURCE_REGIONS,
    paint: {
      'line-color': REGION_LINES.shadow,
      'line-width': REGION_LINES.shadowWidth,
      'line-opacity': opaciteDesTraits(REGION_LINES.shadowOpacity),
      'line-translate': REGION_LINES.shadowOffset,
    },
  });

  // ── 3. Les aplats ──────────────────────────────────────────────────────
  // C'est ici que tient toute l'identité : l'opacité suit le zoom, et le voile
  // de la région ouverte tombe à 0,14 — la vraie carte apparaît, avec ses
  // routes et ses villes, au moment exact où on en a besoin.
  couches.push({
    id: 'region-aplat',
    type: 'fill',
    source: SOURCE_REGIONS,
    paint: {
      'fill-color': natif
        ? tonsDesRegions()
        : [
            'case',
            ['boolean', ['feature-state', 'hover'], false],
            REGION_LINES.hover,
            tonsDesRegions(),
          ],
      'fill-opacity': natif
        ? opaciteDesAplatsNative(ouverte, attenuation)
        : opaciteDesAplats(attenuation),
      'fill-opacity-transition': transition(natif, TRANSITION.autresRegions.duree),
    },
  });

  // ── 4. Les coutures entre régions ──────────────────────────────────────
  couches.push({
    id: 'region-couture',
    type: 'line',
    source: SOURCE_REGIONS,
    paint: {
      'line-color': REGION_LINES.seam,
      'line-width': REGION_LINES.seamWidth,
      'line-opacity': opaciteDesTraits(),
    },
  });

  // ── 5. Les coutures de départements ────────────────────────────────────
  // Elles ne sont pas un étage de navigation : un deuxième geste obligatoire
  // ajouterait un palier avant de voir un lieu. Elles ne servent que de repère
  // DANS une région ouverte — « du côté du Gard ».
  couches.push({
    id: 'departement-couture',
    type: 'line',
    source: SOURCE_DEPTS,
    filter: ['in', ['get', 'code'], ['literal', departements]],
    paint: {
      'line-color': REGION_LINES.shadow,
      'line-opacity': opaciteDesTraits(0.5),
      'line-width': 1.1,
      'line-dasharray': [4, 4],
    },
  });

  // ── 6. Le contour de la région ouverte ─────────────────────────────────
  couches.push({
    id: 'region-choisie',
    type: 'line',
    source: SOURCE_REGIONS,
    filter: ['==', ['get', 'code'], ouverte ?? '__aucune__'],
    paint: {
      'line-color': REGION_LINES.chosen,
      'line-width': REGION_LINES.chosenWidth,
      'line-opacity': opaciteDesTraits(),
    },
  });

  // ── 7. Les lieux ───────────────────────────────────────────────────────
  // Un niveau, une couleur, une taille — repris partout : carte, listes,
  // badges. Aucun chiffre, aucun regroupement. Le disque porte la NOTE, le
  // symbole posé dessus porte la CATÉGORIE : deux choses à dire, deux moyens
  // de les dire, au lieu d'une taille de rond qui devait tout faire.
  couches.push({
    id: 'place',
    type: 'circle',
    source: SOURCE_LIEUX,
    paint: {
      'circle-color': [
        'match',
        ['get', 'tier'],
        1,
        ETOILE_COULEURS[3],
        2,
        ETOILE_COULEURS[2],
        ETOILE_COULEURS[1],
      ],
      'circle-opacity': opacite,
      'circle-opacity-transition': fondu,
      'circle-radius': rayonDesPastilles(),
      // Un lieu validé change de CONTOUR, pas de remplissage. Le repeindre en
      // vert ajoutait une quatrième couleur à une carte qui en portait déjà
      // trois, et faisait perdre au passage ce que le lieu vaut.
      'circle-stroke-width': [
        'case',
        ['==', ['get', 'visited'], 1],
        2.6,
        ['<=', ['get', 'tier'], 2],
        1.6,
        0,
      ],
      'circle-stroke-color': [
        'case',
        ['==', ['get', 'visited'], 1],
        mapColors.visited,
        mapColors.halo,
      ],
      // Le CONTOUR aussi, sans quoi le fondu laisse voir des anneaux vides :
      // `circle-stroke-opacity` est une propriété à part, et elle vaut un par
      // défaut. Les pastilles arrivaient en cerceaux avant de se remplir.
      'circle-stroke-opacity': opacite,
      'circle-stroke-opacity-transition': fondu,
    },
  });

  // Le lieu mis en avant : un ANNEAU autour de sa pastille, pas un disque
  // par-dessus. Un disque plein recouvrait le symbole du thème — toucher un
  // lieu trois étoiles lui faisait perdre son icône au moment précis où on le
  // regardait.
  couches.push({
    id: 'place-highlight',
    type: 'circle',
    source: SOURCE_LIEUX,
    filter: ['==', ['get', 'id'], misEnAvant ?? '__none__'],
    paint: {
      'circle-opacity': 0,
      'circle-radius': rayonDesPastilles(4),
      'circle-stroke-width': 2.4,
      'circle-stroke-color': colors.primary,
    },
  });

  // Le symbole du thème, en clair sur le disque. Seule la première note en
  // porte un : mille deux cent soixante-neuf lieux à une étoile, tous surmontés
  // d'un symbole, feraient une carte illisible — et le symbole devient ainsi
  // une distinction, pas seulement une étiquette.
  couches.push({
    id: 'place-glyphe',
    type: 'symbol',
    source: SOURCE_LIEUX,
    filter: ['==', ['get', 'tier'], 1],
    layout: {
      'icon-image': ['concat', 'theme-', ['get', 'themeId']],
      'icon-size': tailleDesGlyphes(),
      // Jamais masqué par collision : deux lieux voisins doivent tous deux
      // garder leur pastille, sinon la carte ment sur ce qu'il y a.
      'icon-allow-overlap': true,
      'icon-ignore-placement': true,
    },
    paint: {
      'icon-opacity': opacite,
      'icon-opacity-transition': fondu,
    },
  });

  // ── Les noms de départements ───────────────────────────────────────────
  // Un repère, pas une couche d'information : MapLibre en masque lui-même la
  // plupart par collision, et c'est très bien ainsi. Absents quand le fond
  // n'apporte pas ses polices — le style de secours hors réseau n'en a pas, et
  // une couche de texte sans police est refusée en silence.
  if (avecPolices) {
    couches.push({
      id: 'departement-nom',
      type: 'symbol',
      source: SOURCE_DEPTS,
      filter: ['in', ['get', 'code'], ['literal', departements]],
      layout: {
        'text-field': ['get', 'nom'],
        'text-font': ['Noto Sans Regular'],
        'text-size': 13,
      },
      paint: {
        'text-color': '#5A4A38',
        'text-opacity': 0.85,
        'text-halo-color': mapColors.labelHalo,
        'text-halo-width': 1.4,
      },
    });
  }

  return couches;
}

/** Les couches d'une source, dans l'ordre du dessin. */
export const couchesDe = (source: string, etat: EtatDeLaCarte): Couche[] =>
  couchesDeLaCarte(etat).filter((couche) => couche.source === source);
