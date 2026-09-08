import {
  ajoutee,
  basculee,
  parDateDecroissante,
  retiree,
  sansLesVisites,
} from './envies';
import type { Envie } from '../types';

const le = (jour: string) => new Date(`2026-03-${jour}T10:00:00.000Z`);
const envie = (placeId: string, jour: string): Envie => ({
  placeId,
  addedAt: le(jour).toISOString(),
});

describe('ajoutee', () => {
  it('ajoute un lieu avec sa date', () => {
    const liste = ajoutee([], 'Q1', le('10'));
    expect(liste).toHaveLength(1);
    expect(liste[0].placeId).toBe('Q1');
    expect(liste[0].addedAt).toBe('2026-03-10T10:00:00.000Z');
  });

  it("n'ajoute pas deux fois le même lieu", () => {
    const une = ajoutee([], 'Q1', le('10'));
    const deux = ajoutee(une, 'Q1', le('11'));
    // La liste est rendue TELLE QUELLE : pas de doublon, et pas de rendu inutile.
    expect(deux).toBe(une);
  });
});

describe('retiree', () => {
  it('retire le lieu nommé et lui seul', () => {
    const liste = [envie('Q1', '10'), envie('Q2', '11')];
    expect(retiree(liste, 'Q1').map((e) => e.placeId)).toEqual(['Q2']);
  });
});

describe('basculee', () => {
  it('ajoute ce qui est absent, retire ce qui est présent', () => {
    const une = basculee([], 'Q1', le('10'));
    expect(une.map((e) => e.placeId)).toEqual(['Q1']);
    expect(basculee(une, 'Q1', le('11'))).toEqual([]);
  });
});

describe('sansLesVisites', () => {
  it('retire de la liste un lieu qui vient d’être validé', () => {
    // LA règle demandée : la liste dit ce qu'il RESTE à faire. Un lieu validé
    // qu'on y laisserait ferait de la liste un second carnet de visites.
    const liste = [envie('Q1', '10'), envie('Q2', '11'), envie('Q3', '12')];
    const reste = sansLesVisites(liste, new Set(['Q2']));
    expect(reste.map((e) => e.placeId)).toEqual(['Q1', 'Q3']);
  });

  it('retire tout un lot validé d’un coup', () => {
    // Le quadrillage en valide cinquante d'un geste : le nettoyage doit être
    // ensembliste, pas lieu par lieu.
    const liste = [envie('Q1', '10'), envie('Q2', '11'), envie('Q3', '12')];
    expect(sansLesVisites(liste, new Set(['Q1', 'Q3']))).toHaveLength(1);
  });

  it('rend la liste inchangée quand il n’y a rien à retirer', () => {
    // L'identité compte : elle évite un rendu et une écriture dans le
    // stockage local à chaque visite enregistrée, qu'elle concerne la liste
    // ou non.
    const liste = [envie('Q1', '10')];
    expect(sansLesVisites(liste, new Set(['Q9']))).toBe(liste);
    expect(sansLesVisites(liste, new Set())).toBe(liste);
  });

  it("n'a besoin d'aucun lieu au catalogue pour trancher", () => {
    // La règle porte sur des identifiants. Un lieu sorti du catalogue ne
    // ressuscite pas une envie, et n'en efface pas non plus.
    expect(sansLesVisites([envie('Q404', '10')], new Set(['Q404']))).toEqual([]);
  });
});

describe('parDateDecroissante', () => {
  it('met la dernière envie ajoutée en tête', () => {
    const liste = [envie('Q1', '10'), envie('Q2', '12'), envie('Q3', '11')];
    expect(parDateDecroissante(liste).map((e) => e.placeId)).toEqual(['Q2', 'Q3', 'Q1']);
  });

  it('ne touche pas à la liste reçue', () => {
    const liste = [envie('Q1', '10'), envie('Q2', '12')];
    parDateDecroissante(liste);
    expect(liste.map((e) => e.placeId)).toEqual(['Q1', 'Q2']);
  });
});
