import { validateStyleMin } from '@maplibre/maplibre-gl-style-spec';

import {
  type EtatDeLaCarte,
  SOURCE_DEPTS,
  SOURCE_LIEUX,
  SOURCE_REGIONS,
  SOURCE_VOILE,
  couchesDeLaCarte,
} from './couches';

/**
 * Les couches passées au VALIDATEUR du format de style.
 *
 * C'est le même code que celui qui tourne dans MapLibre, et c'est lui qui
 * refusait `place-highlight` : son rayon posait `["+", rayonDesPastilles(), 4]`,
 * ce qui enferme `["zoom"]` dans une addition. MapLibre refuse alors la couche
 * par un ÉVÉNEMENT, jamais par une exception — la couche manquait, l'anneau du
 * lieu touché n'existait pas, et rien dans l'application ne le disait. Il a
 * fallu ouvrir la console d'un navigateur sans écran pour le voir.
 *
 * Le voir ici coûte une seconde, et le voir sur un téléphone coûte une
 * compilation native.
 */

/** Un style minimal, nos couches posées sur des sources vides. */
function styleAvec(couches: ReturnType<typeof couchesDeLaCarte>) {
  const vide = {
    type: 'geojson' as const,
    data: { type: 'FeatureCollection' as const, features: [] },
  };
  return {
    version: 8 as const,
    // Les polices : sans elles, le validateur refuse `text-field` — et il a
    // raison, c'est exactement la panne qu'on évite en amont.
    glyphs: 'https://exemple.invalid/{fontstack}/{range}.pbf',
    sources: {
      [SOURCE_LIEUX]: vide,
      [SOURCE_REGIONS]: vide,
      [SOURCE_DEPTS]: vide,
      [SOURCE_VOILE]: vide,
    },
    layers: couches,
  };
}

const CAS: [string, EtatDeLaCarte][] = [
  ['web, rien d’ouvert', { natif: false }],
  ['web, une région ouverte', { natif: false, ouverte: '53', misEnAvant: 'Q243', departements: ['22', '29'], attenuation: 0.55 }],
  ['natif, rien d’ouvert', { natif: true }],
  ['natif, une région ouverte', { natif: true, ouverte: '53', misEnAvant: 'Q243', departements: ['22', '29'], attenuation: 0.55 }],
  ['natif, fond sans polices', { natif: true, avecPolices: false }],
];

describe('couchesDeLaCarte', () => {
  for (const [nom, etat] of CAS) {
    it(`est acceptée par le format de style — ${nom}`, () => {
      const erreurs = validateStyleMin(styleAvec(couchesDeLaCarte({ ...etat })) as never);
      expect(erreurs.map((e) => `${e.message}`)).toEqual([]);
    });
  }

  it('dessine du fond vers le doigt', () => {
    // L'ordre est le dessin : un lieu posé sous l'aplat de sa région serait
    // invisible, et un aplat posé sur les lieux les rendrait intouchables.
    const ids = couchesDeLaCarte({ natif: true }).map((couche) => couche.id);
    expect(ids).toEqual([
      'voile',
      'region-ombre',
      'region-aplat',
      'region-couture',
      'departement-couture',
      'region-choisie',
      'place',
      'place-highlight',
      'place-glyphe',
      'departement-nom',
    ]);
  });

  it('donne les mêmes couches aux deux plateformes', () => {
    // Les deux cartes doivent rester la même carte. Ce qui diffère est nommé
    // — `feature-state`, les transitions — et rien d'autre ne doit s'y glisser.
    const web = couchesDeLaCarte({ natif: false }).map((c) => c.id);
    const natif = couchesDeLaCarte({ natif: true }).map((c) => c.id);
    expect(natif).toEqual(web);
  });

  it('ne pose `feature-state` que sur le web', () => {
    // Les SDK d'Android et d'iOS ne le connaissent pas : une couche qui s'en
    // sert y est refusée, en silence comme toujours.
    expect(JSON.stringify(couchesDeLaCarte({ natif: true }))).not.toContain('feature-state');
    expect(JSON.stringify(couchesDeLaCarte({ natif: false }))).toContain('feature-state');
  });

  it('ne confie ses fondus au moteur que sur le natif', () => {
    // Le web anime en réécrivant une propriété de peinture image par image, ce
    // qu'il fait bien ; sur le natif chaque écriture traverserait le pont.
    const natif = couchesDeLaCarte({ natif: true }).find((c) => c.id === 'place');
    const web = couchesDeLaCarte({ natif: false }).find((c) => c.id === 'place');
    expect(natif?.paint['circle-opacity-transition']).toMatchObject({ duration: expect.any(Number) });
    expect(web?.paint['circle-opacity-transition']).toEqual({});
  });

  it('retire les noms de départements quand le fond n’a pas de polices', () => {
    const ids = couchesDeLaCarte({ natif: true, avecPolices: false }).map((c) => c.id);
    expect(ids).not.toContain('departement-nom');
  });

  it('n’enferme jamais `zoom` ailleurs qu’en entrée d’une interpolation', () => {
    // La règle qui a coûté `place-highlight`, vérifiée sur TOUTES les couches
    // plutôt que sur celle dont on se souvient.
    const fautes: string[] = [];
    const parcourir = (valeur: unknown, chemin: string, sousInterpolation: boolean) => {
      if (!Array.isArray(valeur)) return;
      if (valeur[0] === 'zoom' && valeur.length === 1) {
        if (!sousInterpolation) fautes.push(chemin);
        return;
      }
      const entree = valeur[0] === 'interpolate' || valeur[0] === 'step';
      valeur.forEach((element, index) =>
        parcourir(element, `${chemin}/${index}`, entree && index <= 2),
      );
    };
    for (const couche of couchesDeLaCarte({ natif: true, ouverte: '53', misEnAvant: 'Q243' })) {
      parcourir(couche.paint, `${couche.id}.paint`, false);
      parcourir(couche.layout ?? {}, `${couche.id}.layout`, false);
    }
    expect(fautes).toEqual([]);
  });
});
