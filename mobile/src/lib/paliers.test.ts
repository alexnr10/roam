import { readFileSync, readdirSync, statSync } from 'fs';
import { join } from 'path';

import { PALIERS, palierMinuscule } from './paliers';

describe('PALIERS', () => {
  it('nomme les trois paliers, sans les numéroter', () => {
    expect(Object.keys(PALIERS).sort()).toEqual(['1', '2', '3']);
    for (const nom of Object.values(PALIERS)) {
      expect(nom).not.toMatch(/\d/);
      expect(nom.length).toBeGreaterThan(6);
    }
    expect(new Set(Object.values(PALIERS)).size).toBe(3);
  });

  it('donne une minuscule utilisable dans une phrase', () => {
    expect(palierMinuscule(2)).toBe('la deuxième ligne');
  });
});

/**
 * Le garde-fou : une seule échelle chiffrée à l'écran, et c'est l'étoile.
 *
 * Sur la fiche de la maison du docteur Gachet on lisait « une étoile » sous le
 * titre et « niveau 3 dans cette collection » vingt lignes plus bas. Deux
 * barèmes pour une seule idée, et le lecteur ne sait plus lequel croire.
 */
describe('le vocabulaire des écrans', () => {
  const racine = join(__dirname, '..', '..');

  const fichiers = (dossier: string): string[] =>
    readdirSync(dossier).flatMap((entree) => {
      const chemin = join(dossier, entree);
      if (statSync(chemin).isDirectory()) return fichiers(chemin);
      return chemin.endsWith('.tsx') ? [chemin] : [];
    });

  /** Le texte affiché, commentaires retirés. */
  const sansCommentaires = (source: string): string =>
    source.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');

  it('n’écrit plus « niveau » nulle part, ni « N2 »', () => {
    const fautifs: string[] = [];
    for (const chemin of [...fichiers(join(racine, 'app')), ...fichiers(join(racine, 'src'))]) {
      if (chemin.endsWith('.test.tsx')) continue;
      const texte = sansCommentaires(readFileSync(chemin, 'utf8'));
      if (/[Nn]iveaux?\s*[\d{]/.test(texte) || /\bN\{?\d/.test(texte)) {
        fautifs.push(chemin.slice(racine.length + 1));
      }
    }
    expect(fautifs).toEqual([]);
  });
});
