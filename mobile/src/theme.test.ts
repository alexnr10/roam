import { themes } from './data/catalog';
import { themeEmoji } from './theme';

describe('themeEmoji', () => {
  it('couvre TOUS les thèmes du catalogue', () => {
    // L'emoji est le repli quand un lieu n'a pas de photo ou qu'elle ne charge
    // pas. Dix thèmes sans entrée affichaient un 📍 anonyme, et le quadrillage
    // en montrait des grilles entières.
    const sans = themes.map((theme) => theme.id).filter((id) => !themeEmoji[id]);
    expect(sans).toEqual([]);
  });
});
