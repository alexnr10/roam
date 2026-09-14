import { BASE, PAYS, PAYS_EMBARQUE, PaysInconnu, REFERENCE_PAR_DEFAUT, catalogueDe, dejaCharge, deposer, lireIndex, obtenir, referenceServie } from './catalogues';
import type { Catalog } from '../types';

const vide = { places: [], collections: [], themes: [], areas: {} } as unknown as Catalog;

describe('catalogues par pays', () => {
  it('embarque celui du pays de départ, disponible sans réseau', () => {
    expect(dejaCharge(PAYS_EMBARQUE)).toBe(true);
    expect(catalogueDe(PAYS_EMBARQUE)?.places.length).toBeGreaterThan(0);
  });

  it('rend un catalogue déjà en main SANS aucune requête', async () => {
    // C'est toute la différence entre « changer de pays » et « attendre » :
    // revenir en France après un détour par l'Italie doit être instantané.
    const jamais = () => { throw new Error('le réseau ne devait pas être appelé'); };
    const rendu = await obtenir(PAYS_EMBARQUE, jamais as unknown as typeof fetch);
    expect(rendu.places.length).toBeGreaterThan(0);
  });

  it('refuse un pays dont on ne sait pas où il est', async () => {
    await expect(obtenir('XX')).rejects.toBeInstanceOf(PaysInconnu);
  });

  it('télécharge un pays annoncé, puis ne le redemande plus', async () => {
    PAYS.push({ code: 'IT', name: 'Italie', emprises: [], fichier: 'it.json' });
    let appels = 0;
    const faux = async () => {
      appels += 1;
      return { ok: true, json: async () => vide } as unknown as Response;
    };
    await obtenir('IT', faux as unknown as typeof fetch);
    await obtenir('IT', faux as unknown as typeof fetch);
    expect(appels).toBe(1);
    PAYS.pop();
  });

  it("dit ce qui ne va pas quand le serveur refuse", async () => {
    PAYS.push({ code: 'ZZ', name: 'Zzz', emprises: [], fichier: 'zz.json' });
    const casse = async () => ({ ok: false, status: 404 } as unknown as Response);
    await expect(obtenir('ZZ', casse as unknown as typeof fetch)).rejects.toThrow('404');
    PAYS.pop();
  });

  it('accepte un catalogue déposé par un autre chemin', () => {
    deposer('YY', vide);
    expect(dejaCharge('YY')).toBe(true);
  });
});

describe("l'index du dépôt", () => {
  it('donne au pays embarqué son emprise, sans lui reprendre son catalogue', async () => {
    // Sans emprise, la carte ne saurait pas qu'on vient de SORTIR de France.
    // Et retélécharger un catalogue déjà embarqué serait deux mégaoctets pour
    // rien.
    const index = {
      pays: [{ code: PAYS_EMBARQUE, name: 'France', fichier: 'fr.json', lieux: 2081,
               emprises: [[-5, 42, 8, 51]] }],
    };
    const faux = async () => ({ ok: true, json: async () => index } as unknown as Response);
    const liste = await lireIndex(faux as unknown as typeof fetch);
    const france = liste.find((p) => p.code === PAYS_EMBARQUE);
    expect(france?.emprises).toHaveLength(1);
    expect(catalogueDe(PAYS_EMBARQUE)?.places.length).toBeGreaterThan(100);
  });

  it("annonce les pays qu'on n'a pas", async () => {
    const index = { pays: [{ code: 'IT', name: 'Italie', fichier: 'it.json', emprises: [[6, 36, 19, 47]] }] };
    const faux = async () => ({ ok: true, json: async () => index } as unknown as Response);
    const liste = await lireIndex(faux as unknown as typeof fetch);
    expect(liste.some((p) => p.code === 'IT')).toBe(true);
    // Retiré pour ne pas déteindre sur les autres cas.
    PAYS.splice(PAYS.findIndex((p) => p.code === 'IT'), 1);
  });

  it("se tait quand le réseau manque : le pays embarqué suffit", async () => {
    // Un message d'erreur au démarrage, pour une fonction dont on ne se sert
    // peut-être pas, serait pire que le manque.
    const casse = async () => { throw new Error('hors ligne'); };
    await expect(lireIndex(casse as unknown as typeof fetch)).resolves.toBeDefined();
  });
});

describe('la référence servie', () => {
  /**
   * Une version donnée à quelqu'un ne doit pas changer sous ses pieds.
   *
   * Les catalogues sont relus à chaque démarrage — c'est voulu, corriger le
   * catalogue ne demande pas de recompiler. Mais en lisant `main`, une version
   * publiée verrait apparaître un pays le jour où on l'y pousse : quelqu'un à
   * qui on a confié « la version France » ferait glisser la carte vers Menton
   * et trouverait l'Italie.
   */

  it('retombe sur `main` quand la configuration ne dit rien', () => {
    // C'est le cas des tests, qui tournent sans application autour — et celui
    // du développement, où lire la branche de travail est le bon défaut.
    expect(referenceServie()).toBe(REFERENCE_PAR_DEFAUT);
  });

  it('construit une adresse brute du dépôt', () => {
    expect(BASE).toBe(
      `https://raw.githubusercontent.com/alexnr10/roam/${referenceServie()}/catalogues`,
    );
  });

  it('accepte une étiquette aussi bien qu’une branche', () => {
    // `raw.githubusercontent.com` sert un tag exactement comme une branche :
    // c'est ce qui permet de figer les catalogues d'une version publiée.
    const gele = `https://raw.githubusercontent.com/alexnr10/roam/v0.1-france/catalogues`;
    expect(gele).toContain('/v0.1-france/');
  });

  it('préfère la variable inlinée dans le bundle', () => {
    // LA correction qui manquait. La configuration Expo suffit à une
    // application NATIVE, qui embarque son manifeste — pas à un site statique,
    // dont l'`index.html` n'en porte aucun. La version publiée retombait donc
    // silencieusement sur `main`, et aurait vu apparaître un deuxième pays le
    // jour où on l'y pousse : exactement ce que ce mécanisme empêche.
    const avant = process.env.EXPO_PUBLIC_ROAM_CATALOGUES;
    try {
      process.env.EXPO_PUBLIC_ROAM_CATALOGUES = 'v9-publiee';
      jest.isolateModules(() => {
        jest.doMock(
          'expo-constants',
          () => ({ default: { expoConfig: { extra: { catalogues: 'autre-chose' } } } }),
          { virtual: true },
        );
        // La variable inlinée l'emporte sur le manifeste : c'est elle qui vaut
        // sur les deux plateformes.
        expect(require('./catalogues').referenceServie()).toBe('v9-publiee');
      });
    } finally {
      if (avant === undefined) delete process.env.EXPO_PUBLIC_ROAM_CATALOGUES;
      else process.env.EXPO_PUBLIC_ROAM_CATALOGUES = avant;
    }
  });

  it('laisse l’adresse choisir la référence, sur le web', () => {
    // UNE SEULE page publiée, deux publics. Le lien donné sert la version
    // figée ; le même lien suivi de `?catalogues=main` sert ce qui est en
    // cours. C'est ainsi qu'on regarde l'Italie sans la montrer à personne.
    const avant = process.env.EXPO_PUBLIC_ROAM_CATALOGUES;
    try {
      process.env.EXPO_PUBLIC_ROAM_CATALOGUES = 'v0.1-france';
      jest.isolateModules(() => {
        const module = require('./catalogues');
        expect(module.referenceServie()).toBe('v0.1-france');
      });
      // @ts-expect-error — on simule l'adresse d'un navigateur
      global.location = { search: '?catalogues=main' };
      jest.isolateModules(() => {
        const module = require('./catalogues');
        expect(module.referenceServie()).toBe('main');
        expect(module.BASE).toContain('/main/catalogues');
      });
    } finally {
      // @ts-expect-error — nettoyage du faux `location`
      delete global.location;
      if (avant === undefined) delete process.env.EXPO_PUBLIC_ROAM_CATALOGUES;
      else process.env.EXPO_PUBLIC_ROAM_CATALOGUES = avant;
    }
  });

  it('refuse une référence que l’adresse aurait fabriquée', () => {
    // La référence entre dans une URL de `raw.githubusercontent` : une valeur
    // libre y ferait chercher un catalogue chez n'importe qui.
    const avant = process.env.EXPO_PUBLIC_ROAM_CATALOGUES;
    try {
      process.env.EXPO_PUBLIC_ROAM_CATALOGUES = 'v0.1-france';
      for (const mauvaise of ['../../autre', 'v1/../../autre', '/main', 'main/',
                              'https://ailleurs.example', 'a b', '', '.git',
                              'x'.repeat(65)]) {
        // @ts-expect-error — on simule l'adresse d'un navigateur
        global.location = { search: `?catalogues=${encodeURIComponent(mauvaise)}` };
        jest.isolateModules(() => {
          expect(require('./catalogues').referenceServie()).toBe('v0.1-france');
        });
      }
    } finally {
      // @ts-expect-error — nettoyage du faux `location`
      delete global.location;
      if (avant === undefined) delete process.env.EXPO_PUBLIC_ROAM_CATALOGUES;
      else process.env.EXPO_PUBLIC_ROAM_CATALOGUES = avant;
    }
  });

  it('retombe sur la configuration quand rien n’est inliné', () => {
    // LE point du mécanisme, et le seul qui ne se voie pas : si la lecture
    // échouait, tout retomberait sur `main` sans un mot, et les catalogues
    // d'une version publiée se remettraient à bouger.
    jest.isolateModules(() => {
      jest.doMock(
        'expo-constants',
        () => ({ default: { expoConfig: { extra: { catalogues: 'v0.1-france' } } } }),
        { virtual: true },
      );
      const module = require('./catalogues');
      expect(module.referenceServie()).toBe('v0.1-france');
      expect(module.BASE).toContain('/v0.1-france/catalogues');
      expect(module.BASE).not.toContain('/main/');
    });
  });

  it('ignore une référence vide plutôt que de fabriquer une adresse fausse', () => {
    jest.isolateModules(() => {
      jest.doMock(
        'expo-constants',
        () => ({ default: { expoConfig: { extra: { catalogues: '   ' } } } }),
        { virtual: true },
      );
      expect(require('./catalogues').referenceServie()).toBe(REFERENCE_PAR_DEFAUT);
    });
  });

  it("survit au ramenage du chemin à la racine de la page autonome", () => {
    // La page publiée est UN SEUL fichier, servi sous un chemin quelconque.
    // Expo Router lisant `location.pathname`, un préambule ramène le chemin à
    // la racine AVANT que le bundle ne s'exécute. Il effaçait aussi la
    // question — et `?catalogues=` est lue à l'évaluation de ce module,
    // c'est-à-dire exactement dans cette fenêtre-là. La porte de service
    // marchait en test et ne marchait pas sur la page : seul un navigateur l'a
    // montré, donc on le tient ici.
    const source = require('fs').readFileSync(
      require('path').join(__dirname, '../../scripts/inline-web-build.mjs'), 'utf8',
    );
    const debut = source.indexOf('var initial = location.href;');
    const fin = source.indexOf("addEventListener('load'", debut);
    expect(debut).toBeGreaterThan(0);
    expect(fin).toBeGreaterThan(debut);

    const faux = {
      pathname: '/roam/roam-apercu.html',
      search: '?catalogues=main',
      hash: '',
      href: 'https://x.example/roam/roam-apercu.html?catalogues=main',
    };
    const history = {
      replaceState(_etat: unknown, _titre: string, url: string) {
        const [chemin, question = ''] = url.split('?');
        faux.pathname = chemin;
        faux.search = question ? `?${question}` : '';
      },
      pushState() {},
    };
    // eslint-disable-next-line no-new-func
    new Function('location', 'history', 'addEventListener', 'console',
                 source.slice(debut, fin))(faux, history, () => {}, console);

    expect(faux.pathname).toBe('/');
    expect(faux.search).toBe('?catalogues=main');
  });

  it('est déclarée dans app.json', () => {
    // Le lien est ténu — une clé de configuration lue par un `require` — et
    // sans elle, une version publiée retomberait silencieusement sur `main`.
    const app = require('../../app.json');
    expect(typeof app.expo.extra.catalogues).toBe('string');
    expect(app.expo.extra.catalogues.trim()).not.toBe('');
  });
});
