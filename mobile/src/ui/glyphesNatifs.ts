// Fichier ENGENDRÉ par `node scripts/build-glyphes.mjs` — ne pas modifier à la main.
//
// Les vingt-trois icônes de thèmes, en images, pour la couche de symboles de
// la carte native. Leur source est `src/ui/themeIcons.tsx` : c'est là qu'on
// modifie un tracé, et ce script réécrit ce fichier et les PNG voisins.

import type { ImageRequireSource } from 'react-native';

export const GLYPHES: Record<string, ImageRequireSource> = {
  'chateaux': require('../../assets/glyphes/chateaux.png'),
  'abbayes': require('../../assets/glyphes/abbayes.png'),
  'cathedrales': require('../../assets/glyphes/cathedrales.png'),
  'villages': require('../../assets/glyphes/villages.png'),
  'sommets': require('../../assets/glyphes/sommets.png'),
  'cascades': require('../../assets/glyphes/cascades.png'),
  'gorges': require('../../assets/glyphes/gorges.png'),
  'plages': require('../../assets/glyphes/plages.png'),
  'grottes': require('../../assets/glyphes/grottes.png'),
  'lacs': require('../../assets/glyphes/lacs.png'),
  'ponts': require('../../assets/glyphes/ponts.png'),
  'phares': require('../../assets/glyphes/phares.png'),
  'monuments': require('../../assets/glyphes/monuments.png'),
  'musees': require('../../assets/glyphes/musees.png'),
  'maisons': require('../../assets/glyphes/maisons.png'),
  'jardins': require('../../assets/glyphes/jardins.png'),
  'megalithes': require('../../assets/glyphes/megalithes.png'),
  'iles': require('../../assets/glyphes/iles.png'),
  'volcans': require('../../assets/glyphes/volcans.png'),
  'forets': require('../../assets/glyphes/forets.png'),
  'cirques': require('../../assets/glyphes/cirques.png'),
  'dunes-marais': require('../../assets/glyphes/dunes-marais.png'),
  'rochers': require('../../assets/glyphes/rochers.png'),
};
