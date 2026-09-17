import { chargerCatalogue, collections, places } from '../data/catalog';
import catalogueFrancais from '../data/catalog.json';
import { MENTIONS, etoilesDe, repartition } from './etoiles';

describe('etoilesDe', () => {
  it('donne une note à CHAQUE lieu du catalogue', () => {
    const sans = places.filter((place) => ![1, 2, 3].includes(etoilesDe(place.id)));
    expect(sans).toEqual([]);
  });

  it('suit la relecture, pas le score brut', () => {
    // La Porte d'Aval, à Étretat, est onzième sur quatorze par le score et
    // niveau 1 dans la collection : c'est la relecture à la main qui l'a mise
    // là. Une note tirée du score seul lui aurait donné une étoile — et
    // c'est précisément ce qu'une note ne doit pas faire.
    const porteDAval = places.find((place) => place.name === "Porte d'Aval");
    expect(porteDAval).toBeDefined();
    const memeTheme = places.filter((place) => place.themeId === porteDAval!.themeId);
    const parScore = [...memeTheme].sort((a, b) => b.score - a.score);
    expect(parScore.indexOf(porteDAval!)).toBeGreaterThan(6);
    expect(etoilesDe(porteDAval!.id)).toBe(3);
  });

  it('reprend le niveau de la collection nationale du thème', () => {
    const nationale = collections.find(
      (collection) => collection.kind === 'theme' && !collection.geoCode,
    )!;
    for (const membre of nationale.places) {
      expect([membre.tier, etoilesDe(membre.placeId)]).toEqual([membre.tier, 4 - membre.tier]);
    }
  });

  it('donne une étoile à ce qui est hors de la collection nationale', () => {
    const nationales = new Set(
      collections
        .filter((collection) => collection.kind === 'theme' && !collection.geoCode)
        .flatMap((collection) => collection.places.map((membre) => membre.placeId)),
    );
    const dehors = places.filter((place) => !nationales.has(place.id));
    expect(dehors.length).toBeGreaterThan(0);
    for (const place of dehors) expect(etoilesDe(place.id)).toBe(1);
  });

  it('garde la répartition que le pipeline vise : une dizaine, puis un quart', () => {
    // Dix places au premier niveau et vingt-cinq au second par collection : la
    // note nationale hérite de ce budget, et la pyramide reste une pyramide.
    const compte = repartition(places.map((place) => place.id));
    const total = places.length;
    expect(compte[3] / total).toBeGreaterThan(0.08);
    expect(compte[3] / total).toBeLessThan(0.16);
    expect(compte[2] / total).toBeGreaterThan(0.2);
    expect(compte[2] / total).toBeLessThan(0.32);
    expect(compte[1]).toBeGreaterThan(compte[2] + compte[3]);
  });

  it('donne une mention à chaque note', () => {
    expect(Object.keys(MENTIONS).sort()).toEqual(['1', '2', '3']);
    for (const mention of Object.values(MENTIONS)) expect(mention.length).toBeGreaterThan(5);
  });

  it('classe les châteaux entre eux, pas contre Versailles', () => {
    // Une cascade ne peut pas perdre contre un château : le point de
    // comparaison est la catégorie.
    const cascades = places.filter((place) => place.themeId === 'cascades');
    expect(cascades.some((place) => etoilesDe(place.id) === 3)).toBe(true);
  });
});


/**
 * Un pays trop petit pour avoir des collections de thème.
 *
 * Un thème n'en a une qu'à partir de huit lieux. Le Vatican compte dix-neuf
 * lieux en tout, et son thème le plus fourni en garde cinq : aucune collection
 * de thème, donc aucun barème — ses dix-neuf lieux tombaient tous sur le défaut
 * d'une étoile, la basilique Saint-Pierre comprise.
 */
describe('un pays sans collection de thème', () => {
  const vatican = {
    places: [
      { id: 'Q12512', name: 'Basilique Saint-Pierre', themeId: 'cathedrales', lat: 0, lon: 0, score: 188 },
      { id: 'Q2943', name: 'Chapelle Sixtine', themeId: 'cathedrales', lat: 0, lon: 0, score: 138 },
      { id: 'Q3671583', name: 'Église San Pellegrino', themeId: 'cathedrales', lat: 0, lon: 0, score: 60 },
    ],
    collections: [
      {
        slug: 'geo-country-va',
        name: 'Le meilleur du Vatican',
        kind: 'geo',
        geoLevel: 'country',
        geoCode: 'VA',
        places: [
          { placeId: 'Q12512', rank: 1, tier: 1 },
          { placeId: 'Q2943', rank: 2, tier: 2 },
          { placeId: 'Q3671583', rank: 3, tier: 3 },
        ],
      },
    ],
    themes: [],
    areas: { region: [], departement: [], commune: [], country: [{ code: 'VA', name: 'Vatican' }] },
  };

  afterAll(() => chargerCatalogue(catalogueFrancais as never));

  it('note sur la collection du PAYS, faute de mieux', () => {
    chargerCatalogue(vatican as never);
    expect(collections.filter((c) => c.kind === 'theme')).toHaveLength(0);
    expect(etoilesDe('Q12512')).toBe(3);
    expect(etoilesDe('Q2943')).toBe(2);
    expect(etoilesDe('Q3671583')).toBe(1);
  });

  it('ne s’en sert PAS là où des thèmes existent', () => {
    // La France a ses vingt-trois collections de thème : la collection du pays
    // ne doit rien y changer, sinon les quatre-vingts lieux du « Meilleur de
    // France » gagneraient des étoiles que leur thème leur refuse.
    chargerCatalogue(catalogueFrancais as never);
    const meilleurDeFrance = collections.find((c) => c.slug === 'geo-country-fr');
    expect(meilleurDeFrance).toBeDefined();
    const dernier = meilleurDeFrance!.places.find((m) => m.tier === 3);
    expect(dernier).toBeDefined();
    // Son thème peut très bien ne lui donner qu'une étoile, et c'est lui qui
    // décide : la note ne vient pas de la collection géographique.
    const parTheme = collections
      .filter((c) => c.kind === 'theme' && !c.geoCode)
      .flatMap((c) => c.places)
      .filter((m) => m.placeId === dernier!.placeId);
    const attendue = parTheme.length ? Math.max(...parTheme.map((m) => 4 - m.tier)) : 1;
    expect(etoilesDe(dernier!.placeId)).toBe(attendue);
  });
});
