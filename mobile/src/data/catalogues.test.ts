import { PAYS, PAYS_EMBARQUE, PaysInconnu, catalogueDe, dejaCharge, deposer, obtenir } from './catalogues';
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
    PAYS.push({ code: 'IT', name: 'Italie', url: 'https://exemple.test/it.json' });
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
    PAYS.push({ code: 'ZZ', name: 'Zzz', url: 'https://exemple.test/zz.json' });
    const casse = async () => ({ ok: false, status: 404 } as unknown as Response);
    await expect(obtenir('ZZ', casse as unknown as typeof fetch)).rejects.toThrow('404');
    PAYS.pop();
  });

  it('accepte un catalogue déposé par un autre chemin', () => {
    deposer('YY', vide);
    expect(dejaCharge('YY')).toBe(true);
  });
});
