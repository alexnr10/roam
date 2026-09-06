import { regionsPresentes, tuiles } from './grid';
import type { Place } from '../types';

function lieu(nom: string, extra: Partial<Place> = {}): Place {
  return {
    id: nom,
    slug: nom.toLowerCase(),
    name: nom,
    themeId: 'monuments',
    lat: 48,
    lon: 2,
    radiusM: 150,
    score: 100,
    departement: 'Paris',
    departementCode: '75',
    regionCode: '11',
    imageUrl: `https://commons.wikimedia.org/wiki/Special:FilePath/${nom}.jpg`,
    ...extra,
  } as Place;
}

const AUCUNE = new Set<string>();

describe('tuiles', () => {
  it('montre les plus connus en premier', () => {
    // Une vie de voyages en France est surtout faite de lieux célèbres :
    // c'est là qu'est le rendement du quadrillage.
    const lot = [lieu('Petit', { score: 40 }), lieu('Grand', { score: 200 })];
    expect(tuiles(lot, { mode: 'a-reconnaitre', visitedIds: AUCUNE }).map((p) => p.name))
      .toEqual(['Grand', 'Petit']);
  });

  it('renvoie les lieux sans photo à la fin, sans les cacher', () => {
    // Une tuile sans image ne se reconnaît pas, elle se lit — le geste qu'on
    // cherchait justement à éviter.
    const lot = [
      lieu('Sans photo', { score: 300, imageUrl: null }),
      lieu('Avec photo', { score: 50 }),
    ];
    expect(tuiles(lot, { mode: 'a-reconnaitre', visitedIds: AUCUNE }).map((p) => p.name))
      .toEqual(['Avec photo', 'Sans photo']);
  });

  it('écarte ce qui est déjà validé', () => {
    const lot = [lieu('Vu'), lieu('Pas vu')];
    const vus = new Set(['Vu']);
    expect(tuiles(lot, { mode: 'a-reconnaitre', visitedIds: vus }).map((p) => p.name))
      .toEqual(['Pas vu']);
  });

  it('sait aussi ne montrer que les validés, pour se dédire', () => {
    // Un doigt qui glisse coche un lieu où l'on n'est jamais allé : il faut
    // pouvoir revenir dessus, et le même écran doit servir.
    const lot = [lieu('Vu'), lieu('Pas vu')];
    expect(tuiles(lot, { mode: 'valides', visitedIds: new Set(['Vu']) }).map((p) => p.name))
      .toEqual(['Vu']);
  });

  it('filtre par région : on se souvient par territoire, pas par catégorie', () => {
    const lot = [lieu('Breton', { regionCode: '53' }), lieu('Parisien')];
    expect(
      tuiles(lot, { mode: 'a-reconnaitre', regionCode: '53', visitedIds: AUCUNE })
        .map((p) => p.name),
    ).toEqual(['Breton']);
  });

  it('départage deux lieux de même score par leur nom', () => {
    const lot = [lieu('Zèbre'), lieu('Alpha')];
    expect(tuiles(lot, { mode: 'a-reconnaitre', visitedIds: AUCUNE }).map((p) => p.name))
      .toEqual(['Alpha', 'Zèbre']);
  });

  it("ne modifie pas la liste qu'on lui donne", () => {
    // Le catalogue est un module partagé : le trier en place changerait
    // l'ordre de tous les autres écrans.
    const lot = [lieu('Petit', { score: 40 }), lieu('Grand', { score: 200 })];
    tuiles(lot, { mode: 'a-reconnaitre', visitedIds: AUCUNE });
    expect(lot.map((p) => p.name)).toEqual(['Petit', 'Grand']);
  });
});

describe('regionsPresentes', () => {
  it('ne propose que les régions où il y a quelque chose à reconnaître', () => {
    const noms = new Map([['11', 'Île-de-France'], ['53', 'Bretagne'], ['84', 'Auvergne']]);
    const lot = [lieu('A'), lieu('B', { regionCode: '53' }), lieu('C', { regionCode: '53' })];
    expect(regionsPresentes(lot, noms)).toEqual([
      { value: '53', label: 'Bretagne' },
      { value: '11', label: 'Île-de-France' },
    ]);
  });

  it("ignore un code que le répertoire ne nomme pas", () => {
    // Wikidata range parfois un lieu dans la nomenclature d'avant 2016 — la
    // Corse en « 92 ». Le filtre affichait une pastille « 92 », qui ne veut
    // rien dire pour personne.
    const noms = new Map([['11', 'Île-de-France']]);
    const lot = [lieu('A'), lieu('Corse', { regionCode: '92' })];
    expect(regionsPresentes(lot, noms)).toEqual([{ value: '11', label: 'Île-de-France' }]);
  });
});
