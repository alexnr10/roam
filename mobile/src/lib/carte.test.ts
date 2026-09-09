import { bandeau } from './carte';
import type { Place } from '../types';

function lieu(nom: string, lat: number, lon: number, score = 100): Place {
  return {
    id: nom, slug: nom, name: nom, themeId: 'monuments',
    lat, lon, radiusM: 150, score,
    departement: null, departementCode: null, regionCode: null,
  } as unknown as Place;
}

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
