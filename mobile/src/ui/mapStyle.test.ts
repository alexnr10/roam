import { REGIONS } from '../lib/regions';
import {
  OPACITE_REGION_OUVERTE,
  REGION_FILL_OPACITY,
  REGION_TONES,
  REGION_TONE_BY_CODE,
  opaciteDesAplats,
  tonsDesRegions,
} from './mapStyle';

/** Où `["zoom"]` apparaît-il dans une expression ? Les chemins, en clair. */
function cheminsDuZoom(expression: unknown, chemin = ''): string[] {
  if (!Array.isArray(expression)) return [];
  if (expression[0] === 'zoom') return [chemin];
  return expression.flatMap((element, index) =>
    cheminsDuZoom(element, `${chemin}/${index}`),
  );
}

describe('opaciteDesAplats', () => {
  it('ne place `zoom` qu’en entrée de l’interpolation de premier niveau', () => {
    // MapLibre refuse une couche où `["zoom"]` est imbriqué ailleurs — et il la
    // refuse par un événement `error`, pas par une exception. La couche manque
    // alors sans qu'aucune ligne ne le dise : les aplats de régions étaient
    // absents, donc la carte n'avait ni couleur ni clic, et rien ne l'expliquait.
    const expression = opaciteDesAplats();
    expect(expression[0]).toBe('interpolate');
    expect(cheminsDuZoom(expression)).toEqual(['/2']);
  });

  it('garde les paliers du livrable, survol compris', () => {
    const expression = opaciteDesAplats();
    const paliers = REGION_FILL_OPACITY.slice(3) as number[];
    for (let i = 0; i < paliers.length; i += 2) {
      // Le zoom du palier passe tel quel…
      expect(expression[3 + i]).toBe(paliers[i]);
      // …et l'opacité devient un cas de survol dont la branche « au repos »
      // porte la valeur d'origine.
      const sortie = expression[4 + i] as unknown[];
      expect(sortie[0]).toBe('case');
      // Région ouverte d'abord, survol ensuite, palier de zoom en dernier.
      expect(sortie[2]).toBe(OPACITE_REGION_OUVERTE);
      expect(sortie[4]).toBe(0.85);
      expect(sortie[5]).toBe(paliers[i + 1]);
    }
  });
});

describe('tonsDesRegions', () => {
  const expression = tonsDesRegions();

  it('donne un sable à chacune des dix-huit régions', () => {
    const codes = expression.slice(2, -1).filter((_, index) => index % 2 === 0);
    expect(new Set(codes)).toEqual(new Set(REGIONS.keys()));
  });

  it('n’emploie que les quatre teintes de la famille', () => {
    const teintes = expression.slice(3).filter((_, index) => index % 2 === 0);
    for (const teinte of teintes) {
      expect(Object.values(REGION_TONES)).toContain(teinte);
    }
  });

  it('ne donne jamais la même teinte à deux régions frontalières', () => {
    // Dix-huit aplats de la même couleur donnent une tache, dix-huit couleurs
    // différentes un patchwork. Quatre teintes suffisent, à condition que le
    // coloriage soit fait à la main — un hachage donnerait des voisines
    // jumelles, et la frontière disparaîtrait.
    const voisines: [string, string][] = [
      ['11', '24'], // Île-de-France / Centre-Val de Loire
      ['11', '32'], // Île-de-France / Hauts-de-France
      ['11', '44'], // Île-de-France / Grand Est
      ['11', '28'], // Île-de-France / Normandie
      ['53', '52'], // Bretagne / Pays de la Loire
      ['53', '28'], // Bretagne / Normandie
      ['76', '75'], // Occitanie / Nouvelle-Aquitaine
      ['76', '84'], // Occitanie / Auvergne-Rhône-Alpes
      ['76', '93'], // Occitanie / Provence-Alpes-Côte d'Azur
      ['84', '93'], // Auvergne-Rhône-Alpes / Provence-Alpes-Côte d'Azur
      ['84', '27'], // Auvergne-Rhône-Alpes / Bourgogne-Franche-Comté
      ['27', '44'], // Bourgogne-Franche-Comté / Grand Est
      ['27', '24'], // Bourgogne-Franche-Comté / Centre-Val de Loire
      ['75', '52'], // Nouvelle-Aquitaine / Pays de la Loire
      ['75', '24'], // Nouvelle-Aquitaine / Centre-Val de Loire
      ['52', '24'], // Pays de la Loire / Centre-Val de Loire
      ['32', '28'], // Hauts-de-France / Normandie
      ['32', '44'], // Hauts-de-France / Grand Est
      ['28', '24'], // Normandie / Centre-Val de Loire
    ];
    for (const [a, b] of voisines) {
      expect(REGION_TONE_BY_CODE[a]).not.toBe(REGION_TONE_BY_CODE[b]);
    }
  });
});
