import fs from 'node:fs';
import path from 'node:path';

import { enBoite, enclavesDansLeCadre, lieuxMarques, notesDe, seTouchent } from './enclaves';
import { dansLaRegion } from './regions';
import type { PaysConnu } from './pays';
import type { Catalog } from '../types';

const ITALIE: PaysConnu = {
  code: 'IT',
  name: 'Italie',
  // Deux provinces, comme dans l'index servi : Rome et Milan.
  emprises: [[11.7, 41.3, 13.3, 42.3], [8.7, 45.2, 9.5, 45.7]],
};
const VATICAN: PaysConnu = {
  code: 'VA',
  name: 'Vatican',
  emprises: [[12.4483, 41.9019, 12.4575, 41.9064]],
};
const FRANCE: PaysConnu = { code: 'FR', name: 'France', emprises: [[-5, 42, 8, 51]] };

describe('enclavesDansLeCadre', () => {
  it('pose le Vatican quand il est dans le cadre', () => {
    // Un cadre de dix kilomètres autour du centre de Rome.
    expect(enclavesDansLeCadre([12.40, 41.86, 12.52, 41.95], 'IT', [ITALIE, VATICAN, FRANCE]))
      .toEqual(['VA']);
  });

  it('ne le pose pas quand on regarde ailleurs en Italie', () => {
    // Milan : même pays, même enclave connue, mais elle n'est pas à l'écran.
    expect(enclavesDansLeCadre([9.1, 45.4, 9.3, 45.6], 'IT', [ITALIE, VATICAN, FRANCE]))
      .toEqual([]);
  });

  it('ne pose JAMAIS un voisin qui déborde', () => {
    // La France n'est pas une enclave de l'Italie : même cadrée sur les Alpes,
    // elle n'a rien à faire sur la carte italienne. C'est la même définition
    // que pour la bascule de pays — l'emprise tient dans une boîte, ou non.
    expect(enclavesDansLeCadre([6.0, 44.0, 8.0, 46.0], 'IT', [ITALIE, VATICAN, FRANCE]))
      .toEqual([]);
  });

  it('ne dit rien sans cadre ni pays connu', () => {
    expect(enclavesDansLeCadre(null, 'IT', [ITALIE, VATICAN])).toEqual([]);
    expect(enclavesDansLeCadre([12.4, 41.8, 12.5, 41.95], 'ZZ', [ITALIE, VATICAN])).toEqual([]);
  });

  it('ne se pose pas sur son propre pays', () => {
    expect(enclavesDansLeCadre([12.4, 41.8, 12.5, 41.95], 'VA', [ITALIE, VATICAN])).toEqual([]);
  });
});

describe('seTouchent', () => {
  it('reconnaît deux boîtes qui se chevauchent, et deux qui s’évitent', () => {
    expect(seTouchent([0, 0, 2, 2], [1, 1, 3, 3])).toBe(true);
    expect(seTouchent([0, 0, 2, 2], [3, 3, 4, 4])).toBe(false);
  });

  it('lit un cadre de carte sans le retourner', () => {
    expect(enBoite([[1, 2], [3, 4]])).toEqual([1, 2, 3, 4]);
  });
});

describe('les lieux marqués', () => {
  const catalogue = {
    places: [
      { id: 'Q12512', name: 'Basilique Saint-Pierre', regionCode: null },
      { id: 'Q3671583', name: 'Église San Pellegrino', regionCode: null },
    ],
    collections: [
      {
        slug: 'geo-country-va', name: 'Le meilleur du Vatican', kind: 'geo',
        geoLevel: 'country', geoCode: 'VA',
        places: [
          { placeId: 'Q12512', rank: 1, tier: 1 },
          { placeId: 'Q3671583', rank: 2, tier: 3 },
        ],
      },
    ],
  } as unknown as Catalog;

  it('portent leur pays et leur note, qui ne se calcule pas ici', () => {
    const lieux = lieuxMarques('VA', catalogue);
    expect(lieux.map((l) => [l.id, l.paysDOrigine, l.etoiles])).toEqual([
      ['Q12512', 'VA', 3],
      ['Q3671583', 'VA', 1],
    ]);
  });

  it('passent le filtre par région, quelle qu’elle soit', () => {
    // Ils ne sont d'AUCUNE région d'ici : s'ils sont sur la carte, c'est
    // parce qu'ils sont dans le cadre.
    const [saintPierre] = lieuxMarques('VA', catalogue);
    expect(dansLaRegion(saintPierre, '12')).toBe(true);
    expect(dansLaRegion({ regionCode: null }, '12')).toBe(false);
  });

  it('note sur les thèmes dès qu’il y en a', () => {
    const avecThemes = {
      ...catalogue,
      collections: [
        ...catalogue.collections,
        { slug: 'theme-cathedrales', kind: 'theme', geoCode: null,
          places: [{ placeId: 'Q3671583', rank: 1, tier: 1 }] },
      ],
    } as unknown as Catalog;
    const notes = notesDe(avecThemes);
    // Le thème décide, et la collection du pays ne s'en mêle plus.
    expect(notes.get('Q3671583')).toBe(3);
    expect(notes.get('Q12512')).toBeUndefined();
  });
});

describe('sur les catalogues publiés', () => {
  const racine = path.join(__dirname, '..', '..', '..');
  const chemins = [
    path.join(racine, 'catalogues', 'va.json'),
    path.join(racine, 'catalogues', 'index.json'),
  ];
  const epreuve = chemins.every((c) => fs.existsSync(c)) ? it : it.skip;

  epreuve('le Vatican servi se pose sur Rome, avec ses vraies étoiles', () => {
    const index = JSON.parse(fs.readFileSync(chemins[1], 'utf8'));
    const connus: PaysConnu[] = index.pays.map(
      (p: PaysConnu) => ({ code: p.code, name: p.name, emprises: p.emprises }),
    );
    // Le cadre d'un écran de téléphone zoomé sur le centre de Rome.
    const cadre = enBoite([[12.42, 41.87], [12.52, 41.93]]);
    expect(enclavesDansLeCadre(cadre, 'IT', connus)).toEqual(['VA']);

    const va = JSON.parse(fs.readFileSync(chemins[0], 'utf8')) as Catalog;
    const lieux = lieuxMarques('VA', va);
    expect(lieux).toHaveLength(19);
    expect(lieux.every((l) => l.paysDOrigine === 'VA')).toBe(true);
    const saintPierre = lieux.find((l) => l.id === 'Q12512');
    expect(saintPierre?.etoiles).toBe(3);
  });
});
