import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { AGENT, CONTACT, DENSITE_MAX, ENTETES, PALIERS, VERSION, palier, photoUrl, sourceDeLaPhoto } from './photo';

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

describe('densité', () => {
  it("demande l'image à la densité de l'écran, pas à la taille du cadre", () => {
    // Une photo demandée en POINTS est étirée d'autant de fois qu'il y a de
    // pixels par point : quatre cents pixels sur mille, c'est flou — et
    // l'application vend des images.
    expect(photoUrl(NUE, 380, 2.6)).toBe(`${NUE}?width=800`);
    expect(photoUrl(NUE, 380, 1)).toBe(`${NUE}?width=400`);
  });

  it('ne dépasse pas deux, quel que soit ce que dit le téléphone', () => {
    // Au-delà l'œil ne distingue plus grand-chose, et chaque palier double le
    // poids téléchargé — sur un forfait mobile, au bord d'une route.
    expect(photoUrl(NUE, 400, 4)).toBe(photoUrl(NUE, 400, DENSITE_MAX));
  });

  it("ne rétrécit jamais l'image sous la taille du cadre", () => {
    expect(photoUrl(NUE, 400, 0.5)).toBe(`${NUE}?width=400`);
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
    expect(PALIERS[PALIERS.length - 1]).toBe(1200);
  });
});

describe("l'agent utilisateur", () => {
  // Wikimedia refuse par un 403 — sans un mot d'explication — les clients qui
  // ne se nomment pas. Les vignettes manquaient sur le téléphone alors que le
  // web les montrait : un navigateur se nomme, le téléchargeur d'images
  // d'Android n'envoyait que celui de sa bibliothèque.

  it('donne un nom, une version et un contact', () => {
    // Les trois que la politique demande. Un agent qui dit seulement « Roam »
    // ne vaut pas mieux qu'un agent générique.
    expect(AGENT).toContain('Roam/');
    expect(AGENT).toContain(VERSION);
    expect(AGENT).toContain(CONTACT);
    expect(CONTACT).toMatch(/^https?:\/\//);
  });

  it("suit la version de l'application", () => {
    // Une version qui ment est pire qu'une version absente : elle envoie
    // Wikimedia chercher un défaut dans une livraison qui n'existe plus.
    const app = JSON.parse(
      readFileSync(join(__dirname, '..', '..', 'app.json'), 'utf8'),
    );
    expect(VERSION).toBe(app.expo.version);
  });

  it("s'envoie sous le nom que le protocole attend", () => {
    expect(ENTETES['User-Agent']).toBe(AGENT);
  });
});

describe('sourceDeLaPhoto', () => {
  // `<Image source={{ uri, headers }} />` PERD les en-têtes sur Android : dans
  // `Image.android.js`, ils ne sont extraits que d'une source en TABLEAU. Nos
  // requêtes partaient donc sous l'agent d'OkHttp, que Wikimedia refuse.

  it('enveloppe la source dans un tableau sur Android', () => {
    const source = sourceDeLaPhoto('https://exemple/x.jpg', true);
    expect(Array.isArray(source)).toBe(true);
    expect(source).toHaveLength(1);
  });

  it('la laisse en objet ailleurs', () => {
    // `react-native-web` teste `!Array.isArray(source)` : un tableau y
    // donnerait une image sans adresse. iOS lit les en-têtes dans l'objet.
    const source = sourceDeLaPhoto('https://exemple/x.jpg', false);
    expect(Array.isArray(source)).toBe(false);
  });

  it("porte l'agent dans les deux formes", () => {
    // C'est le seul point qui compte : quelle que soit la plateforme, la
    // requête doit se nommer.
    for (const android of [true, false]) {
      const source = sourceDeLaPhoto('https://exemple/x.jpg', android);
      const premier = Array.isArray(source) ? source[0] : source;
      expect(premier.uri).toBe('https://exemple/x.jpg');
      expect(premier.headers).toEqual(ENTETES);
      expect(premier.headers['User-Agent']).toBe(AGENT);
    }
  });
});
