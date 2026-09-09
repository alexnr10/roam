import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

/**
 * Les glyphes sur le disque, et l'échelle que porte leur NOM.
 *
 * React Native lit la densité dans le nom du fichier : `x.png` vaut un pixel
 * par point, `x@2x.png` deux. Il transmet cette échelle à MapLibre, qui en
 * déduit la taille du symbole sur la carte.
 *
 * Les glyphes n'étaient d'abord écrits qu'en `x.png`, à quarante-quatre
 * pixels : MapLibre les a donc pris pour quarante-quatre POINTS, et les
 * symboles des lieux trois étoiles débordaient de leur pastille — deux fois
 * trop grands, exactement. Rien dans le code ne le disait : la taille demandée
 * était la bonne des deux côtés, seule l'échelle déclarée manquait.
 *
 * Ce test lit les images produites plutôt que le script qui les produit : ce
 * qui compte est ce que Metro trouvera, pas ce qu'on a voulu écrire.
 */

const DOSSIER = join(__dirname, '..', '..', 'assets', 'glyphes');

/**
 * Les thèmes, lus dans la table engendrée.
 *
 * Pas `import { TRACES } from './themeIcons'` : ce module tire
 * `react-native-svg`, que les tests — qui tournent sous Node, sans moteur de
 * rendu — ne savent pas charger. On lit donc `glyphesNatifs.ts`, c'est-à-dire
 * exactement ce que Metro trouvera, et le script vérifie déjà qu'il couvre
 * tous les tracés.
 */
const themes = (() => {
  const source = readFileSync(join(__dirname, 'glyphesNatifs.ts'), 'utf8');
  return [...source.matchAll(/^\s*'([a-z0-9-]+)':/gm)].map((m) => m[1]);
})();

/** Le côté attendu à la densité 1, en points. */
const COTE = 22;

/** Les dimensions d'un PNG, lues dans son en-tête IHDR. */
function dimensions(chemin: string): { largeur: number; hauteur: number } {
  const octets = readFileSync(chemin);
  return {
    largeur: octets.readUInt32BE(16),
    hauteur: octets.readUInt32BE(20),
  };
}

describe('les glyphes de la carte native', () => {
  it('couvre les vingt-trois thèmes', () => {
    expect(themes.length).toBe(23);
  });

  for (const densite of [1, 2, 3]) {
    const suffixe = densite === 1 ? '' : `@${densite}x`;

    it(`existe en ${densite}x, au côté que son nom annonce`, () => {
      const fautes: string[] = [];
      for (const themeId of themes) {
        const chemin = join(DOSSIER, `${themeId}${suffixe}.png`);
        if (!existsSync(chemin)) {
          fautes.push(`${themeId}${suffixe} manquant`);
          continue;
        }
        const { largeur, hauteur } = dimensions(chemin);
        const attendu = COTE * densite;
        if (largeur !== attendu || hauteur !== attendu) {
          fautes.push(`${themeId}${suffixe} fait ${largeur}×${hauteur}, attendu ${attendu}`);
        }
      }
      expect(fautes).toEqual([]);
    });
  }
});
