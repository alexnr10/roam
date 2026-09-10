/**
 * La configuration Expo, dérivée d'`app.json`.
 *
 * `app.json` reste la source : identifiants, greffons, icônes, et la référence
 * des catalogues servis. Ce fichier ne fait qu'UNE chose de plus — poser le
 * préfixe d'URL quand le site est publié ailleurs qu'à la racine d'un domaine.
 *
 * GitHub Pages sert un dépôt de projet sous `https://<compte>.github.io/roam/`.
 * Sans préfixe, l'export écrit `src="/_expo/..."` : chaque fichier est alors
 * cherché à la racine du domaine, et la page reste blanche sans un mot
 * d'explication.
 *
 * Le préfixe vient de l'environnement plutôt que du fichier : l'aperçu local,
 * lui, est servi à la racine, et un préfixe écrit en dur y casserait tout.
 *
 *     npm run export:web      → à la racine, pour regarder chez soi
 *     npm run export:pages    → sous /roam, pour publier
 */
const app = require('./app.json');

module.exports = () => {
  const prefixe = (process.env.ROAM_BASE_URL || '').trim();
  if (!prefixe) return app.expo;
  return {
    ...app.expo,
    experiments: { ...(app.expo.experiments || {}), baseUrl: prefixe },
  };
};
