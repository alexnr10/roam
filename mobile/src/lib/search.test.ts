import { MIN_CARACTERES, fold, pertinence, search, variantes } from './search';
import type { Place } from '../types';

function lieu(name: string, extra: Partial<Place> = {}): Place {
  return {
    id: `Q${name.length}${name.charCodeAt(0)}${extra.communeName ?? ''}`,
    slug: name,
    name,
    themeId: 'chateaux',
    lat: 45,
    lon: 2,
    radiusM: 150,
    score: 50,
    ...extra,
  } as Place;
}

describe('normalisation', () => {
  it('ignore les accents et la casse', () => {
    // On tape « chateau » sur un clavier de téléphone, pas « Château ».
    expect(fold('Château de Sagonne')).toBe('chateau de sagonne');
    expect(fold('Vézère')).toBe('vezere');
  });
});

describe('pertinence', () => {
  it('classe le début du texte avant le début d’un mot, avant le milieu', () => {
    expect(pertinence('Gordes', 'gordes')).toBe(4);
    expect(pertinence('Gordes-le-Haut', 'gordes')).toBe(3);
    expect(pertinence('Château de Gordes', 'gordes')).toBe(2);
    expect(pertinence('Regordes', 'gordes')).toBe(1);
    expect(pertinence('Carcassonne', 'gordes')).toBe(0);
  });

  it('ne répond pas à une recherche vide', () => {
    expect(pertinence('Gordes', '   ')).toBe(0);
  });
});

describe('recherche', () => {
  it('attend deux caractères avant de répondre', () => {
    expect(search([lieu('Gordes')], 'g')).toEqual([]);
    expect(search([lieu('Gordes')], 'go')).toHaveLength(1);
    expect(MIN_CARACTERES).toBe(2);
  });

  it('trouve un lieu par sa COMMUNE quand son nom ne dit rien', () => {
    // Le vrai cas : les falaises d'Étretat sont fichées « Porte d'Aval ».
    // Chercher sur le seul nom ne rendait rien.
    const trouves = search([lieu("Porte d'Aval", { communeName: 'Étretat' })], 'etretat');
    expect(trouves).toHaveLength(1);
    expect(trouves[0].par).toBe('lieu');
  });

  it('fait passer le nom avant la commune', () => {
    // Qui tape « gordes » cherche le village, pas les lieux qui s'y trouvent.
    const village = lieu('Gordes', { communeName: 'Gordes' });
    const dedans = lieu('Abbaye de Sénanque', { communeName: 'Gordes', score: 900 });
    const trouves = search([dedans, village], 'gordes');
    expect(trouves[0].place.name).toBe('Gordes');
    expect(trouves[0].par).toBe('nom');
  });

  it('départage par la notoriété à pertinence égale', () => {
    const petit = lieu('Château de Vaux', { score: 10 });
    const grand = lieu('Château de Chambord', { score: 200 });
    const trouves = search([petit, grand], 'chateau');
    expect(trouves[0].place.name).toBe('Château de Chambord');
  });

  it('trouve aussi par département', () => {
    const trouves = search([lieu('Pointe du Raz', { departement: 'Finistère' })], 'finistere');
    expect(trouves[0].par).toBe('lieu');
  });

  it('ne rend rien quand rien ne correspond', () => {
    expect(search([lieu('Gordes')], 'zzz')).toEqual([]);
  });

  it('borne le nombre de résultats', () => {
    const beaucoup = Array.from({ length: 100 }, (_, i) => lieu(`Château ${i}`));
    expect(search(beaucoup, 'chateau', 10)).toHaveLength(10);
  });

  it('supporte un lieu sans commune ni département', () => {
    // Trente-neuf lieux du catalogue n'ont pas de commune.
    expect(search([lieu('Mont Blanc')], 'mont')).toHaveLength(1);
  });
});

describe('un mot générique se cherche dans les deux langues', () => {
  it('trouve un lieu italien par le mot français', () => {
    // Cinq cent soixante et onze noms du catalogue italien gardent leur mot
    // italien, parce que c'est ainsi qu'on les dit : la Piazza dei Miracoli,
    // le Palazzo Vecchio. Personne ne tape « piazza » en cherchant une place.
    const places = [lieu('Piazza dei Miracoli'), lieu('Palazzo Vecchio'), lieu('Ponte Vecchio')];
    expect(search(places, 'place').map((m) => m.place.name)).toContain('Piazza dei Miracoli');
    expect(search(places, 'palais').map((m) => m.place.name)).toContain('Palazzo Vecchio');
    expect(search(places, 'pont').map((m) => m.place.name)).toContain('Ponte Vecchio');
  });

  it('trouve un lieu italien par le saint français', () => {
    const places = [lieu('Basilique San Francesco'), lieu('Chiesa di Santa Chiara')];
    expect(search(places, 'saint').map((m) => m.place.name)).toContain('Basilique San Francesco');
    expect(search(places, 'sainte').map((m) => m.place.name)).toContain('Chiesa di Santa Chiara');
  });

  it('ne fait JAMAIS passer une traduction devant une lecture directe', () => {
    // Le garde-fou, et il a été payé : sans plafond, « san » traduisait en
    // « saint » et rendait 217 résultats français là où il y en avait 13.
    // Sancerre disparaissait sous deux cents « Saint-… ».
    const places = [
      lieu('Saint-Guilhem-le-Désert', { score: 180 }),
      lieu('Saint-Véran', { score: 167 }),
      lieu('Sancerre', { score: 155 }),
    ];
    expect(search(places, 'san')[0].place.name).toBe('Sancerre');
    // Les Saint restent trouvables — derrière, ce qui est leur juste place.
    expect(search(places, 'san')).toHaveLength(3);
  });

  it('ne traduit que le mot ENTIER', () => {
    // « pon » n'a pas besoin d'être traduit : le préfixe atteint déjà
    // « Ponte ». Traduire un préfixe ferait dire à la table plus qu'elle ne
    // sait — et « la » deviendrait un lac.
    expect(variantes('pont')).toEqual(['pont', 'ponte']);
    expect(variantes('pon')).toEqual(['pon']);
    expect(variantes('lac')).toEqual(['lac', 'lago']);
    expect(variantes('la')).toEqual(['la']);
  });

  it('laisse intact ce que la recherche trouvait déjà', () => {
    // Une traduction ne peut que faire MONTER une note : le classement
    // français d'avant doit se retrouver à l'identique.
    const places = [lieu('Pont du Gard', { score: 200 }), lieu('Pont-Aven', { score: 150 }), lieu('Ponte Vecchio', { score: 100 })];
    expect(search(places, 'pont').map((m) => m.place.name)).toEqual([
      'Pont du Gard', 'Pont-Aven', 'Ponte Vecchio',
    ]);
  });
});

describe('une recherche à plusieurs mots', () => {
  it('trouve la Piazza dei Miracoli en tapant « place dei miracoli »', () => {
    // Le cas rapporté. La phrase entière ne pouvait pas répondre : le
    // glossaire ne traduit que ce qu'on tape EN ENTIER, et « place dei
    // miracoli » n'y est pas. Chaque mot doit donc être jugé séparément.
    const places = [lieu('Piazza dei Miracoli', { communeName: 'Pisa' })];
    expect(search(places, 'place dei miracoli')).toHaveLength(1);
    expect(search(places, 'piazza miracoli')).toHaveLength(1);
  });

  it('tolère cinq lettres communes pour un nom propre traduit de tête', () => {
    // « Place des miracles » est une traduction du NOM PROPRE, que le
    // glossaire ne peut pas porter — traduire les noms propres serait sans
    // fin. Cinq lettres communes suffisent : « mirac ».
    const places = [lieu('Piazza dei Miracoli', { communeName: 'Pisa' })];
    expect(search(places, 'place des miracles')).toHaveLength(1);
  });

  it('cherche aussi dans la COMMUNE, mot par mot', () => {
    // La basilique d'Assise ne porte pas « Assise » dans son nom : c'est sa
    // commune qui le dit, et en italien.
    const places = [lieu('Basilique Saint-François', { communeName: 'Assisi' })];
    expect(search(places, 'basilique assise')).toHaveLength(1);
  });

  it('exige que TOUS les mots répondent', () => {
    const places = [lieu('Piazza dei Miracoli', { communeName: 'Pisa' })];
    expect(search(places, 'place de rome')).toHaveLength(0);
    expect(search(places, 'miracoli venise')).toHaveLength(0);
  });

  it('ne se déclenche que si la phrase entière a échoué', () => {
    // Le repli AJOUTE des résultats, il n'en déplace aucun : « pont du gard »
    // se lit d'un bloc, et son classement ne doit pas bouger d'un cran.
    const places = [
      lieu('Pont du Gard', { score: 200 }),
      lieu('Pont-Aven', { score: 150 }),
    ];
    expect(search(places, 'pont du gard').map((m) => m.place.name)).toEqual(['Pont du Gard']);
  });

  it('classe un accord mot à mot APRÈS une lecture directe', () => {
    const places = [
      lieu('Piazza dei Miracoli', { score: 10 }),
      lieu('Place des Miracles de Lourdes', { score: 5 }),
    ];
    // Le second contient la phrase telle quelle : il passe devant, malgré un
    // score cinq fois moindre.
    expect(search(places, 'place des miracles')[0].place.name)
      .toBe('Place des Miracles de Lourdes');
  });
});


/**
 * Le trait d'union, que personne ne tape.
 *
 * « basilique saint pierre » ne trouvait pas « Basilique Saint-Pierre » comme
 * une PHRASE : ni égale, ni commençant par, ni contenant. Le lieu ne revenait
 * que par le repli mot à mot, à la note la plus basse — donc derrière
 * « Basilique Saint-Pierre-aux-Liens », qui y arrivait par le même chemin.
 */
describe('les séparateurs ne comptent pas', () => {
  const lieu = (name: string, score = 0): Place =>
    ({ id: name, slug: name, name, themeId: 'cathedrales', lat: 0, lon: 0, score } as unknown as Place);

  it('lit un nom à trait d’union tapé avec des espaces', () => {
    expect(fold('Basilique Saint-Pierre')).toBe('basilique saint pierre');
    expect(fold("Île d'Yeu")).toBe('ile d yeu');
    expect(fold('  Mont   St-Michel  ')).toBe('mont st michel');
  });

  it('reconnaît alors le nom EXACT, et le classe devant', () => {
    const trouves = search(
      [lieu('Basilique Saint-Pierre-aux-Liens', 111), lieu('Basilique Saint-Pierre', 188)],
      'basilique saint pierre',
    );
    expect(trouves.map((m) => m.place.name)).toEqual([
      'Basilique Saint-Pierre',
      'Basilique Saint-Pierre-aux-Liens',
    ]);
    // Nom exact contre « commence par » : quatre contre trois, doublés.
    expect(trouves[0].note).toBe(8);
    expect(trouves[1].note).toBe(6);
  });

  it('trouve encore avec le trait d’union, au même rang', () => {
    const trouves = search(
      [lieu('Basilique Saint-Pierre-aux-Liens', 111), lieu('Basilique Saint-Pierre', 188)],
      'basilique saint-pierre',
    );
    expect(trouves[0].place.name).toBe('Basilique Saint-Pierre');
  });
});
