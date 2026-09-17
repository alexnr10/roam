import { dansLEmprise, paysAAdopter, paysEnglobant, type PaysConnu } from './pays';

const FR: PaysConnu = { code: 'FR', name: 'France', emprises: [[-5, 42, 8, 51]] };
const IT: PaysConnu = { code: 'IT', name: 'Italie', emprises: [[6, 36, 19, 47]] };
const CONNUS = [FR, IT];

describe('dansLEmprise', () => {
  it('reconnaît un point dedans et un point dehors', () => {
    expect(dansLEmprise(2.35, 48.85, FR.emprises)).toBe(true);
    expect(dansLEmprise(12.5, 41.9, FR.emprises)).toBe(false);
  });

  it('accepte plusieurs boîtes — un pays a des îles', () => {
    const outreMer: PaysConnu['emprises'] = [[-5, 42, 8, 51], [55, -22, 56, -20]];
    expect(dansLEmprise(55.5, -21, outreMer)).toBe(true);
  });
});

describe('paysAAdopter', () => {
  it('ne bascule pas tant qu’on est chez soi', () => {
    expect(paysAAdopter(2.35, 48.85, 'FR', CONNUS)).toBeNull();
  });

  it('bascule quand on est sorti et qu’un seul pays répond', () => {
    expect(paysAAdopter(12.5, 41.9, 'FR', CONNUS)).toBe('IT');
  });

  it('ne bascule PAS dans la zone que deux pays se partagent', () => {
    // LE confort : les Alpes sont dans la boîte de la Savoie ET dans celle du
    // Piémont. Sans cette règle, se promener autour du mont Blanc ferait
    // clignoter le catalogue à chaque mouvement de doigt.
    const montBlanc = [6.86, 45.83] as const;
    expect(dansLEmprise(montBlanc[0], montBlanc[1], FR.emprises)).toBe(true);
    expect(dansLEmprise(montBlanc[0], montBlanc[1], IT.emprises)).toBe(true);
    expect(paysAAdopter(montBlanc[0], montBlanc[1], 'FR', CONNUS)).toBeNull();
    expect(paysAAdopter(montBlanc[0], montBlanc[1], 'IT', CONNUS)).toBeNull();
  });

  it('ne devine pas entre deux candidats', () => {
    // Un point hors du pays courant mais dans deux voisins : deviner serait
    // pire que ne rien faire. On attend que la carte tranche.
    const ES: PaysConnu = { code: 'ES', name: 'Espagne', emprises: [[10, 40, 14, 43]] };
    expect(paysAAdopter(12, 41.5, 'FR', [FR, IT, ES])).toBeNull();
  });

  it('ignore un pays dont on ne connaît pas l’emprise', () => {
    // Un pays annoncé sans contours ne peut pas être adopté par la carte : il
    // resterait à le choisir à la main. Mieux vaut ne rien faire que d'y
    // envoyer l'utilisateur au hasard.
    const sansEmprise: PaysConnu = { code: 'DE', name: 'Allemagne', emprises: [] };
    expect(paysAAdopter(20, 60, 'FR', [FR, sansEmprise])).toBeNull();
  });

  it('rend null quand le pays courant est inconnu du manifeste', () => {
    expect(paysAAdopter(12.5, 41.9, 'ZZ', CONNUS)).toBe('IT');
  });
});

/**
 * L'enclave : un pays DANS le pays courant.
 *
 * On ne sort jamais de l'Italie en entrant au Vatican. L'hystérésis, qui
 * protège la frontière franco-italienne du clignotement, répondait donc
 * « reste en Italie » au-dessus même de Saint-Pierre, et le Vatican était
 * inatteignable par la carte — mesuré sur les emprises réellement servies.
 */
describe('une enclave', () => {
  // Les emprises RÉELLES de `catalogues/index.json` : celle du Vatican est
  // celle de ses dix-neuf lieux, celle de la province de Rome contient Rome.
  const VA: PaysConnu = { code: 'VA', name: 'Vatican', emprises: [[12.4483, 41.9019, 12.4575, 41.9064]] };
  const ITALIE: PaysConnu = { code: 'IT', name: 'Italie', emprises: [[11.7, 41.3, 13.3, 42.3]] };
  const SAINT_PIERRE = [12.4534, 41.9022] as const;

  it('est bien DANS le pays courant, ce qui bloquait tout', () => {
    expect(dansLEmprise(SAINT_PIERRE[0], SAINT_PIERRE[1], ITALIE.emprises)).toBe(true);
    expect(dansLEmprise(SAINT_PIERRE[0], SAINT_PIERRE[1], VA.emprises)).toBe(true);
  });

  it('s’adopte quand même : y entrer est un geste, pas un tremblement', () => {
    expect(paysAAdopter(SAINT_PIERRE[0], SAINT_PIERRE[1], 'IT', [ITALIE, VA])).toBe('VA');
  });

  it('se quitte en en sortant', () => {
    // Le Colisée : hors du Vatican, dans l'Italie. La règle du candidat unique
    // suffit, elle n'a pas changé.
    expect(paysAAdopter(12.4922, 41.8902, 'VA', [ITALIE, VA])).toBe('IT');
  });

  it('ne fait PAS basculer un voisin qui déborde', () => {
    // La France n'est pas dans la boîte italienne : la frontière garde son
    // hystérésis, et le mont Blanc ne clignote pas.
    expect(paysAAdopter(6.86, 45.83, 'FR', CONNUS)).toBeNull();
    expect(paysAAdopter(6.86, 45.83, 'IT', CONNUS)).toBeNull();
  });

  it('ne devine pas entre deux enclaves superposées', () => {
    const AUTRE: PaysConnu = { code: 'XX', name: 'Autre', emprises: [[12.44, 41.90, 12.46, 41.91]] };
    expect(paysAAdopter(SAINT_PIERRE[0], SAINT_PIERRE[1], 'IT', [ITALIE, VA, AUTRE])).toBeNull();
  });
});


/**
 * Sortir d'une enclave : le dernier cran de la pastille de retour.
 *
 * Depuis le Vatican, reculer n'a pas de sens — le pays tient dans l'écran, et
 * « revenir au pays, en entier » refaisait ce que le cran précédent venait de
 * faire : « ‹ Vatican │ Vatican », deux fois de suite.
 */
describe('paysEnglobant', () => {
  const VA: PaysConnu = { code: 'VA', name: 'Vatican', emprises: [[12.4483, 41.9019, 12.4575, 41.9064]] };
  const ITALIE: PaysConnu = { code: 'IT', name: 'Italie', emprises: [[11.7, 41.3, 13.3, 42.3]] };

  it('rend le pays qui contient l’enclave', () => {
    expect(paysEnglobant('VA', [ITALIE, VA])).toBe('IT');
  });

  it('ne rend rien pour un pays qui n’est l’enclave de personne', () => {
    expect(paysEnglobant('IT', [ITALIE, VA, FR])).toBeNull();
    expect(paysEnglobant('FR', CONNUS)).toBeNull();
  });

  it('ne devine pas entre deux hôtes possibles', () => {
    const AUTRE: PaysConnu = { code: 'XX', name: 'Autre', emprises: [[11, 41, 14, 43]] };
    expect(paysEnglobant('VA', [ITALIE, AUTRE, VA])).toBeNull();
  });

  it('ne rend rien sans emprise, des deux côtés', () => {
    expect(paysEnglobant('ZZ', [ITALIE, VA])).toBeNull();
    const sans: PaysConnu = { code: 'SM', name: 'Saint-Marin', emprises: [] };
    expect(paysEnglobant('SM', [ITALIE, sans])).toBeNull();
  });
});
