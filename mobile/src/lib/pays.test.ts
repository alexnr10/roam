import { dansLEmprise, paysAAdopter, type PaysConnu } from './pays';

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
