import fs from 'node:fs';
import path from 'node:path';

import { fusionner } from './rechercheMondiale';
import type { Place } from '../types';

const lieu = (name: string, score = 0): Place =>
  ({ id: name, slug: name, name, themeId: 'monuments', lat: 0, lon: 0, score } as unknown as Place);

const FR = {
  code: 'FR',
  name: 'France',
  places: [lieu('Pont du Gard', 200), lieu('Colis', 10)],
};
const IT = {
  code: 'IT',
  name: 'Italie',
  places: [lieu('Colisée', 300), lieu('Ponte Vecchio', 150)],
};

describe('fusionner', () => {
  it('trouve un lieu italien depuis la France', () => {
    // La demande, en une ligne : personne ne se dit « je vais d’abord passer
    // en Italie, puis chercher le Colisée ». On tape, et il vient.
    const trouves = fusionner('colisée', 'FR', [FR, IT]);
    expect(trouves.map((r) => r.place.name)).toContain('Colisée');
    expect(trouves.find((r) => r.place.name === 'Colisée')?.pays).toBe('IT');
    expect(trouves.find((r) => r.place.name === 'Colisée')?.nomDuPays).toBe('Italie');
  });

  it('garde le pays courant DEVANT, même moins bien noté', () => {
    // On cherche neuf fois sur dix là où l’on est. « Pont du Gard » vaut 200,
    // « Ponte Vecchio » 150 — mais même si l’ordre était inverse, le français
    // resterait en tête tant qu’on regarde la France.
    const depuisLaFrance = fusionner('pont', 'FR', [FR, IT]);
    expect(depuisLaFrance[0].place.name).toBe('Pont du Gard');
    // Et l’inverse est vrai depuis l’Italie : c’est le pays REGARDÉ qui mène,
    // pas un pays privilégié en dur.
    const depuisLItalie = fusionner('pont', 'IT', [FR, IT]);
    expect(depuisLItalie[0].place.name).toBe('Ponte Vecchio');
  });

  it('rend le pays de chaque ligne, pour que l’écran puisse le dire', () => {
    const trouves = fusionner('pont', 'FR', [FR, IT]);
    expect(trouves.map((r) => [r.place.name, r.pays])).toEqual([
      ['Pont du Gard', 'FR'],
      ['Ponte Vecchio', 'IT'],
    ]);
  });

  it('se contente du pays courant quand les autres ne sont pas là', () => {
    // Sans réseau, aucun autre catalogue n’est en mémoire : la recherche doit
    // rendre ce qu’elle a toujours rendu, sans erreur ni attente.
    expect(fusionner('pont', 'FR', [FR]).map((r) => r.place.name)).toEqual(['Pont du Gard']);
  });

  it('ne cherche rien en dessous du minimum de caractères', () => {
    expect(fusionner('p', 'FR', [FR, IT])).toEqual([]);
    expect(fusionner('  ', 'FR', [FR, IT])).toEqual([]);
  });

  it('borne le nombre de résultats, pays confondus', () => {
    const beaucoup = {
      code: 'IT',
      name: 'Italie',
      places: Array.from({ length: 50 }, (_, i) => lieu(`Ponte ${i}`)),
    };
    expect(fusionner('pont', 'FR', [FR, beaucoup], 10)).toHaveLength(10);
  });
});

/**
 * L'épreuve sur les VRAIS catalogues, et pas sur quatre lieux inventés.
 *
 * Ce qui est éprouvé ici est la seule chose qui puisse casser sans qu'un test
 * unitaire le voie : que les noms réels du catalogue italien répondent aux
 * mots qu'un francophone tape. Le TÉLÉCHARGEMENT, lui, n'est pas éprouvé —
 * c'est le mécanisme déjà en place pour franchir une frontière, et le
 * navigateur de ce conteneur n'a pas d'accès sortant.
 */
describe('sur les catalogues publiés', () => {
  const racine = path.join(__dirname, '..', '..', '..');
  const chemins = {
    FR: path.join(racine, 'mobile', 'src', 'data', 'catalog.json'),
    IT: path.join(racine, 'catalogues', 'it.json'),
  };
  // La branche `v0.1-france` retire le catalogue italien à dessein.
  const epreuve = Object.values(chemins).every((c) => fs.existsSync(c)) ? it : it.skip;

  const charger = () =>
    (['FR', 'IT'] as const).map((code) => ({
      code,
      name: code === 'FR' ? 'France' : 'Italie',
      places: JSON.parse(fs.readFileSync(chemins[code], 'utf8')).places as Place[],
    }));

  epreuve('« colisée » tapé en France rend le Colisée, en Italie', () => {
    const trouves = fusionner('colisée', 'FR', charger());
    const colisee = trouves.find((r) => r.place.name === 'Colisée');
    expect(colisee).toBeDefined();
    expect(colisee!.pays).toBe('IT');
  });

  epreuve('un mot générique français atteint les noms restés italiens', () => {
    const catalogues = charger();
    const noms = (q: string) =>
      fusionner(q, 'FR', catalogues, 400)
        .filter((r) => r.pays === 'IT')
        .map((r) => r.place.name);
    // Chacun de ces noms est au catalogue tel quel, en italien.
    expect(noms('place')).toContain('Piazza dei Miracoli');
    expect(noms('mont')).toContain('Monte Argentario');
    expect(noms('ile')).toContain('Isola del Giglio');
  });

  epreuve('ne dérange pas la recherche française', () => {
    // Le garde-fou, sur les vraies données : ce qu'on cherchait en France
    // arrive toujours en tête, pays courant d'abord.
    const trouves = fusionner('pont du gard', 'FR', charger());
    expect(trouves[0].place.name).toBe('Pont du Gard');
    expect(trouves[0].pays).toBe('FR');
  });
});
