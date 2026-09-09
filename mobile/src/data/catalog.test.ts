import { chargerCatalogue, areas, collections, getPlace, nomDuPays, places, paysCourant } from './catalog';
import { etoilesDe } from '../lib/etoiles';
import { nomDeRegion, regionDuDepartement } from '../lib/regions';
import contoursFrancais from './outlines.json';
import { chargerContours, niveauxDessinables, outlinesFor } from './outlines';
import type { Catalog } from '../types';

/**
 * Changer de pays change TOUT ce qui se déduit du catalogue.
 *
 * Le piège n'est pas le remplacement lui-même, c'est ce que les modules ont
 * dérivé une fois pour toutes au chargement : les étoiles, les noms de région,
 * la table des départements. Sans reconstruction, on obtiendrait une carte
 * italienne notée à la française — le pire des cas, parce qu'il ne plante pas.
 */

const francais = JSON.parse(JSON.stringify({
  places: places.slice(0, 3),
  collections: collections.slice(0, 5),
  themes: [],
  areas: { country: areas.country, region: areas.region, departement: areas.departement, commune: [] },
})) as Catalog;

const italien: Catalog = {
  places: [
    {
      id: 'Q10285', name: 'Colisée', themeId: 'monuments',
      lat: 41.89, lon: 12.49, radiusM: 150,
      departement: 'Rome', regionCode: 'IT62', communeName: 'Rome',
    } as unknown as Catalog['places'][number],
  ],
  collections: [
    {
      slug: 'theme-monuments-it', name: 'Monuments', kind: 'theme',
      themeId: 'monuments', geoLevel: null, geoCode: null, placeCount: 1,
      tierCounts: {}, places: [{ placeId: 'Q10285', tier: 1, rank: 1 }],
    } as unknown as Catalog['collections'][number],
  ],
  themes: [],
  areas: {
    country: [{ code: 'IT', name: 'Italie', deForm: "d'Italie" }],
    region: [{ code: 'IT62', name: 'Latium', deForm: 'du Latium' }],
    departement: [{ code: 'RM', name: 'Rome', deForm: 'de Rome', parentCode: 'IT62' }],
    commune: [],
  },
} as unknown as Catalog;

describe('changer de catalogue', () => {
  afterEach(() => chargerCatalogue(francais));

  it('remplace les lieux et le pays', () => {
    expect(paysCourant()).toBe('FR');
    chargerCatalogue(italien);
    expect(paysCourant()).toBe('IT');
    expect(nomDuPays()).toBe('Italie');
    expect(getPlace('Q10285')?.name).toBe('Colisée');
  });

  it('refait les étoiles, qui sont dérivées des collections', () => {
    // LE défaut à éviter : un lieu italien noté à une étoile parce que la
    // table des notes est restée celle de la France, où il n'existe pas.
    chargerCatalogue(italien);
    expect(etoilesDe('Q10285')).toBe(3);
  });

  it('refait les noms de région et la table des départements', () => {
    chargerCatalogue(italien);
    expect(nomDeRegion('IT62')).toBe('Latium');
    expect(regionDuDepartement('RM')).toBe('IT62');
  });

  it('rend le catalogue précédent quand on y revient', () => {
    const avant = places.length;
    chargerCatalogue(italien);
    expect(places).toHaveLength(1);
    chargerCatalogue(francais);
    expect(places).toHaveLength(avant);
    expect(paysCourant()).toBe('FR');
  });

  it("ne connaît plus les lieux du pays qu'on a quitté", () => {
    const unFrancais = francais.places[0].id;
    chargerCatalogue(italien);
    expect(getPlace(unFrancais)).toBeUndefined();
  });
});

describe('les contours suivent le pays', () => {
  afterEach(() => {
    chargerContours(contoursFrancais);
    chargerCatalogue(francais);
  });

  it('un pays sans contours retombe sur la liste, sans planter', () => {
    // Ouvrir un pays avant d'avoir tracé ses frontières doit rester possible :
    // la carte de conquête dit alors la même chose sans dessin.
    chargerContours(null);
    chargerCatalogue(italien);
    expect(outlinesFor('region')).toBeNull();
    expect(niveauxDessinables()).toEqual([]);
  });

  it('les échelles dessinables sont RECALCULÉES, pas figées au démarrage', () => {
    // C'était une constante de module : elle serait restée celle du pays de
    // départ, et la carte aurait proposé de colorier des départements qui
    // n'existent pas.
    expect(niveauxDessinables().length).toBeGreaterThan(0);
    chargerContours(null);
    expect(niveauxDessinables()).toEqual([]);
    chargerContours(contoursFrancais);
    expect(niveauxDessinables().length).toBeGreaterThan(0);
  });

  it('rend ses contours au pays quand on y revient', () => {
    chargerContours(null);
    chargerCatalogue(italien);
    chargerContours(contoursFrancais);
    chargerCatalogue(francais);
    expect(outlinesFor('region')).not.toBeNull();
    expect(nomDeRegion('84')).not.toBe('84');
  });
});
