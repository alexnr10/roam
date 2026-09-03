import { MIN_CARACTERES, fold, pertinence, search } from './search';
import type { Place } from '../types';

function lieu(name: string, extra: Partial<Place> = {}): Place {
  return {
    id: `Q${name.length}${name.charCodeAt(0)}${extra.communeName ?? ''}`,
    slug: name,
    name,
    themeId: 'chateaux',
    lat: 45,
    lon: 2,
    radiusM: 150,
    score: 50,
    ...extra,
  } as Place;
}

describe('normalisation', () => {
  it('ignore les accents et la casse', () => {
    // On tape « chateau » sur un clavier de téléphone, pas « Château ».
    expect(fold('Château de Sagonne')).toBe('chateau de sagonne');
    expect(fold('Vézère')).toBe('vezere');
  });
});

describe('pertinence', () => {
  it('classe le début du texte avant le début d’un mot, avant le milieu', () => {
    expect(pertinence('Gordes', 'gordes')).toBe(4);
    expect(pertinence('Gordes-le-Haut', 'gordes')).toBe(3);
    expect(pertinence('Château de Gordes', 'gordes')).toBe(2);
    expect(pertinence('Regordes', 'gordes')).toBe(1);
    expect(pertinence('Carcassonne', 'gordes')).toBe(0);
  });

  it('ne répond pas à une recherche vide', () => {
    expect(pertinence('Gordes', '   ')).toBe(0);
  });
});

describe('recherche', () => {
  it('attend deux caractères avant de répondre', () => {
    expect(search([lieu('Gordes')], 'g')).toEqual([]);
    expect(search([lieu('Gordes')], 'go')).toHaveLength(1);
    expect(MIN_CARACTERES).toBe(2);
  });

  it('trouve un lieu par sa COMMUNE quand son nom ne dit rien', () => {
    // Le vrai cas : les falaises d'Étretat sont fichées « Porte d'Aval ».
    // Chercher sur le seul nom ne rendait rien.
    const trouves = search([lieu("Porte d'Aval", { communeName: 'Étretat' })], 'etretat');
    expect(trouves).toHaveLength(1);
    expect(trouves[0].par).toBe('lieu');
  });

  it('fait passer le nom avant la commune', () => {
    // Qui tape « gordes » cherche le village, pas les lieux qui s'y trouvent.
    const village = lieu('Gordes', { communeName: 'Gordes' });
    const dedans = lieu('Abbaye de Sénanque', { communeName: 'Gordes', score: 900 });
    const trouves = search([dedans, village], 'gordes');
    expect(trouves[0].place.name).toBe('Gordes');
    expect(trouves[0].par).toBe('nom');
  });

  it('départage par la notoriété à pertinence égale', () => {
    const petit = lieu('Château de Vaux', { score: 10 });
    const grand = lieu('Château de Chambord', { score: 200 });
    const trouves = search([petit, grand], 'chateau');
    expect(trouves[0].place.name).toBe('Château de Chambord');
  });

  it('trouve aussi par département', () => {
    const trouves = search([lieu('Pointe du Raz', { departement: 'Finistère' })], 'finistere');
    expect(trouves[0].par).toBe('lieu');
  });

  it('ne rend rien quand rien ne correspond', () => {
    expect(search([lieu('Gordes')], 'zzz')).toEqual([]);
  });

  it('borne le nombre de résultats', () => {
    const beaucoup = Array.from({ length: 100 }, (_, i) => lieu(`Château ${i}`));
    expect(search(beaucoup, 'chateau', 10)).toHaveLength(10);
  });

  it('supporte un lieu sans commune ni département', () => {
    // Trente-neuf lieux du catalogue n'ont pas de commune.
    expect(search([lieu('Mont Blanc')], 'mont')).toHaveLength(1);
  });
});
