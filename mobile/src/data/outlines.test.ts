import { areas } from './catalog';
import { OUTLINE_ATTRIBUTION, outlinesFor } from './outlines';

describe('contours des territoires', () => {
  it('en fournit pour les régions et les départements', () => {
    expect(outlinesFor('region')!.features.length).toBeGreaterThan(10);
    expect(outlinesFor('departement')!.features.length).toBeGreaterThan(90);
  });

  it("n'en promet pas là où il n'y en a pas", () => {
    // Les communes viendront ; le pays n'en a pas besoin. Dans les deux cas
    // l'écran doit pouvoir retomber sur la liste plutôt que sur un cadre vide.
    expect(outlinesFor('commune')).toBeNull();
    expect(outlinesFor('country')).toBeNull();
  });

  it('couvre tous les territoires du catalogue', () => {
    // Un territoire du catalogue sans contour est un trou blanc au milieu de
    // la carte, et il ne se signale nulle part ailleurs.
    for (const level of ['region', 'departement'] as const) {
      const drawn = new Set(outlinesFor(level)!.features.map((f) => f.properties.code));
      const missing = areas[level].filter((area) => !drawn.has(area.code));
      expect(missing.map((area) => area.name)).toEqual([]);
    }
  });

  it('porte un code sur chaque contour', () => {
    // MapLibre colore par `feature-state`, qui s'accroche à cet identifiant.
    for (const feature of outlinesFor('departement')!.features) {
      expect(typeof feature.properties.code).toBe('string');
      expect(feature.properties.code).not.toHaveLength(0);
    }
  });

  it('emporte sa mention de source', () => {
    // Licence ouverte : citer la source est une obligation, pas un ornement.
    expect(OUTLINE_ATTRIBUTION).toMatch(/Etalab/);
  });
});
