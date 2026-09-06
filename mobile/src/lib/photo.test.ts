import { PALIERS, palier, photoUrl } from './photo';

const NUE =
  'https://commons.wikimedia.org/wiki/Special:FilePath/Tour%20Eiffel.jpg';

describe('photoUrl', () => {
  it('demande la largeur à Commons', () => {
    expect(photoUrl(NUE, 200)).toBe(`${NUE}?width=200`);
  });

  it("force le HTTPS : Wikidata donne l'adresse en http", () => {
    // Servie depuis une page en HTTPS, l'image manquerait sans rien dire.
    expect(photoUrl(NUE.replace('https', 'http'), 200)).toBe(`${NUE}?width=200`);
  });

  it('ajoute la largeur à une adresse qui a déjà un paramètre', () => {
    expect(photoUrl(`${NUE}?page=1`, 400)).toBe(`${NUE}?page=1&width=400`);
  });

  it("rend null quand le lieu n'a pas de photo", () => {
    // Vingt-trois lieux du catalogue sont dans ce cas.
    expect(photoUrl(null, 400)).toBeNull();
    expect(photoUrl(undefined, 400)).toBeNull();
    expect(photoUrl('', 400)).toBeNull();
  });
});

describe('palier', () => {
  it('arrondit au palier supérieur, jamais en dessous', () => {
    // Une image plus petite que son cadre est floue ; c'est le seul sens où
    // l'arrondi se voit.
    expect(palier(56)).toBe(200);
    expect(palier(200)).toBe(200);
    expect(palier(201)).toBe(400);
  });

  it('ne dépasse pas le plus grand palier', () => {
    // Sinon un écran très dense ferait fabriquer à Commons une taille unique,
    // rien qu'à lui.
    expect(palier(4000)).toBe(PALIERS[PALIERS.length - 1]);
  });
});
