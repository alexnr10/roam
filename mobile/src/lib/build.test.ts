import { buildLabel, buildStamp } from './build';
import { places } from '../data/catalog';

describe('marque de construction', () => {
  afterEach(() => {
    delete (globalThis as { __ROAM_BUILD__?: unknown }).__ROAM_BUILD__;
  });

  it('ne dit rien hors de l’aperçu web', () => {
    // L'application native n'est pas servie par un cache : pas de marque, et
    // surtout pas de plantage.
    expect(buildStamp()).toBeNull();
  });

  it('annonce quand même la taille du catalogue', () => {
    // C'est le chiffre qui répond à « est-ce que ma suppression est passée ? »,
    // et il est là même sans marque.
    expect(buildLabel()).toBe(`${places.length} lieux`);
  });

  it('ajoute la signature et la date quand la page en porte une', () => {
    (globalThis as { __ROAM_BUILD__?: unknown }).__ROAM_BUILD__ = {
      sha: 'a8a0d5e',
      date: '2026-09-03T12:09:42.000Z',
    };
    const label = buildLabel();
    expect(label).toContain(`${places.length} lieux`);
    expect(label).toContain('a8a0d5e');
    expect(label).toContain('sept');
  });

  it('ignore une marque incomplète plutôt que d’afficher n’importe quoi', () => {
    (globalThis as { __ROAM_BUILD__?: unknown }).__ROAM_BUILD__ = { sha: 'abc' };
    expect(buildStamp()).toBeNull();
  });

  it('laisse tomber une date illisible sans perdre la signature', () => {
    (globalThis as { __ROAM_BUILD__?: unknown }).__ROAM_BUILD__ = {
      sha: 'abcdef0', date: 'pas une date',
    };
    expect(buildLabel()).toBe(`${places.length} lieux · abcdef0`);
  });
});
