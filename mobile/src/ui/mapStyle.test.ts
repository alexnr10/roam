import { colors } from '../theme';
import { REGIONS, voisinage, voisinageDe } from '../lib/regions';
import {
  ETOILE_COULEURS,
  OPACITE_REGION_OUVERTE,
  OPACITE_PLEINE,
  REGION_FILL_OPACITY,
  REGION_TONES,
  REGION_TONE_BY_CODE,
  mapColors,
  TRANSITION,
  depouiller,
  margeDeCamera,
  opaciteDesAplats,
  opaciteDesAplatsNative,
  opaciteDesPastilles,
  opaciteDesTraits,
  opaciteEnCascade,
  pasDeCascade,
  rayonDesPastilles,
  repeindre,
  coloriage,
  tonsDesRegions,
  tonsDuPays,
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

describe('opaciteDesAplatsNative', () => {
  // Les SDK d'Android et d'iOS ne connaissent pas `feature-state` : il n'existe
  // que dans la version web de MapLibre. La question qu'il posait reste la
  // même, elle se pose simplement dans l'expression.

  it('ne mentionne jamais `feature-state`', () => {
    const dedans = JSON.stringify(opaciteDesAplatsNative('53'));
    const dehors = JSON.stringify(opaciteDesAplatsNative(null));
    expect(dedans).not.toContain('feature-state');
    expect(dehors).not.toContain('feature-state');
  });

  it('ne place `zoom` qu’en entrée de l’interpolation de premier niveau', () => {
    // Même piège que sur le web, et il se referme de la même façon : une couche
    // refusée par MapLibre manque en silence.
    for (const expression of [opaciteDesAplatsNative(null), opaciteDesAplatsNative('53')]) {
      expect(expression[0]).toBe('interpolate');
      expect(cheminsDuZoom(expression)).toEqual(['/2']);
    }
  });

  it('rend les paliers nus quand aucune région n’est ouverte', () => {
    // Rien à distinguer : pas de `case` à faire évaluer pour chaque polygone à
    // chaque image.
    const expression = opaciteDesAplatsNative(null);
    const paliers = REGION_FILL_OPACITY.slice(3) as number[];
    for (let i = 0; i < paliers.length; i += 2) {
      expect(expression[3 + i]).toBe(paliers[i]);
      expect(expression[4 + i]).toBe(paliers[i + 1]);
    }
  });

  it('fait tomber le voile de la seule région ouverte', () => {
    const expression = opaciteDesAplatsNative('53', 0.55);
    const paliers = REGION_FILL_OPACITY.slice(3) as number[];
    for (let i = 0; i < paliers.length; i += 2) {
      const sortie = expression[4 + i] as unknown[];
      expect(sortie[0]).toBe('case');
      expect(sortie[1]).toEqual(['==', ['get', 'code'], '53']);
      expect(sortie[2]).toBe(OPACITE_REGION_OUVERTE);
      // Les AUTRES régions : atténuées, pas effacées. Elles disent encore où
      // l'on est dans le pays.
      expect(sortie[3]).toBeCloseTo(paliers[i + 1] * 0.55, 10);
    }
  });

  it('donne les mêmes paliers que la version web', () => {
    // Une seule échelle d'opacité, deux façons de poser la question « est-ce
    // la région ouverte ? ». Si les deux divergeaient, la carte n'aurait pas la
    // même identité selon le téléphone.
    const web = opaciteDesAplats();
    const natif = opaciteDesAplatsNative(null);
    const paliers = REGION_FILL_OPACITY.slice(3) as number[];
    for (let i = 0; i < paliers.length; i += 2) {
      expect(natif[3 + i]).toBe(web[3 + i]);
      expect(natif[4 + i]).toBe((web[4 + i] as unknown[])[5]);
    }
  });
});

describe('opaciteDesPastilles', () => {
  it('laisse le niveau 3 en retrait quand rien n’est touché', () => {
    expect(opaciteDesPastilles(null)).toEqual(OPACITE_PLEINE);
    expect(opaciteDesPastilles()).toEqual(OPACITE_PLEINE);
  });

  it('fait reculer les autres autour du lieu touché', () => {
    // Le lieu touché garde sa pleine opacité, les autres reculent : sans cela,
    // on ne voit pas lequel on a pris.
    expect(opaciteDesPastilles('Q243')).toEqual([
      'case',
      ['==', ['get', 'id'], 'Q243'],
      1,
      0.55,
    ]);
  });
});

describe('margeDeCamera', () => {
  it('réserve la place que prennent la recherche et le bandeau', () => {
    // Cadrer une région sur la hauteur entière fait passer la Bretagne sous la
    // barre de recherche et la Corse sous le bandeau.
    const marge = margeDeCamera(390, 844);
    expect(marge.top).toBe(196);
    expect(marge.bottom).toBe(250);
  });

  it('ne demande jamais plus d’un tiers du cadre', () => {
    // MapLibre refuse une marge plus grande que son conteneur : sur un écran
    // court — un téléphone à l'horizontale — la maquette dépasserait.
    const marge = margeDeCamera(320, 300);
    expect(marge.top).toBeLessThanOrEqual(100);
    expect(marge.bottom).toBeLessThanOrEqual(100);
    expect(marge.top + marge.bottom).toBeLessThan(300);
  });

  it('garde une marge minimale sur un cadre minuscule', () => {
    const marge = margeDeCamera(12, 12);
    expect(marge.top).toBe(8);
    expect(marge.left).toBe(8);
  });
});

describe('le coloriage des régions', () => {
  /**
   * Quatre sables, et jamais le même de part et d'autre d'une frontière —
   * sinon la frontière disparaît.
   *
   * Le défaut qui a mené ici : la table est écrite pour la France, et l'Italie
   * y passait presque entièrement grise. Trois ou quatre régions du nord
   * étaient colorées par ACCIDENT, leurs codes (01 à 06, 11) se trouvant être
   * aussi ceux de la Guadeloupe, de la Martinique et de l'Île-de-France. Une
   * table d'un pays appliquée à un autre ne dit rien : elle coïncide.
   */
  const conflits = (
    tons: Record<string, string>,
    voisins: Map<string, Set<string>>,
  ): string[] => {
    const trouves: string[] = [];
    for (const [code, entoure] of voisins) {
      for (const voisin of entoure) {
        if (tons[code] && tons[code] === tons[voisin]) trouves.push(`${code}/${voisin}`);
      }
    }
    return trouves;
  };

  it('déduit le voisinage des contours jointifs eux-mêmes', () => {
    // Les contours partagent EXACTEMENT les mêmes sommets sur une frontière
    // commune — le pipeline les découpe en arcs partagés. Il n'y a donc aucune
    // géométrie à intersecter, juste des sommets à compter.
    const voisins = voisinage();
    expect(voisins.get('11')?.size).toBeGreaterThanOrEqual(5); // Île-de-France
    expect(voisins.get('53')).toContain('52'); // Bretagne / Pays de la Loire
    expect(voisins.get('94')?.size).toBe(0); // la Corse ne touche personne
  });

  it('ne laisse aucune frontière française sans contraste', () => {
    expect(conflits(REGION_TONE_BY_CODE, voisinage())).toEqual([]);
  });

  it("colorie l'Italie, qui n'a pas de table écrite à la main", () => {
    // Le vrai fichier servi, pas une maquette : c'est lui qui part sur les
    // téléphones.
    //
    // Mais il n'est pas TOUJOURS là, et c'est voulu : la branche `v0.1-france`
    // efface exprès tout ce qui est italien, puisqu'elle ne sert qu'un pays.
    // Ce test y échouait donc, et faisait échouer la construction entière
    // d'une branche dont le contenu est parfaitement sain. Un fichier absent
    // par conception n'est pas une régression : on passe.
    const chemin = require('path').join(__dirname, '../../../catalogues/it-contours.json');
    if (!require('fs').existsSync(chemin)) return;
    const contours = require(chemin);
    const voisins = voisinageDe(contours.region.features);
    expect(voisins.size).toBe(20);

    // La mesure du défaut, gardée : la table française ne rencontrait que six
    // des vingt codes italiens, et par pure coïncidence de numérotation. Les
    // quatorze autres retombaient sur la teinte par défaut — d'où une Italie
    // presque entièrement grise, avec quelques régions du nord colorées.
    const parHasard = [...voisins.keys()].filter((code) => code in REGION_TONE_BY_CODE);
    expect(parHasard.length).toBeLessThan(8);

    const tons = coloriage(voisins);
    expect(Object.keys(tons)).toHaveLength(20);
    expect(conflits(tons, voisins)).toEqual([]);
    // Les quatre teintes servent : avec deux, l'ensemble penche.
    expect(new Set(Object.values(tons)).size).toBe(4);
  });

  it('rend le même coloriage à chaque démarrage', () => {
    const voisins = voisinage();
    expect(coloriage(voisins)).toEqual(coloriage(voisins));
  });

  it('donne à la France sa table, et à un pays inconnu un calcul', () => {
    const voisins = voisinage();
    expect(tonsDuPays('FR', voisins)).toBe(REGION_TONE_BY_CODE);
    expect(tonsDuPays('ZZ', voisins)).toEqual(coloriage(voisins));
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

/** Le canal linéaire d'un octet sRGB. */
function canal(octet: number): number {
  const c = octet / 255;
  return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
}

/** Luminance relative, au sens WCAG. */
function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => canal(parseInt(hex.slice(i, i + 2), 16)));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

/** Le rapport de contraste entre deux couleurs opaques. */
function contraste(a: string, b: string): number {
  const [x, y] = [luminance(a), luminance(b)];
  return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05);
}

/** Une couleur posée sur une autre, avec son opacité. */
function pose(dessus: string, dessous: string, opacite: number): string {
  const melange = [1, 3, 5].map((i) => {
    const f = parseInt(dessus.slice(i, i + 2), 16);
    const d = parseInt(dessous.slice(i, i + 2), 16);
    return Math.round(f * opacite + d * (1 - opacite));
  });
  return `#${melange.map((c) => c.toString(16).padStart(2, '0')).join('')}`;
}

/** La chroma OKLCH : à quel point une couleur appelle l'œil. */
function chroma(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => canal(parseInt(hex.slice(i, i + 2), 16)));
  const cube = (x: number) => (x > 0 ? Math.cbrt(x) : 0);
  const l = cube(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
  const m = cube(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
  const s = cube(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
  const a = 1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s;
  const bb = 0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s;
  return Math.hypot(a, bb);
}

describe('rayonDesPastilles — l’anneau du lieu mis en avant', () => {
  it('n’enferme jamais `zoom` dans un calcul', () => {
    // `["+", rayonDesPastilles(), 4]` enfermait `["zoom"]` dans une addition :
    // MapLibre refuse alors la couche par un ÉVÉNEMENT, pas par une exception.
    // L'anneau du lieu touché n'a jamais existé, sur aucune plateforme, et rien
    // dans l'application ne le disait.
    const expression = rayonDesPastilles(4);
    expect(expression[0]).toBe('interpolate');
    expect(cheminsDuZoom(expression)).toEqual(['/2']);
  });

  it('élargit chaque note de la marge demandée', () => {
    const nu = rayonDesPastilles();
    const large = rayonDesPastilles(4);
    for (let i = 3; i < nu.length; i += 2) {
      // Les paliers de zoom ne bougent pas…
      expect(large[i]).toBe(nu[i]);
      const avant = nu[i + 1] as number[];
      const apres = large[i + 1] as number[];
      // …et chacune des trois notes grossit d'autant : l'anneau entoure la
      // pastille, il ne la remplace pas.
      for (const rang of [3, 5, 6]) {
        expect(apres[rang]).toBeCloseTo(avant[rang] + 4, 10);
      }
    }
  });
});

describe('ETOILE_COULEURS', () => {
  it('donne trois couleurs distinctes', () => {
    expect(new Set([ETOILE_COULEURS[3], ETOILE_COULEURS[2], ETOILE_COULEURS[1]]).size).toBe(3);
  });

  it('garde la note la plus basse lisible sur tous les fonds de la carte', () => {
    // LE test de ce bloc, et celui qui manquait. La couleur d'une étoile a
    // longtemps été choisie pour sa place dans une famille ; personne ne l'avait
    // mesurée sur ce qu'elle recouvre. Le beige de la note la plus basse tenait
    // 1,52:1 sur un axe routier — invisible, sur le plus petit disque de la
    // carte et les deux tiers du catalogue.
    //
    // Le plancher ne vaut QUE pour cette note-là, et c'est voulu : elle est la
    // seule pastille nue. Les deux autres portent le symbole de leur thème,
    // dessiné en sable clair — un disque large avec un dessin dedans se lit par
    // son contraste INTERNE (5,72:1 pour trois étoiles, 3,03:1 pour deux), et
    // une route qui passe derrière ne l'efface pas. Un point de trois pixels
    // n'a pas de dedans : il n'existe que par ce qu'il y a derrière lui.
    const fonds = {
      ...Object.fromEntries(
        Object.entries(REGION_TONES).map(([nom, ton]) => [
          `aplat ${nom}`,
          pose(ton, mapColors.earth, OPACITE_REGION_OUVERTE),
        ]),
      ),
      'route majeure': mapColors.road,
      'route mineure': mapColors.roadMinor,
      'espace vert': mapColors.green,
      bâti: mapColors.built,
    };
    // 2:1 est bas pour du texte ; c'est le plancher qui convient à une forme
    // pleine de plusieurs pixels, qu'on repère à sa masse et non à son dessin.
    // En dessous, le disque se fond dans le fond.
    const nue = ETOILE_COULEURS[1];
    const trop_pale: string[] = [];
    for (const [nom, fond] of Object.entries(fonds)) {
      const ratio = contraste(nue, fond);
      if (ratio <= 2) trop_pale.push(`1★ ${nue} sur ${nom} : ${ratio.toFixed(2)}:1`);
    }
    expect(trop_pale).toEqual([]);
  });

  it('garde un symbole lisible sur les deux pastilles qui en portent un', () => {
    // Le pendant du test précédent : ce qui tient les deux premières notes,
    // c'est leur dedans. Si une terre cuite s'éclaircissait au point que le
    // symbole sable ne s'y détache plus, ces pastilles perdraient la seule
    // chose qui les fait lire sur un fond chargé.
    expect(contraste(ETOILE_COULEURS[3], colors.bg)).toBeGreaterThan(4.5);
    expect(contraste(ETOILE_COULEURS[2], colors.bg)).toBeGreaterThan(3);
  });

  it('réserve la terre cuite aux deux premières notes', () => {
    // La hiérarchie ne passe PLUS par la valeur : deux et une étoiles ne se
    // tenaient qu'à cinq pour cent l'une de l'autre, ce qui ne se voyait pas,
    // et l'exiger obligeait la plus petite pastille à être aussi la plus pâle.
    // Elle passe par la taille (rayons 9 / 5,5 / 3), par le symbole que seules
    // les deux premières notes portent, et par la saturation testée ici.
    expect(chroma(ETOILE_COULEURS[1])).toBeLessThan(chroma(ETOILE_COULEURS[2]) / 3);
    expect(chroma(ETOILE_COULEURS[1])).toBeLessThan(chroma(ETOILE_COULEURS[3]) / 3);
    // Et la note la plus haute reste l'encre la plus foncée de la carte.
    expect(luminance(ETOILE_COULEURS[3])).toBeLessThan(luminance(ETOILE_COULEURS[2]));
    expect(luminance(ETOILE_COULEURS[3])).toBeLessThan(luminance(ETOILE_COULEURS[1]));
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
