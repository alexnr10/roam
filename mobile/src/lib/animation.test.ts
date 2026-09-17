import { MARGE_DU_FILET, animer, type Horloge } from './animation';

/** Une horloge qu'on fait avancer à la main. */
function horlogeDeBanc() {
  let t = 0;
  const images = new Map<number, () => void>();
  const filets = new Map<number, { suite: () => void; quand: number }>();
  let jeton = 0;
  const horloge: Horloge = {
    maintenant: () => t,
    image: (suite) => {
      images.set(++jeton, suite);
      return jeton;
    },
    annulerImage: (j) => {
      images.delete(j);
    },
    filet: (suite, delai) => {
      filets.set(++jeton, { suite, quand: t + delai });
      return jeton as unknown as ReturnType<typeof setTimeout>;
    },
    annulerFilet: (j) => {
      filets.delete(j as unknown as number);
    },
  };
  return {
    horloge,
    /** Avance le temps et joue les images ET les filets échus. */
    avancer(ms: number) {
      t += ms;
      for (const [j, suite] of [...images]) {
        images.delete(j);
        suite();
      }
      for (const [j, { suite, quand }] of [...filets]) {
        if (quand <= t) {
          filets.delete(j);
          suite();
        }
      }
    },
    enAttente: () => images.size + filets.size,
  };
}

describe('animer', () => {
  it('appelle surImage puis surFin, et finit à un', () => {
    const banc = horlogeDeBanc();
    const vus: number[] = [];
    let finie = false;
    animer(100, (a) => vus.push(a), () => { finie = true; }, banc.horloge);
    banc.avancer(50);
    expect(vus).toEqual([0.5]);
    expect(finie).toBe(false);
    banc.avancer(60);
    expect(vus[vus.length - 1]).toBe(1);
    expect(finie).toBe(true);
  });

  it('aboutit par le FILET quand les images ne viennent pas', () => {
    // Un onglet en arrière-plan ne reçoit pas d'images : sans filet,
    // l'animation resterait à mi-course pour toujours.
    const banc = horlogeDeBanc();
    let finie = false;
    const vus: number[] = [];
    const a = animer(100, (x) => vus.push(x), () => { finie = true; }, banc.horloge);
    // On coupe l'arrivée des images en avançant d'un coup au-delà du filet.
    banc.avancer(100 + MARGE_DU_FILET);
    expect(finie).toBe(true);
    expect(vus[vus.length - 1]).toBe(1);
    expect(a).toBeDefined();
  });

  it('ARRÊTÉE, elle n’appelle NI surImage(1) NI surFin — même après le filet', () => {
    // LE défaut. Le filet d'un fondu annulé continuait de courir, et sa fin
    // vidait la source de la carte : en arrivant dans une région qu'on venait
    // d'ouvrir, les lieux disparaissaient. Il fallait quitter la région et y
    // revenir pour les revoir.
    const banc = horlogeDeBanc();
    let finie = false;
    const vus: number[] = [];
    const animation = animer(160, (a) => vus.push(a), () => { finie = true; }, banc.horloge);
    banc.avancer(40);
    animation.arreter();
    // Bien au-delà de la durée ET de la marge du filet.
    banc.avancer(1000);
    expect(finie).toBe(false);
    expect(vus).not.toContain(1);
    expect(banc.enAttente()).toBe(0);
  });

  it('n’aboutit qu’une fois, quoi qu’on lui demande', () => {
    const banc = horlogeDeBanc();
    let fins = 0;
    const animation = animer(100, () => {}, () => { fins += 1; }, banc.horloge);
    animation.finir();
    animation.finir();
    animation.arreter();
    banc.avancer(1000);
    expect(fins).toBe(1);
  });

  it('ne laisse rien derrière elle', () => {
    // Ni image ni filet en attente : un filet survivant rappellerait une carte
    // qui n'existe plus.
    const banc = horlogeDeBanc();
    animer(100, () => {}, undefined, banc.horloge).arreter();
    expect(banc.enAttente()).toBe(0);
  });
});
