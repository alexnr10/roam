import { CHEMIN_DU_WORKER, racineDuSite, voisinDuSite } from './site';

/**
 * Sans worker, MapLibre ne traite AUCUNE donnée et la carte reste muette :
 * pas de lieux, pas de territoires, et aucune erreur pour le dire. C'est la
 * panne la plus coûteuse de l'écran, parce qu'elle ne ressemble pas à une
 * panne — et il suffit de servir le site ailleurs qu'à la racine d'un domaine
 * pour la déclencher. C'est arrivé au premier essai sur GitHub Pages.
 */

const BUNDLE = (base: string) => `${base}_expo/static/js/web/entry-abc123.js`;

describe('racineDuSite', () => {
  it('rend la racine du domaine quand le site y est servi', () => {
    expect(racineDuSite([BUNDLE('https://exemple.fr/')], 'x')).toBe('https://exemple.fr/');
  });

  it('rend le préfixe quand le site vit dans un sous-chemin', () => {
    // Le cas de GitHub Pages sur un dépôt de projet.
    expect(racineDuSite([BUNDLE('https://compte.github.io/roam/')], 'x')).toBe(
      'https://compte.github.io/roam/',
    );
  });

  it('ne se laisse pas tromper par une route profonde', () => {
    // Un hébergeur statique rend `index.html` pour `/roam/place/Q243` : la
    // page est profonde, le bundle non. Se fier à l'adresse de la PAGE ferait
    // chercher le worker dans `/roam/place/`.
    expect(
      racineDuSite(
        [BUNDLE('https://compte.github.io/roam/')],
        'https://compte.github.io/roam/place/Q243',
      ),
    ).toBe('https://compte.github.io/roam/');
  });

  it('ignore les scripts étrangers', () => {
    expect(
      racineDuSite(
        ['https://cdn.ailleurs.net/analytics.js', BUNDLE('https://compte.github.io/roam/')],
        'x',
      ),
    ).toBe('https://compte.github.io/roam/');
  });

  it('retombe sur le repli quand le bundle est introuvable', () => {
    // Une page repliée en un seul fichier n'a pas de script séparé ; elle
    // fournit alors l'adresse du worker elle-même.
    expect(racineDuSite([], 'https://exemple.fr/')).toBe('https://exemple.fr/');
  });
});

describe('voisinDuSite', () => {
  it('compose l’adresse du worker sous un préfixe', () => {
    expect(
      voisinDuSite(CHEMIN_DU_WORKER, [BUNDLE('https://compte.github.io/roam/')], 'x'),
    ).toBe('https://compte.github.io/roam/maplibre/maplibre-gl-worker.mjs');
  });

  it('n’ajoute pas de préfixe quand il n’y en a pas', () => {
    expect(voisinDuSite(CHEMIN_DU_WORKER, [BUNDLE('https://exemple.fr/')], 'x')).toBe(
      'https://exemple.fr/maplibre/maplibre-gl-worker.mjs',
    );
  });

  it('ne fabrique jamais une adresse absurde', () => {
    // Un repli qui n'est pas une adresse ferait lever `new URL`.
    expect(voisinDuSite(CHEMIN_DU_WORKER, [], 'pas une adresse')).toBe(
      `/${CHEMIN_DU_WORKER}`,
    );
  });
});
