import { PAYS, PAYS_EMBARQUE, PaysInconnu, catalogueDe, dejaCharge, deposer, lireIndex, obtenir } from './catalogues';
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
