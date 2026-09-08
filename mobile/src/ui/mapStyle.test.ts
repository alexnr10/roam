import { REGIONS } from '../lib/regions';
import {
  ETOILE_COULEURS,
  OPACITE_REGION_OUVERTE,
  REGION_FILL_OPACITY,
  REGION_TONES,
  REGION_TONE_BY_CODE,
  mapColors,
  TRANSITION,
  depouiller,
  opaciteDesAplats,
  opaciteDesTraits,
  opaciteEnCascade,
  pasDeCascade,
  rayonDesPastilles,
  repeindre,
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

describe('repeindre', () => {
  /**
   * Un style tiers, réduit à ce qui compte : plusieurs TYPES sur une même
   * couche de données. C'est la forme qu'ont les styles d'OpenMapTiles, dont
   * `positron` — et c'est elle qui faisait tout disparaître.
   */
  const styleTiers = {
    version: 8,
    glyphs: 'https://exemple/{fontstack}/{range}.pbf',
    sources: { openmaptiles: { type: 'vector', url: 'https://exemple' } },
    layers: [
      { id: 'background', type: 'background', paint: { 'background-color': '#fff' } },
      { id: 'water', type: 'fill', 'source-layer': 'water', paint: {} },
      { id: 'waterway', type: 'line', 'source-layer': 'waterway', paint: {} },
      { id: 'landcover-wood', type: 'fill', 'source-layer': 'landcover', paint: {} },
      { id: 'building', type: 'fill', 'source-layer': 'building', paint: {} },
      { id: 'building-3d', type: 'fill-extrusion', 'source-layer': 'building', paint: {} },
      { id: 'highway-motorway', type: 'line', 'source-layer': 'transportation', paint: {} },
      // Les flèches de sens unique : une couche de SYMBOLES sur la même couche
      // de données que les tracés.
      { id: 'highway-oneway', type: 'symbol', 'source-layer': 'transportation', layout: {}, paint: {} },
      { id: 'place-city', type: 'symbol', 'source-layer': 'place', layout: {}, paint: {} },
      { id: 'poi-level-1', type: 'symbol', 'source-layer': 'poi', paint: {} },
      { id: 'boundary-3', type: 'line', 'source-layer': 'boundary', paint: {} },
    ],
  };

  const prefixesParType: Record<string, string> = {
    background: 'background',
    fill: 'fill',
    line: 'line',
    symbol: 'text',
  };

  it('ne pose jamais une propriété étrangère au type de la couche', () => {
    // Poser `line-color` sur une couche de symboles produit un style que
    // MapLibre refuse EN ENTIER : il le signale par un événement et n'émet
    // jamais `load`. Aucune couche de Roam n'est alors posée — la carte reste
    // un rectangle vide, et rien à l'écran ne dit pourquoi.
    const repeint = repeindre(styleTiers);
    for (const couche of repeint.layers) {
      const attendu = prefixesParType[couche.type];
      if (!attendu) continue;
      for (const propriete of Object.keys(couche.paint ?? {})) {
        expect(propriete.startsWith(attendu)).toBe(true);
      }
    }
  });

  it('garde les tracés de route et écarte leurs flèches de sens unique', () => {
    const repeint = repeindre(styleTiers);
    const ids = repeint.layers.map((couche: { id: string }) => couche.id);
    expect(ids).toContain('highway-motorway');
    expect(ids).not.toContain('highway-oneway');
  });

  it('écarte le bavardage : points d’intérêt, frontières, bâtiments en relief', () => {
    const ids = repeindre(styleTiers).layers.map((couche: { id: string }) => couche.id);
    expect(ids).not.toContain('poi-level-1');
    expect(ids).not.toContain('boundary-3');
    expect(ids).not.toContain('building-3d');
  });

  it('n’impose aucune police aux étiquettes qu’il colore', () => {
    // Un nom de fonte absent du jeu de glyphes du style ferait disparaître les
    // étiquettes qu'on vient justement de colorer.
    const ville = repeindre(styleTiers).layers.find(
      (couche: { id: string }) => couche.id === 'place-city',
    );
    expect(ville.paint['text-color']).toBe(mapColors.labelInk);
    expect(ville.layout['text-font']).toBeUndefined();
  });

  it('repeint le fond au sable de l’application', () => {
    const fond = repeindre(styleTiers).layers.find(
      (couche: { id: string }) => couche.id === 'background',
    );
    expect(fond.paint['background-color']).toBe(mapColors.earth);
  });

  it('ne touche pas au style d’origine', () => {
    repeindre(styleTiers);
    expect(styleTiers.layers[0].paint['background-color']).toBe('#fff');
  });
});

describe('opaciteDesAplats — l’effacement des autres régions', () => {
  it('atténue les paliers de zoom, sans toucher à l’ouverte ni au survol', () => {
    // Ce qui s'efface pendant le vol, ce sont LES AUTRES. La région ouverte a
    // déjà son propre voile, et le survol sa propre couleur.
    const plein = opaciteDesAplats();
    const attenue = opaciteDesAplats(0.55);
    const paliers = REGION_FILL_OPACITY.slice(3) as number[];
    for (let i = 0; i < paliers.length; i += 2) {
      const a = plein[4 + i] as unknown[];
      const b = attenue[4 + i] as unknown[];
      expect(b[2]).toBe(a[2]); // région ouverte
      expect(b[4]).toBe(a[4]); // survol
      expect(b[5]).toBeCloseTo((a[5] as number) * 0.55, 10);
    }
  });
});

describe('pasDeCascade', () => {
  it('garde le pas du livrable quand les lieux sont peu nombreux', () => {
    // Les huit lieux de Mayotte : douze millisecondes chacun, soit un
    // balayage de moins d'un dixième de seconde.
    expect(pasDeCascade(8)).toBe(TRANSITION.lieux.cascade);
  });

  it('resserre le pas quand il y a foule', () => {
    // Douze millisecondes sur les deux cent soixante-douze lieux d'Occitanie
    // feraient trois secondes et quart : ce n'est plus un remplissage, c'est
    // une attente.
    const pas = pasDeCascade(272);
    expect(pas).toBeLessThan(TRANSITION.lieux.cascade);
    expect(pas * 271).toBeCloseTo(TRANSITION.lieux.etalement, 6);
  });

  it('ne divise pas par zéro sur un lieu unique', () => {
    expect(pasDeCascade(1)).toBe(0);
    expect(pasDeCascade(0)).toBe(0);
  });

  it('borne l’étalement, quel que soit le nombre de lieux', () => {
    for (const combien of [1, 2, 8, 41, 137, 272, 2029]) {
      const etalement = pasDeCascade(combien) * Math.max(0, combien - 1);
      expect(etalement).toBeLessThanOrEqual(TRANSITION.lieux.etalement + 1e-9);
    }
  });
});

describe('opaciteEnCascade', () => {
  /** Évalue l'expression à la main, pour un lieu donné. */
  const evaluer = (expression: unknown, proprietes: Record<string, number>): number => {
    if (!Array.isArray(expression)) return expression as number;
    const [operateur, ...arguments_] = expression;
    const valeurs = arguments_.map((a) => evaluer(a, proprietes));
    switch (operateur) {
      case 'get':
        return proprietes[arguments_[0] as string];
      case '*':
        return valeurs.reduce((a, b) => a * b, 1);
      case '-':
        return valeurs[0] - valeurs[1];
      case '/':
        return valeurs[0] / valeurs[1];
      case 'min':
        return Math.min(...valeurs);
      case 'max':
        return Math.max(...valeurs);
      case 'match': {
        const sujet = valeurs[0];
        for (let i = 1; i < valeurs.length - 1; i += 2) {
          if (sujet === valeurs[i]) return valeurs[i + 1];
        }
        return valeurs[valeurs.length - 1];
      }
      default:
        throw new Error(`opérateur inattendu : ${operateur}`);
    }
  };

  const premier = { tier: 1, rang: 0 };
  const centieme = { tier: 1, rang: 100 };

  it('part de rien', () => {
    expect(evaluer(opaciteEnCascade(0, 12), premier)).toBe(0);
  });

  it('remplit le premier point en `apparition` millisecondes', () => {
    expect(evaluer(opaciteEnCascade(TRANSITION.lieux.apparition, 12), premier)).toBe(1);
  });

  it('fait attendre les points éloignés du centre', () => {
    // Le centième point n'a pas encore commencé quand le premier est plein.
    expect(evaluer(opaciteEnCascade(TRANSITION.lieux.apparition, 12), centieme)).toBe(0);
  });

  it('n’oublie personne à la fin de la cascade', () => {
    const front = 100 * 12 + TRANSITION.lieux.apparition;
    expect(evaluer(opaciteEnCascade(front, 12), centieme)).toBe(1);
  });

  it('respecte le retrait du niveau 3', () => {
    const plein = evaluer(opaciteEnCascade(9999, 12), { tier: 3, rang: 0 });
    expect(plein).toBeCloseTo(0.8, 10);
  });
});

describe('depouiller', () => {
  const repeint = repeindre({
    version: 8,
    sources: {},
    layers: [
      { id: 'background', type: 'background', paint: {} },
      { id: 'water', type: 'fill', 'source-layer': 'water', paint: {} },
      { id: 'waterway', type: 'line', 'source-layer': 'waterway', paint: {} },
      { id: 'water-name', type: 'symbol', 'source-layer': 'water', layout: {}, paint: {} },
      { id: 'highway-motorway', type: 'line', 'source-layer': 'transportation', paint: {} },
      { id: 'landcover-wood', type: 'fill', 'source-layer': 'landcover', paint: {} },
      { id: 'building', type: 'fill', 'source-layer': 'building', paint: {} },
      { id: 'place-city', type: 'symbol', 'source-layer': 'place', layout: {}, paint: {} },
    ],
  });

  it('ne garde que le sol et l’eau', () => {
    // Une route vue à travers un aplat de conquête à quarante-cinq pour cent
    // devient un trait qui ne dit rien : ni ville, ni frontière, ni chemin.
    const ids = depouiller(repeint).layers.map((couche: { id: string }) => couche.id);
    expect(ids).toEqual(['background', 'water', 'waterway']);
  });

  it('laisse la carte principale intacte', () => {
    expect(repeint.layers.length).toBeGreaterThan(3);
  });
});

describe('rayonDesPastilles', () => {
  it('donne aux deux premières notes de quoi porter un symbole', () => {
    // Un disque de moins de sept pixels de rayon ne peut pas accueillir une
    // icône lisible : le symbole y deviendrait une tache.
    const expression = rayonDesPastilles();
    for (let i = 3; i < expression.length; i += 2) {
      const parNote = expression[i + 1] as unknown[];
      // ['match', ['get','tier'], 1, grand, 2, moyen, petit]
      const [troisEtoiles, deuxEtoiles, uneEtoile] = [parNote[3], parNote[5], parNote[6]];
      expect(troisEtoiles).toBeGreaterThan(deuxEtoiles as number);
      // Trois tailles franchement distinctes : une pastille à deux étoiles
      // aussi large qu'une à trois, mais sans symbole, paraissait incomplète
      // plutôt que moindre.
      expect(deuxEtoiles).toBeGreaterThan((uneEtoile as number) * 1.4);
      expect(troisEtoiles).toBeGreaterThan((deuxEtoiles as number) * 1.4);
      // Une étoile reste un point : mille deux cent soixante-neuf lieux à cette
      // note, tous porteurs d'un symbole, feraient une carte illisible.
      expect(uneEtoile).toBeLessThan(5);
    }
  });

  it('grossit avec le zoom', () => {
    const expression = rayonDesPastilles();
    const zooms = expression.filter((_, i) => i >= 3 && i % 2 === 1) as number[];
    expect(zooms).toEqual([...zooms].sort((a, b) => a - b));
  });
});

describe('ETOILE_COULEURS', () => {
  it('donne trois teintes distinctes, de la plus forte à la plus effacée', () => {
    const valeurs = [ETOILE_COULEURS[3], ETOILE_COULEURS[2], ETOILE_COULEURS[1]];
    expect(new Set(valeurs).size).toBe(3);
    // Du plus foncé au plus clair : la note se lit à la valeur, pas seulement
    // à la teinte — ce qui la garde lisible en noir et blanc.
    const clarte = (hex: string) =>
      parseInt(hex.slice(1, 3), 16) + parseInt(hex.slice(3, 5), 16) + parseInt(hex.slice(5, 7), 16);
    expect(clarte(valeurs[0])).toBeLessThan(clarte(valeurs[1]));
    expect(clarte(valeurs[1])).toBeLessThan(clarte(valeurs[2]));
  });
});

describe('opaciteDesTraits', () => {
  it('efface les contours administratifs quand on approche', () => {
    // Nos contours sont simplifiés ; à l'échelle d'une île, notre trait passe à
    // côté de la vraie côte que les tuiles dessinent juste en dessous. Le
    // retirer là où il devient faux vaut mieux que d'alourdir le fichier — et
    // une frontière de région n'a plus rien à dire quand on est dedans.
    const expression = opaciteDesTraits();
    expect(expression[0]).toBe('interpolate');
    const [zoomBas, opaciteBasse, zoomHaut, opaciteHaute] = expression.slice(3) as number[];
    expect(opaciteBasse).toBe(1);
    expect(opaciteHaute).toBe(0);
    expect(zoomHaut).toBeGreaterThan(zoomBas);
  });

  it('respecte l’opacité maximale demandée', () => {
    // L'ombre des régions vit à 0,35 : l'effacement ne doit pas la rendre plus
    // présente qu'elle ne l'était.
    expect((opaciteDesTraits(0.35).slice(3) as number[])[1]).toBe(0.35);
  });
});
