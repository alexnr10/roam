import { useSyncExternalStore } from 'react';

import { surChangement, versionDuCatalogue } from '../data/catalog';

/**
 * Se redessiner quand le catalogue change de pays.
 *
 * `places`, `collections` et `areas` sont des liens vivants : leur contenu
 * suit tout seul. Ce qui ne suit pas, c'est REACT — il ne redessine que ce
 * dont l'état a changé, et de son point de vue rien n'a changé. D'où ce
 * crochet, que tout écran lisant le catalogue doit appeler.
 *
 * Il rend la version, à mettre dans les dépendances d'un `useMemo` qui dérive
 * du catalogue.
 */
export function useCatalogue(): number {
  return useSyncExternalStore(surChangement, versionDuCatalogue, versionDuCatalogue);
}
