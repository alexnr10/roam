import type { Place } from '../types';

/**
 * Retrouver un lieu qu'on a visité, sans se souvenir de son nom exact.
 *
 * C'est le problème le plus concret de l'application : personne ne se rappelle
 * ce qu'il a visité en parcourant deux mille fiches. On se souvient en
 * RECONNAISSANT — et pour reconnaître, il faut d'abord pouvoir taper trois
 * lettres.
 *
 * Trois décisions, chacune tirée d'un vrai raté du catalogue :
 *
 * 1. **La commune compte autant que le nom.** Les falaises d'Étretat sont
 *    fichées « Porte d'Aval » ; chercher « étretat » sur le seul nom ne rend
 *    rien. Le lieu se cherche par là où l'on est allé, pas par le libellé que
 *    Wikidata lui donne.
 * 2. **Les accents et la casse ne comptent pas.** On tape « chateau » sur un
 *    clavier de téléphone, pas « Château ».
 * 3. **Un début de mot vaut mieux qu'un milieu.** « Marie » doit rendre
 *    « Sainte-Marie-Majeure » avant « Les Saintes-Maries-de-la-Mer ».
 */

export type Match = {
  place: Place;
  /** Ce qui a répondu : le nom du lieu, ou l'endroit où il se trouve. */
  par: 'nom' | 'lieu';
};

const VIDES = new Set([
  'de', 'des', 'du', 'la', 'le', 'les', 'l', 'd', 'et', 'aux', 'au', 'sur',
  'sous', 'en', 'a',
  // Les mêmes, en italien : « Piazza dei Miracoli », « Ponte di Veja ».
  // Sans eux, « place dei miracoli » exigeait que « dei » réponde aussi, et
  // un lieu nommé « Piazza del Duomo » n'aurait jamais pu convenir.
  'di', 'del', 'della', 'dei', 'degli', 'delle', 'dal', 'dalla', 'il', 'lo',
  'gli', 'alla', 'ai', 'sul', 'sulla',
]);

/** Minuscules sans accents : « Château » et « chateau » doivent se répondre. */
export function fold(texte: string): string {
  return texte
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase();
}

/**
 * Les mots génériques, d'une langue à l'autre.
 *
 * Un catalogue italien porte les noms que Wikidata donne en français, et
 * beaucoup le sont déjà — « Tour de Pise », « Lac de Côme », « Palais
 * Farnèse ». Mais cinq cent soixante et onze noms sur deux mille soixante-seize
 * gardent leur mot italien, parce que c'est ainsi qu'on les dit en français :
 * le Ponte Vecchio, la Piazza dei Miracoli, le Monte Argentario.
 *
 * Personne ne tape « ponte » en cherchant un pont. Cette table fait donc ce
 * qu'un lecteur ferait de tête : elle traduit LE MOT QU'ON TAPE, dans les deux
 * sens, et la recherche essaie chaque variante.
 *
 * Elle ne contient que des mots GÉNÉRIQUES — ce qui désigne une catégorie de
 * lieu, jamais un nom propre. Traduire les noms propres serait une autre
 * affaire, et une mauvaise idée : « Livourne » et « Livorno » sont deux
 * graphies du même nom, pas deux mots.
 */
const EQUIVALENTS: Record<string, string[]> = {
  // Le bâti
  eglise: ['chiesa'], chiesa: ['eglise'],
  cathedrale: ['duomo', 'cattedrale'], duomo: ['cathedrale'], cattedrale: ['cathedrale'],
  basilique: ['basilica'], basilica: ['basilique'],
  abbaye: ['abbazia', 'badia'], abbazia: ['abbaye'], badia: ['abbaye'],
  couvent: ['convento'], convento: ['couvent'],
  cloitre: ['chiostro'], chiostro: ['cloitre'],
  ermitage: ['eremo'], eremo: ['ermitage'],
  sanctuaire: ['santuario'], santuario: ['sanctuaire'],
  temple: ['tempio'], tempio: ['temple'],
  chateau: ['castello'], castello: ['chateau'],
  palais: ['palazzo'], palazzo: ['palais'],
  forteresse: ['rocca', 'fortezza'], rocca: ['forteresse'], fortezza: ['forteresse'],
  tour: ['torre'], torre: ['tour'],
  pont: ['ponte'], ponte: ['pont'],
  porte: ['porta'], porta: ['porte'],
  musee: ['museo'], museo: ['musee'],
  theatre: ['teatro'], teatro: ['theatre'],
  fontaine: ['fontana'], fontana: ['fontaine'],
  thermes: ['terme'], terme: ['thermes'],
  phare: ['faro'], faro: ['phare'],
  place: ['piazza'], piazza: ['place'],
  jardin: ['giardino', 'orto'], giardino: ['jardin'], orto: ['jardin'],
  parc: ['parco'], parco: ['parc'],
  village: ['borgo', 'paese'], borgo: ['village'], bourg: ['borgo'],
  tombeau: ['tomba'], tomba: ['tombeau'],
  // Le paysage
  lac: ['lago'], lago: ['lac'],
  mont: ['monte'], monte: ['mont'], montagne: ['montagna'], montagna: ['montagne'],
  ile: ['isola'], isola: ['ile'],
  grotte: ['grotta'], grotta: ['grotte'],
  cascade: ['cascata'], cascata: ['cascade'],
  plage: ['spiaggia'], spiaggia: ['plage'],
  golfe: ['golfo'], golfo: ['golfe'],
  baie: ['baia'], baia: ['baie'],
  cap: ['capo'], capo: ['cap'],
  vallee: ['valle', 'val'], valle: ['vallee'],
  gorges: ['gole'], gole: ['gorges'],
  fleuve: ['fiume'], riviere: ['fiume'], fiume: ['fleuve'],
  source: ['sorgente', 'fonte'], sorgente: ['source'],
  col: ['passo'], passo: ['col'],
  volcan: ['vulcano'], vulcano: ['volcan'],
  // Les saints — « saint françois » doit rendre « San Francesco ».
  saint: ['san', 'santo', 'sant'], sainte: ['santa', 'sant'],
  san: ['saint'], santo: ['saint'], santa: ['sainte'], sant: ['saint'],
};

/**
 * Ce qu'on tape, et ce que ça pourrait vouloir dire dans l'autre langue.
 *
 * La traduction ne s'applique qu'au mot ENTIER : « pont » donne « ponte »,
 * mais « pon » ne donne rien — et n'en a pas besoin, puisque le préfixe
 * atteint déjà « Ponte Vecchio ». Traduire un préfixe ferait dire à la table
 * plus qu'elle ne sait.
 */
export function variantes(recherche: string): string[] {
  const q = fold(recherche).trim();
  if (!q) return [];
  const traductions = EQUIVALENTS[q] ?? [];
  return traductions.length ? [q, ...traductions] : [q];
}

/**
 * Le plafond d'une correspondance obtenue par TRADUCTION.
 *
 * Une traduction est une hypothèse sur l'intention, pas une lecture du texte :
 * elle doit pouvoir faire trouver, jamais faire passer devant.
 *
 * Sans ce plafond, « san » traduisait en « saint » et rendait deux cent
 * dix-sept résultats là où il y en avait treize : Sancerre, Sanary, le domaine
 * de George Sand disparaissaient sous deux cents « Saint-… » mieux notés
 * qu'eux. Le plafond les remet à leur place — les Saint restent trouvables,
 * derrière ce qui commence vraiment par « san ».
 */
const PLAFOND_TRADUIT = 2;

/** Les mots porteurs d'un texte, ponctuation et articles ôtés. */
function mots(texte: string): string[] {
  return fold(texte)
    .replace(/[^a-z0-9]+/g, ' ')
    .split(' ')
    .filter((mot) => mot.length > 0 && !VIDES.has(mot));
}

/**
 * À quel point ce texte répond à la recherche. `0` = pas du tout.
 *
 * L'échelle est grossière à dessein : elle sépare trois cas — le texte
 * COMMENCE par ce qu'on tape, un de ses MOTS commence par ce qu'on tape, ou
 * le texte le contient quelque part. Au-delà, c'est la notoriété du lieu qui
 * départage, et elle le fait mieux qu'une heuristique.
 */
export function pertinence(texte: string, recherche: string): number {
  const cible = fold(texte);
  // Chaque variante est jugée, et la meilleure l'emporte. Une traduction ne
  // peut donc que faire MONTER une note, jamais la faire baisser : ce que la
  // recherche trouvait avant, elle le trouve toujours, au même rang.
  let meilleure = 0;
  const formes = variantes(recherche);
  for (const [rang, q] of formes.entries()) {
    let note = 0;
    if (cible === q) note = 4;
    else if (cible.startsWith(q)) note = 3;
    else if (mots(texte).some((mot) => mot.startsWith(q))) note = 2;
    else if (cible.includes(q)) note = 1;
    // La première forme est CE QU'ON A TAPÉ : elle garde l'échelle entière.
    // Les suivantes sont des traductions, et plafonnent.
    if (rang > 0) note = Math.min(note, PLAFOND_TRADUIT);
    if (note > meilleure) meilleure = note;
  }
  return meilleure;
}

/**
 * Combien de lettres deux mots doivent partager pour être tenus pour le même.
 *
 * C'est la seule règle APPROXIMATIVE de la recherche, et elle est là pour un
 * cas précis : le nom propre qu'on traduit de tête. « Place des miracles »
 * pour la Piazza dei Miracoli, « Saint François d'Assise » pour la basilique
 * d'Assisi. Le glossaire ne peut rien pour ceux-là — traduire les noms propres
 * serait sans fin.
 *
 * Cinq, et pas moins : « miracles » et « miracoli » partagent « mirac »,
 * « assise » et « Assisi » partagent « assis », « botanique » et « botanico »
 * partagent « botani ». À quatre, « cathédrale » rejoindrait « cathare » et
 * « Cannes » rejoindrait « Cannobio ».
 */
const LETTRES_COMMUNES = 5;

/** Combien de lettres deux mots ont en commun, depuis le début. */
function prefixeCommun(a: string, b: string): number {
  const court = Math.min(a.length, b.length);
  let n = 0;
  while (n < court && a[n] === b[n]) n += 1;
  return n;
}

/**
 * Chaque mot de la recherche répond-il QUELQUE PART dans ce qu'on lui donne ?
 *
 * La recherche jugeait la phrase entière d'un bloc : « Piazza dei Miracoli »
 * répondait à « piazza dei miracoli », qu'elle contient mot pour mot, mais pas
 * à « place dei miracoli » — le glossaire ne traduit que ce qu'on tape EN
 * ENTIER, et « place dei miracoli » n'est pas dans le glossaire.
 *
 * Ici chaque mot est jugé séparément, contre le nom ET la commune, et tous
 * doivent répondre. C'est ce qui permet à « basilique assise » de trouver une
 * basilique dont la commune est Assisi et dont le nom ne dit pas « Assise ».
 *
 * Rend `2` quand tous les mots répondent exactement, `1` quand l'un d'eux n'a
 * répondu qu'à cinq lettres près, `0` sinon.
 */
export function pertinenceParMots(textes: string[], recherche: string): number {
  const demandes = mots(recherche);
  if (demandes.length < 2) return 0;
  const disponibles = textes.flatMap((texte) => mots(texte));
  if (disponibles.length === 0) return 0;

  let exact = true;
  for (const demande of demandes) {
    const formes = variantes(demande);
    if (formes.some((forme) => disponibles.some((mot) => mot.startsWith(forme)))) continue;
    if (formes.some((forme) =>
      disponibles.some((mot) => prefixeCommun(mot, forme) >= LETTRES_COMMUNES))) {
      exact = false;
      continue;
    }
    return 0;
  }
  return exact ? 2 : 1;
}

/** Combien de caractères il faut avoir tapés pour qu'une recherche ait un sens. */
export const MIN_CARACTERES = 2;

/**
 * Les lieux qui répondent, les plus pertinents d'abord.
 *
 * Le nom l'emporte toujours sur la commune : qui tape « gordes » cherche le
 * village, pas les six lieux qui s'y trouvent. Mais la commune reste, plus
 * bas — c'est elle qui sauve Étretat.
 */
export function search(places: Place[], recherche: string, limite = 40): Match[] {
  const q = recherche.trim();
  if (q.length < MIN_CARACTERES) return [];

  const notes: Array<{ match: Match; note: number; score: number }> = [];
  for (const place of places) {
    const parNom = pertinence(place.name, q);
    // La commune vaut un cran de moins que le nom, à pertinence égale : elle
    // répond quand le nom ne dit rien, elle ne le remplace pas.
    const ou = [place.communeName, place.departement].filter(Boolean) as string[];
    const parLieu = Math.max(0, ...ou.map((texte) => pertinence(texte, q)));

    // La phrase d'abord, mot à mot ensuite : une recherche à plusieurs mots
    // que la phrase ne sait pas lire n'est pas forcément une recherche vide.
    // Le repli ne peut donc qu'AJOUTER des résultats, jamais en déplacer un.
    const parMots =
      parNom === 0 && parLieu === 0
        ? pertinenceParMots([place.name, ...ou], q)
        : 0;

    if (parNom === 0 && parLieu === 0 && parMots === 0) continue;
    const gagnant = parNom >= parLieu ? 'nom' : 'lieu';
    notes.push({
      match: { place, par: parMots > 0 ? 'nom' : gagnant },
      note: parMots > 0
        ? parMots
        : gagnant === 'nom' ? parNom * 2 : parLieu * 2 - 1,
      score: place.score ?? 0,
    });
  }

  notes.sort((a, b) =>
    b.note - a.note
    || b.score - a.score
    || a.match.place.name.localeCompare(b.match.place.name, 'fr'));
  return notes.slice(0, limite).map((entree) => entree.match);
}
