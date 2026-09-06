import { aDessiner, bandeau, dansLeCadre, type Cadre } from './carte';
import type { Place } from '../types';

function lieu(nom: string, lat: number, lon: number, score = 100): Place {
  return {
    id: nom, slug: nom, name: nom, themeId: 'monuments',
    lat, lon, radiusM: 150, score,
    departement: null, departementCode: null, regionCode: null,
  } as unknown as Place;
}

const FRANCE: Cadre = { ouest: -5, sud: 41, est: 10, nord: 51 };

describe('dansLeCadre', () => {
  it('garde ce qui est dedans et écarte ce qui est dehors', () => {
    expect(dansLeCadre(lieu('Paris', 48.85, 2.35), FRANCE)).toBe(true);
    expect(dansLeCadre(lieu('Berlin', 52.5, 13.4), FRANCE)).toBe(false);
  });
});

describe('aDessiner', () => {
  it('ne dessine que le cadre : un point hors écran ne coûte rien', () => {
    const lot = [lieu('Paris', 48.85, 2.35), lieu('Berlin', 52.5, 13.4)];
    expect(aDessiner(lot, FRANCE, 100).map((p) => p.name)).toEqual(['Paris']);
  });

  it('garde les mieux classés quand le cadre en contient trop', () => {
    // Un guide qui montre tout ne recommande rien.
    const lot = [
      lieu('Obscur', 48, 2, 10),
      lieu('Fameux', 48, 2, 200),
      lieu('Moyen', 48, 2, 100),
    ];
    expect(aDessiner(lot, FRANCE, 2).map((p) => p.name)).toEqual(['Fameux', 'Moyen']);
  });

  it("ne trie pas quand il n'y a pas de quoi plafonner", () => {
    // Sans plafond à appliquer, l'ordre d'entrée est conservé : c'est celui
    // que la couche de rendu attend, et trier pour rien coûte à chaque image.
    const lot = [lieu('A', 48, 2, 10), lieu('B', 48, 2, 200)];
    expect(aDessiner(lot, FRANCE, 10).map((p) => p.name)).toEqual(['A', 'B']);
  });

  it('sans cadre, montre tout : la carte ne sait pas encore où elle est', () => {
    const lot = [lieu('Paris', 48.85, 2.35), lieu('Berlin', 52.5, 13.4)];
    expect(aDessiner(lot, null, 100)).toHaveLength(2);
  });

  it("ne modifie pas la liste qu'on lui donne", () => {
    const lot = [lieu('A', 48, 2, 10), lieu('B', 48, 2, 200)];
    aDessiner(lot, FRANCE, 1);
    expect(lot.map((p) => p.name)).toEqual(['A', 'B']);
  });
});

describe('bandeau', () => {
  it('met le plus proche en tête quand on sait où est le lecteur', () => {
    const lot = [lieu('Loin', 43.3, 5.4), lieu('Près', 48.86, 2.34)];
    const position = { latitude: 48.85, longitude: 2.35 };
    expect(bandeau(lot, position, 2).map((p) => p.name)).toEqual(['Près', 'Loin']);
  });

  it('sans position, met le mieux classé en tête', () => {
    // Un guide ouvert au hasard doit tomber sur ce qui vaut le détour.
    const lot = [lieu('Obscur', 48, 2, 10), lieu('Fameux', 48, 2, 200)];
    expect(bandeau(lot, null, 2).map((p) => p.name)).toEqual(['Fameux', 'Obscur']);
  });

  it('mesure une vraie distance : Paris–Lyon fait environ 390 km', () => {
    const lot = [lieu('Lyon', 45.76, 4.84)];
    // On le vérifie par l'ordre, seule chose que le bandeau expose.
    const proche = [...lot, lieu('Versailles', 48.8, 2.13)];
    expect(bandeau(proche, { latitude: 48.85, longitude: 2.35 }, 1)[0].name)
      .toBe('Versailles');
  });
});
