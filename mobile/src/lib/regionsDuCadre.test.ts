import { regionsDuCadre } from './regions';

/**
 * La vignette du pays, et la règle qui choisit ce qu'elle montre.
 *
 * C'était une LISTE DE CODES : `01`, `02`, `03`, `04`, `06` — les cinq régions
 * d'outre-mer, sorties d'une vignette qu'elles auraient étirée sur deux océans.
 * Ces mêmes codes, en Italie, sont le Piémont, le Val d'Aoste, la Lombardie, le
 * Trentin et le Frioul : la vignette italienne perdait tout son nord, et rien
 * ne le disait. Même accident que le coloriage des régions, même cause — une
 * table écrite pour un pays, appliquée à un autre.
 */
describe('les régions de la vignette', () => {
  const DROM = ['01', '02', '03', '04', '06'];

  it("garde la métropole et laisse l'outre-mer dehors", () => {
    const codes = regionsDuCadre();
    expect(codes).toContain('94'); // la Corse reste : elle est dans le cadre
    expect(codes).toContain('53'); // la Bretagne aussi
    for (const drom of DROM) expect(codes).not.toContain(drom);
  });

  it('choisit par la GÉOMÉTRIE, pas par une liste de codes', () => {
    // La preuve : avec un cadre posé sur les Antilles, ce sont la Guadeloupe et
    // la Martinique qui entrent, et la Bretagne qui sort. Une liste noire de
    // codes rendrait exactement l'inverse, quel que soit le cadre.
    const antilles: [[number, number], [number, number]] = [[-62, 14], [-60, 17]];
    const codes = regionsDuCadre(antilles);
    expect(codes).toContain('01'); // Guadeloupe
    expect(codes).toContain('02'); // Martinique
    expect(codes).not.toContain('53'); // Bretagne
    expect(codes).not.toContain('94'); // Corse
  });

  it('montre tout quand on ne sait rien du cadre', () => {
    expect(regionsDuCadre(null).length).toBeGreaterThan(15);
  });
});
