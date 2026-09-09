/**
 * Les icônes de thèmes, en images, pour la carte native.
 *
 * Le web dessine les vingt-trois glyphes sur un canevas au démarrage
 * (`src/ui/glyphes.ts`) : il a `document`, `Path2D` et `addImage`. Le natif n'a
 * rien de tout cela — MapLibre y réclame de vraies images, déclarées avant que
 * la couche de symboles ne soit posée.
 *
 * Plutôt que de redessiner les icônes à la main dans un format d'image, on
 * repasse EXACTEMENT le même code de dessin — mêmes tracés, même grille de 24,
 * même épaisseur, même couleur — dans un navigateur sans écran, et on écrit le
 * résultat en PNG. `src/ui/themeIcons.tsx` reste donc la seule source : ajouter
 * un thème, c'est ajouter son tracé là-bas et relancer ce script.
 *
 *     node scripts/build-glyphes.mjs
 *
 * Les images produites sont VERSIONNÉES : les rebâtir demande un Chromium, et
 * personne ne devrait avoir à en installer un pour compiler l'application.
 */
import { createRequire } from 'node:module';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const racine = join(here, '..');
const sortie = join(racine, 'assets', 'glyphes');

/** Le côté du glyphe, en POINTS. Identique à `COTE` dans `src/ui/glyphes.ts`. */
const COTE = 22;

/**
 * Les densités produites, et pourquoi il en faut plusieurs.
 *
 * React Native lit la densité dans le NOM du fichier : `x.png` vaut un pixel
 * par point, `x@2x.png` deux, `x@3x.png` trois. Il choisit ensuite celui qui
 * convient à l'écran et transmet l'échelle à MapLibre, qui en déduit la taille
 * du symbole.
 *
 * N'écrire que `x.png` à 44 pixels revient donc à déclarer un symbole de
 * quarante-quatre POINTS : sur la carte, les glyphes des lieux trois étoiles
 * débordaient largement de leur pastille — deux fois trop grands, exactement.
 * La taille demandée par `tailleDesGlyphes()` est la même des deux côtés ;
 * c'est l'échelle déclarée qui manquait.
 */
const DENSITES = [1, 2, 3];

/**
 * Les tracés, lus dans le module TypeScript.
 *
 * Lus, et non importés : ce script tourne sous Node, `themeIcons.tsx` importe
 * `react-native-svg`. La table est un littéral plat — vingt-trois clés, des
 * tableaux de chaînes — et l'extraire par accolades équilibrées coûte moins
 * qu'une chaîne de compilation entière pour une constante.
 */
function lireLesTraces() {
  const source = readFileSync(join(racine, 'src', 'ui', 'themeIcons.tsx'), 'utf8');
  const debut = source.indexOf('export const TRACES');
  if (debut < 0) throw new Error('TRACES introuvable dans themeIcons.tsx');
  const ouvrante = source.indexOf('{', debut);
  let profondeur = 0;
  let fin = ouvrante;
  for (; fin < source.length; fin += 1) {
    if (source[fin] === '{') profondeur += 1;
    else if (source[fin] === '}') {
      profondeur -= 1;
      if (profondeur === 0) break;
    }
  }
  const litteral = source.slice(ouvrante, fin + 1);
  return new Function(`return ${litteral};`)();
}

const traces = lireLesTraces();
const themes = Object.keys(traces);

/**
 * La couleur du glyphe.
 *
 * Le sable du fond, comme sur le web : le disque porte la note par sa couleur,
 * le symbole se lit en clair par-dessus. `colors.bg` du thème de l'app.
 */
const ENCRE = (() => {
  const theme = readFileSync(join(racine, 'src', 'theme.ts'), 'utf8');
  const trouve = theme.match(/\bbg:\s*'(#[0-9A-Fa-f]{3,8})'/);
  if (!trouve) throw new Error('couleur `bg` introuvable dans theme.ts');
  return trouve[1];
})();

const page = `<!doctype html><meta charset="utf-8"><body style="margin:0">
<script>
const TRACES = ${JSON.stringify(traces)};
const COTE = ${COTE}, DENSITES = ${JSON.stringify(DENSITES)}, ENCRE = ${JSON.stringify(ENCRE)};
// Le dessin de \`src/ui/glyphes.ts\`, au trait près.
window.rendre = () => {
  const sorties = {};
  for (const [themeId, chemins] of Object.entries(TRACES)) {
    sorties[themeId] = {};
    for (const densite of DENSITES) {
      const cote = Math.round(COTE * densite);
      const canevas = document.createElement('canvas');
      canevas.width = cote;
      canevas.height = cote;
      const ctx = canevas.getContext('2d');
      ctx.scale(cote / 24, cote / 24);
      ctx.strokeStyle = ENCRE;
      ctx.lineWidth = 2.4;
      ctx.lineCap = 'round';
      ctx.lineJoin = 'round';
      for (const chemin of chemins) ctx.stroke(new Path2D(chemin));
      sorties[themeId][densite] = canevas.toDataURL('image/png');
    }
  }
  return sorties;
};
</script></body>`;

// `createRequire` plutôt qu'un `import` : Playwright n'est pas une dépendance
// de l'application — elle ne sert qu'ici — et la résolution CommonJS sait
// aussi la trouver dans une installation globale.
const { chromium } = createRequire(import.meta.url)('playwright');
const navigateur = await chromium.launch();
const onglet = await navigateur.newPage();
await onglet.setContent(page);
const images = await onglet.evaluate(() => window.rendre());
await navigateur.close();

mkdirSync(sortie, { recursive: true });
for (const themeId of themes) {
  for (const densite of DENSITES) {
    const donnees = images[themeId]?.[densite];
    if (!donnees) throw new Error(`glyphe manquant : ${themeId} @${densite}x`);
    // `x.png`, `x@2x.png`, `x@3x.png` : c'est le nom qui porte l'échelle.
    const suffixe = densite === 1 ? '' : `@${densite}x`;
    writeFileSync(
      join(sortie, `${themeId}${suffixe}.png`),
      Buffer.from(donnees.slice('data:image/png;base64,'.length), 'base64'),
    );
  }
}

/**
 * La table d'images, écrite en TypeScript.
 *
 * `require` d'un chemin littéral : Metro résout les ressources à la
 * compilation, un chemin construit à l'exécution ne lui dit rien. La table doit
 * donc être écrite, pas calculée — et l'écrire à la main serait vingt-trois
 * lignes à retoucher chaque fois qu'un thème bouge.
 */
const table = [
  '// Fichier ENGENDRÉ par `node scripts/build-glyphes.mjs` — ne pas modifier à la main.',
  '//',
  '// Les vingt-trois icônes de thèmes, en images, pour la couche de symboles de',
  '// la carte native. Leur source est `src/ui/themeIcons.tsx` : c\'est là qu\'on',
  '// modifie un tracé, et ce script réécrit ce fichier et les PNG voisins.',
  '//',
  '// Le `require` ne nomme QUE la densité de base : React Native choisit',
  '// lui-même le fichier `@2x` ou `@3x` selon l\'écran, et transmet l\'échelle',
  '// à MapLibre — sans quoi un bitmap de 44 pixels passe pour 44 points, et le',
  '// symbole déborde de sa pastille.',
  '',
  'import type { ImageRequireSource } from \'react-native\';',
  '',
  'export const GLYPHES: Record<string, ImageRequireSource> = {',
  ...themes.map((id) => `  '${id}': require('../../assets/glyphes/${id}.png'),`),
  '};',
  '',
].join('\n');
writeFileSync(join(racine, 'src', 'ui', 'glyphesNatifs.ts'), table);

console.log(
  `${themes.length} glyphes écrits dans assets/glyphes/, en ${DENSITES.join('x, ')}x`,
);
