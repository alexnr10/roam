"""Construction des collections et attribution des niveaux.

Règle cardinale : une collection n'existe que si elle a assez de lieux pour être
une collection. Sans ce garde-fou, croiser N thèmes par M échelons géographiques
produit des milliers de collections vides du type « Cascades de la Creuse :
2 lieux » — ce qui casse le jeu au lieu de l'enrichir.
"""

from __future__ import annotations

import logging
import math
import re
import unicodedata
from collections import Counter, defaultdict

from .config import Config
from .geo import FRANCE, area, departements, region_of, regions
from .models import Collection, CollectionPlace, Place
from .score import assign_tiers, rescued

LOG = logging.getLogger(__name__)

EARTH_RADIUS_M = 6_371_000.0
# Deux lieux du même thème à moins de cette distance sont presque toujours deux
# entrées Wikidata pour le même site (le château et sa chapelle, par exemple).
DUPLICATE_DISTANCE_M = 150.0


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def dedupe(places: list[Place]) -> list[Place]:
    """Écarte les doublons de proximité, en gardant le mieux scoré.

    Deux bandes, et pas une seule, parce que la distance seule se trompe.

    **Sous trente mètres**, deux fiches décrivent la même emprise au sol et la
    fusion est juste quel que soit le nom : le musée national d'Art moderne EST
    le Centre Pompidou, le musée des Beaux-Arts d'Arras est dans l'abbaye
    Saint-Vaast, les thermes de Chassenon sont Cassinomagus.

    **Entre trente et cent cinquante mètres**, il faut en plus que les deux noms
    PARTAGENT un mot distinctif. Sans cette condition, la règle se trompait dix
    fois sur quatorze sur le catalogue réel :

        Sainte-Chapelle          écartée par la Conciergerie de Paris (120 m)
        musée Grobet-Labadié     par les Beaux-Arts de Marseille     (149 m)
        musée de l'Œuvre N.-D.   par les Beaux-Arts de Strasbourg     (62 m)
        musée historique         par le musée alsacien               (100 m)
        musée Rude               par les Beaux-Arts de Dijon         (133 m)
        odéon antique de Lyon    par le théâtre antique de Lyon      (124 m)
        Table des Marchands      par le Grand menhir brisé            (48 m)
        Arc Héré, hôtel de ville de Nancy, opéra de Dijon…

    Ce sont des visites distinctes, avec chacune son billet. Le nom partagé,
    lui, désigne bien une seule visite — et il ouvre déjà la porte inverse dans
    `twins`, jusqu'à trois cents mètres.

    Ce qui reste douteux n'est pas perdu : `twins` le signale au curateur, qui
    tranche. Écarter automatiquement est irréversible ; c'est pour cela que la
    règle doit être plus prudente que le contraire.
    """
    kept: list[Place] = []
    by_theme: dict[str, list[Place]] = defaultdict(list)
    fusionnes: list[tuple[Place, Place, float]] = []

    for place in sorted(places, key=lambda p: -p.score):
        jumeau: tuple[Place, float] | None = None
        for other in by_theme[place.theme_id]:
            ecart = haversine_m(place.lat, place.lon, other.lat, other.lon)
            if ecart >= DUPLICATE_DISTANCE_M:
                continue
            if ecart < SAME_FOOTPRINT_M or (
                _mots_distinctifs(place.name, place.commune_name)
                & _mots_distinctifs(other.name, other.commune_name)
            ):
                jumeau = (other, ecart)
                break
        if jumeau is not None:
            fusionnes.append((place, jumeau[0], jumeau[1]))
            continue
        by_theme[place.theme_id].append(place)
        kept.append(place)

    LOG.info("déduplication : %s lieux gardés sur %s", len(kept), len(places))
    if fusionnes:
        # Nommés, et non plus en DEBUG : la fusion est irréversible, et c'est
        # la seule occasion de la voir passer.
        LOG.info(
            "  doublons de proximité fusionnés : %s",
            ", ".join(
                f"{perdu.name} → {garde.name} ({ecart:.0f} m)"
                for perdu, garde, ecart in sorted(fusionnes, key=lambda t: -t[0].score)[:8]
            ),
        )
    return kept


MOTS_GENERIQUES = frozenset(
    """musee musees museum cathedrale basilique eglise abbaye abbatiale palais chateau
    chateaux maison tour pont place square jardin jardins parc hotel des les aux
    saint sainte saints notre dame royale royal ancien ancienne national nationale
    beaux arts art histoire archeologique archeologie memorial crypte antique romain
    romaine ile village plage grotte theatre amphitheatre thermes porte arc fort
    prieure couvent sur ville cite site vieux grand petit naturelle""".split()
)
# En deçà, deux fiches ne sont plus voisines : elles décrivent la même emprise
# au sol. « Musée Toulouse-Lautrec » et « palais de la Berbie » sont à 4 m.
SAME_FOOTPRINT_M = 30.0

# Quand les DEUX noms portent le même mot distinctif, on regarde deux fois plus
# loin. « Château du Louvre » et « musée du Louvre » sont à 188 m : trente-huit
# de trop pour le seuil ordinaire, et une seule visite pour qui s'y rend.
#
# Trois cents mètres, et pas plus : c'est là que le rendement s'effondre. Le
# nom partagé rattrape treize paires entre 150 et 300 m, dont huit désignent
# vraiment une seule visite — le phare de l'île Vierge et l'île Vierge, le
# cairn de Gavrinis et Gavrinis, le cap Gris-Nez et son phare, Glanum et son
# arc. Poussé à 750 m il en ramène dix-neuf de plus, dont presque aucune : les
# calanques de Sugiton et de Morgiou sont deux calanques, les puys de Lassolas
# et de Mercœur deux volcans.
#
# Le nom fait tout le travail. À 300 m, la seule distance rapproche 308 paires ;
# avec le nom, vingt.
NAMED_TWIN_DISTANCE_M = 300.0


def _mots_distinctifs(nom: str, commune: str | None) -> set[str]:
    """Les mots d'un nom qui désignent CE monument et pas sa catégorie.

    Le nom de la commune en est retiré, et c'est tout le sel : sans cela,
    « musée des Beaux-Arts de Tours » et « cathédrale Saint-Gatien de Tours »
    partagent un mot et passent pour la même visite, alors que le seul point
    commun est la ville.
    """
    ville = set(_decoupe(commune or ""))
    return {
        mot
        for mot in _decoupe(nom)
        if len(mot) > 2 and mot not in MOTS_GENERIQUES and mot not in ville
    }


def _decoupe(texte: str) -> list[str]:
    sans_accents = (
        unicodedata.normalize("NFD", texte.lower()).encode("ascii", "ignore").decode()
    )
    return [mot for mot in re.split(r"[^a-z0-9]+", sans_accents) if mot]


def twins(places: list[Place]) -> dict[str, list[tuple[Place, float, str]]]:
    """Les paires de lieux proches que `dedupe` ne peut pas voir.

    `dedupe` ne compare qu'à l'intérieur d'un thème et qu'à cent cinquante
    mètres, et il a raison de se tenir là : un musée et la cathédrale d'en face
    sont deux visites, et écarter automatiquement est irréversible. Mais la
    même règle laisse passer « palais du Louvre » (châteaux) et « musée du
    Louvre » (musées) à dix mètres — une seule visite, deux fiches Wikidata,
    deux entrées dans le catalogue.

    Deux portes, donc. La PROXIMITÉ seule ne parle qu'entre thèmes différents
    et de près. Le NOM PARTAGÉ ouvre deux fois plus loin, et à l'intérieur d'un
    thème : « château du Louvre » et « musée du Louvre » sont à 188 m, trente-
    huit de trop pour le seuil ordinaire ; l'abbaye de Lérins et sa
    tour-monastère à 160 m, dans le même thème, là où `dedupe` s'arrête.

    On ne tranche pas ici : distinguer « le musée EST le monument » de « le
    musée est en face » demande de savoir ce qu'on visite, ce qu'aucune donnée
    ne dit. On signale, avec le motif du soupçon, et le curateur décide.

    Renvoie, par identifiant, les jumeaux trouvés : (l'autre lieu, la distance,
    le motif).
    """
    grille: dict[tuple[float, float], list[Place]] = defaultdict(list)
    for place in places:
        grille[(round(place.lat, 2), round(place.lon, 2))].append(place)

    jumeaux: dict[str, list[tuple[Place, float, str]]] = defaultdict(list)
    vus: set[tuple[str, str]] = set()
    for place in places:
        for dlat in (-0.01, 0.0, 0.01):
            for dlon in (-0.01, 0.0, 0.01):
                voisins = grille.get(
                    (round(place.lat + dlat, 2), round(place.lon + dlon, 2)), []
                )
                for autre in voisins:
                    couple = tuple(sorted((place.wikidata_id, autre.wikidata_id)))
                    if couple in vus or couple[0] == couple[1]:
                        continue
                    distance = haversine_m(place.lat, place.lon, autre.lat, autre.lon)
                    if distance >= NAMED_TWIN_DISTANCE_M:
                        continue
                    communs = _mots_distinctifs(
                        place.name, place.commune_name
                    ) & _mots_distinctifs(autre.name, autre.commune_name)
                    # Deux portes. La proximité seule ne vaut qu'entre thèmes
                    # différents et de près — `dedupe` fait déjà le reste, et
                    # élargir sans le nom rapprocherait trois cents paires de
                    # voisins qui n'ont rien à voir. Le nom partagé, lui, ouvre
                    # plus loin ET à l'intérieur d'un thème : l'abbaye de Lérins
                    # et sa tour-monastère sont à 160 m, deux fiches pour un
                    # même rocher, et `dedupe` s'arrête à 150.
                    if autre.theme_id == place.theme_id:
                        # En deçà de son seuil, `dedupe` a déjà tranché — une
                        # paire qui arrive ici de si près n'existe pas en vrai.
                        # Au-delà, il ne voit plus rien : c'est le nom qui parle.
                        if not communs or distance < DUPLICATE_DISTANCE_M:
                            continue
                    elif not communs and distance >= DUPLICATE_DISTANCE_M:
                        continue
                    vus.add(couple)
                    if communs:
                        motif = "nom partagé : " + ", ".join(sorted(communs))
                    elif distance < SAME_FOOTPRINT_M:
                        motif = "même emplacement"
                    else:
                        motif = "à quelques pas"
                    jumeaux[place.wikidata_id].append((autre, distance, motif))
                    jumeaux[autre.wikidata_id].append((place, distance, motif))

    if jumeaux:
        LOG.info(
            "sosies : %s lieux concernés, %s paires — à trancher en revue",
            len(jumeaux),
            len(vus),
        )
    for lot in jumeaux.values():
        lot.sort(key=lambda t: t[1])
    return dict(jumeaux)


def diameter_km(places: list[Place]) -> float:
    """Distance entre les deux lieux les plus éloignés de la liste."""
    coords = [(p.lat, p.lon) for p in places if p.lat is not None and p.lon is not None]
    return max(
        (haversine_m(*a, *b) / 1000.0
         for i, a in enumerate(coords) for b in coords[i + 1:]),
        default=0.0,
    )


def _spread(ordered: list[Place], limit: int, max_per_dept: int) -> list[Place]:
    """Choisit `limit` lieux sans laisser un département occuper la collection.

    Le score mesure la documentation d'un lieu, et Paris est documenté comme
    nulle part ailleurs : la collection nationale des ponts comptait vingt-cinq
    ponts parisiens sur quarante. Ce n'est pas un fait de géographie mais un
    fait d'écriture — les volcans sont vraiment en Auvergne, les ponts ne sont
    pas vraiment à Paris.

    Le quota s'applique dans l'ordre du score : on prend le meilleur de chaque
    territoire avant de revenir en prendre un deuxième. Et il ne RÉTRÉCIT
    jamais la collection — si le quota ne suffit pas à remplir le plafond, on
    complète avec les meilleurs écartés. Mieux vaut une collection un peu
    parisienne qu'une collection trop courte pour exister.
    """
    retenus: list[Place] = []
    reportes: list[Place] = []
    par_dept: Counter[str] = Counter()

    for place in ordered:
        dept = place.departement_code or "?"
        if len(retenus) >= limit:
            break
        if par_dept[dept] >= max_per_dept:
            reportes.append(place)
            continue
        par_dept[dept] += 1
        retenus.append(place)

    if len(retenus) < limit:
        retenus.extend(reportes[: limit - len(retenus)])
        retenus.sort(key=lambda p: (-p.score, p.name))
    return retenus


def _force_promoted(
    retenus: list[Place], members: list[Place]
) -> tuple[list[Place], set[str]]:
    """Un lieu remonté par le curateur entre, même si le plafond l'avait coupé.

    L'appartenance à une collection se décidait AVANT que le niveau n'existe :
    le plafond coupait au score, et le verdict du curateur n'arrivait qu'ensuite,
    pour ranger ce qui restait. Un `promote` sur un lieu hors collection ne
    faisait donc rien de ce qu'on lui demandait — Camon était 81e sur 154 pour
    un plafond de 80, et le promouvoir le laissait dehors.

    C'est la même règle que le `keep` face au plancher de notoriété, et que le
    déplacement de niveau face au plafond du niveau 1 : le seuil est une
    heuristique, la décision est un jugement.
    """
    dedans = {place.wikidata_id for place in retenus}
    forces = [
        place for place in members
        if place.tier_shift < 0 and place.wikidata_id not in dedans
    ]
    if not forces:
        return retenus, set()
    return (
        sorted(retenus + forces, key=lambda p: (-p.score, p.name)),
        {place.wikidata_id for place in forces},
    )


def _rank_within_theme(members: list[Place]) -> dict[str, float]:
    """Rang de chaque lieu dans son thème, ramené entre 0 et 1.

    Une collection mixte compare des scores bruts d'un thème à l'autre, et le
    score est bâti sur la documentation — une échelle faite pour les monuments.
    La MEILLEURE cascade de France score 74 ; le château MÉDIAN, 86. Il n'y a
    aucune compétition possible, et « Le meilleur de France » ne comptait que
    trois lieux naturels sur quatre-vingts.

    Le rang, lui, se compare : le premier des cascades vaut le premier des
    cathédrales. C'est la seule façon de mettre les gorges du Verdon et
    Notre-Dame sur la même ligne sans toucher au score, qui classe très bien à
    l'intérieur d'un thème et qu'on casserait en le rééquilibrant de force.

    Le rang RELATIF, pas absolu : avec le rang absolu, le quatrième cirque de
    France — il n'y en a que onze — vaudrait le quatrième château sur
    quatre cent vingt-cinq.
    """
    par_theme: dict[str, list[Place]] = defaultdict(list)
    for place in members:
        par_theme[place.theme_id].append(place)
    rangs: dict[str, float] = {}
    for lot in par_theme.values():
        lot.sort(key=lambda p: (-p.score, p.name))
        dernier = max(1, len(lot) - 1)
        for index, place in enumerate(lot):
            rangs[place.wikidata_id] = index / dernier
    return rangs


def _mix_themes(ordered: list[Place], limit: int, part: float) -> list[Place]:
    """Empêche un seul thème d'occuper tout un « Le meilleur de… ».

    « Le meilleur de Paris » comptait quarante et un musées sur quatre-vingts.
    Le quota par département, lui, ne peut rien y faire : dans une collection
    géographique, tous les lieux sont du même département par construction.
    C'est son symétrique qui manquait.

    Le plafond se calcule sur le PLAFOND de la collection, jamais sur le nombre
    de lieux présents. Calculé sur les lieux présents, il coupait la Creuse de
    douze à huit — quatre lieux retirés qu'aucun autre thème ne pouvait
    remplacer, et tout le travail du repêchage annulé. Une collection de douze
    lieux n'a rien à sélectionner : elle les prend tous.

    Et il MONTE d'un cran tant qu'il reste des places, comme celui du
    repêchage : le Centre-Val de Loire n'a pas soixante lieux hors châteaux à
    offrir, alors son plafond s'établit à trente et un. Mieux vaut une région
    un peu châtelaine qu'une collection trop courte.
    """
    plafond = max(3, int(limit * part))
    limite = max(plafond, limit)
    retenus: list[Place] = []
    par_theme: Counter[str] = Counter()
    vus: set[str] = set()

    while len(retenus) < limit and plafond <= limite:
        avant = len(retenus)
        for place in ordered:
            if len(retenus) >= limit:
                break
            if place.wikidata_id in vus or par_theme[place.theme_id] >= plafond:
                continue
            retenus.append(place)
            vus.add(place.wikidata_id)
            par_theme[place.theme_id] += 1
        if len(retenus) == avant:
            plafond += 1
    return retenus


def _finalize(
    collection: Collection,
    members: list[Place],
    config: Config,
    cap: int | None = None,
    max_per_dept: int | None = None,
    theme_share: float = 0.0,
) -> Collection | None:
    """Applique plancher, plafond et niveaux. Renvoie None si la collection n'existe pas."""
    rules = config.collections
    if len(members) < rules.min_places:
        return None

    limit = cap or rules.max_places
    ordre = None
    ordered = sorted(members, key=lambda p: (-p.score, p.name))
    if max_per_dept:
        ordered = _spread(ordered, limit, max_per_dept)
    elif theme_share:
        # Dans une collection mixte, le rang dans le thème remplace le score :
        # comparer une cascade et une cathédrale au score brut revient à
        # comparer leurs documentations, pas leur intérêt.
        rangs = _rank_within_theme(ordered)
        ordre = lambda p: (rangs[p.wikidata_id], -p.score, p.name)  # noqa: E731
        ordered = _mix_themes(sorted(ordered, key=ordre), limit, theme_share)
    else:
        ordered = ordered[:limit]
    # Seules les collections THÉMATIQUES : c'est d'elles que parle la revue
    # quand elle annonce « HORS COLLECTION NATIONALE », et c'est là que le
    # curateur veut faire entrer le lieu. Forcer partout gonflait « Le meilleur
    # de France » à 125 lieux pour un plafond de 80.
    ordered, forces = (
        _force_promoted(ordered, members) if collection.kind == "theme"
        else (ordered, set())
    )

    collection.places = [
        CollectionPlace(place_id=place.wikidata_id, tier=tier, rank=rank,
                        forced=place.wikidata_id in forces)
        for place, tier, rank in assign_tiers(ordered, config.tiers, ordre)
    ]
    return collection


# Ce qui trahit un lieu qu'on ne peut PAS visiter.
#
# Deux familles, et deux seulement : la chose n'existe plus, ou personne ne
# sait où elle est. Les motifs sont volontairement étroits — un filet large
# ramènerait toutes les ruines de France, et une ruine se visite très bien.
FANTOMES: tuple[tuple[str, str], ...] = (
    ("démoli, détruit, rasé",
     r"\b(?:fut|est|a été|furent|ont été)\s+(?:\w+ ){0,2}?"
     r"(?:détruit|démoli|rasé|dynamit|arasé)"),
    ("il ne reste rien",
     r"il ne (?:reste|subsiste)\s+(?:plus\s+)?(?:rien|aucun)\b"),
    ("a disparu",
     r"\ba (?:aujourd'hui )?(?:entièrement |totalement |complètement )?disparu"),
    ("n'existe plus", r"n'existe plus\b"),
    ("localisation inconnue",
     r"localisation (?:exacte |précise )?(?:est |reste |demeure )?"
     r"(?:inconnue|incertaine|hypothétique|discutée)"),
    ("jamais localisé",
     r"n'a (?:jamais |pas )(?:été )?(?:formellement )?"
     r"(?:localisé|identifié|retrouvé)"),
)


def fantomes(places: list[Place]) -> list[tuple[Place, list[str]]]:
    """Les lieux dont le résumé dit que la chose n'est plus là.

    Un lieu non visitable est l'échec le plus coûteux du catalogue : il envoie
    quelqu'un faire la route pour rien. Trois sont passés en revue sans être
    vus — la tour du Temple, démolie en 1808, au huitième rang du niveau 1 de
    Paris ; le château de Madrid, démoli au XVIIIe siècle, au même rang une
    fois la tour partie ; Portus Itius, dont personne ne sait où il était.

    Ils ne se voient pas dans une revue à plat : elle demande de lire deux
    mille quatre cents fiches, et il en reste toujours des centaines à lire.
    Ici la question est posée une fois, à tout le catalogue.

    Écarter un lieu PROMEUT le suivant — c'est ainsi que le château de Madrid
    a pris la place de la tour du Temple, puis le château du Louvre celle du
    château de Madrid. La commande se relance donc après chaque `build`, et
    n'a fini que lorsqu'elle ne rend plus rien de neuf.

    Le filet est étroit et faillible : il lit le français des résumés, il ne
    prouve rien. Il ramène des faux positifs — le pont d'Avignon, dont il ne
    reste que quatre arches, se visite très bien — et il rate ce que Wikipédia
    ne dit pas. C'est un rabatteur, pas un juge.

    On a cherché mieux : Wikidata porte P576, « date de dissolution, démolition
    ou disparition », et il paraissait être le signal dur qui remplacerait
    l'heuristique de texte. Mesuré, il fait pire. Il RATE la tour du Temple, le
    château de Madrid et Portus Itius — aucun des trois ne le porte — et il
    DÉSIGNE une trentaine d'abbayes debout, dont la communauté fut dissoute à
    la Révolution mais dont les bâtiments se visitent : Jumièges, Fontenay,
    Valloires, Aubazine. La propriété dit qu'une institution a pris fin, pas
    qu'un lieu a disparu. Ne pas la rebrancher ici.
    """
    trouves: list[tuple[Place, list[str]]] = []
    for place in places:
        resume = place.summary or ""
        motifs = [nom for nom, rx in FANTOMES if re.search(rx, resume, re.I)]
        if motifs:
            trouves.append((place, motifs))
    trouves.sort(key=lambda entree: -(entree[0].score or 0))
    return trouves


def drop_twin_collections(collections: list[Collection]) -> list[Collection]:
    """Écarte les collections qui contiennent exactement les mêmes lieux.

    Un département d'outre-mer est AUSSI une région : La Réunion produisait
    « Le meilleur de La Réunion » deux fois, et « Volcans et sites volcaniques
    de La Réunion » deux fois, à l'identique. Neuf doublons dans la liste, que
    l'utilisateur voyait tels quels.

    La première rencontrée gagne, et `geo_levels` déclare le département avant
    la région : c'est le niveau le plus précis qui reste, celui dont le nom
    correspond à ce qu'on parcourt.
    """
    vus: dict[tuple[str, frozenset[str]], Collection] = {}
    out: list[Collection] = []
    jumelles: list[str] = []
    for collection in collections:
        cle = (collection.name, frozenset(cp.place_id for cp in collection.places))
        if cle in vus:
            jumelles.append(collection.name)
            continue
        vus[cle] = collection
        out.append(collection)
    if jumelles:
        LOG.info(
            "%s collection(s) en double écartées, mêmes lieux sous le même nom "
            "à deux niveaux géographiques : %s",
            len(jumelles), ", ".join(sorted(set(jumelles))),
        )
    return out


def build_theme_collections(places: list[Place], config: Config) -> list[Collection]:
    by_theme: dict[str, list[Place]] = defaultdict(list)
    for place in places:
        by_theme[place.theme_id].append(place)

    out = []
    starved: list[str] = []
    for theme in config.themes:
        collection = Collection(
            slug=f"theme-{theme.id}",
            name=theme.name,
            kind="theme",
            theme_id=theme.id,
        )
        members = by_theme.get(theme.id, [])
        built = _finalize(
            collection, members, config,
            cap=theme.cap, max_per_dept=theme.max_per_departement,
        )
        if built:
            out.append(built)
        else:
            starved.append(f"{theme.id} {len(members)}")

    if starved:
        # Un thème déclaré qui ne produit AUCUNE collection nationale disparaît
        # sinon sans un mot : ses lieux ne survivent qu'au hasard des
        # collections géographiques, et l'onglet du thème reste vide dans
        # l'application. C'est le symptôme d'un thème à revoir ou à fusionner,
        # pas un détail de construction.
        LOG.warning(
            "%s thème(s) sans collection nationale, faute d'atteindre %s lieux : %s",
            len(starved),
            config.collections.min_places,
            ", ".join(starved),
        )
    return out


def build_label_collections(places: list[Place], config: Config) -> list[Collection]:
    out = []
    muets: list[str] = []
    for label in config.labels:
        if not label.makes_collection:
            continue
        members = [p for p in places if label.id in p.labels]
        if not members:
            muets.append(label.id)
            continue
        collection = Collection(
            slug=f"label-{label.id}",
            name=label.name,
            kind="label",
            label_id=label.id,
        )
        # Un label est une liste officielle et finie : on ne la tronque pas,
        # sinon la collection ne correspond plus au label qu'elle affiche.
        built = _finalize(collection, members, config, cap=len(members) or 1)
        if built:
            out.append(built)

    # Un label déclaré « fait une collection » et qui n'a AUCUN membre ne
    # produit rien, et ne produisait rien en silence. Les Plus Beaux Détours
    # sont configurés depuis le premier jour, alimentent le thème « villages »,
    # et attendaient toujours leur fichier : cent quatre communes que le
    # catalogue ne pouvait pas voir, sans qu'une ligne le dise.
    if muets:
        LOG.warning(
            "%s label(s) déclarés comme collection mais sans aucun membre : %s. "
            "Liste manuelle absente, ou `relabel` jamais lancé depuis.",
            len(muets), ", ".join(sorted(muets)),
        )
    return out


def build_geo_collections(places: list[Place], config: Config) -> list[Collection]:
    """Collections « le meilleur de X », tous thèmes confondus."""
    out: list[Collection] = []

    for level in config.collections.geo_levels:
        buckets: dict[str, list[Place]] = defaultdict(list)
        for place in places:
            code = _geo_code(place, level)
            if code:
                buckets[code].append(place)

        for code, members in buckets.items():
            zone = area(level, code)
            if zone is None:
                continue
            collection = Collection(
                slug=f"geo-{level}-{code.lower()}",
                name=f"Le meilleur {zone.de_form}",
                kind="geo",
                geo_level=level,
                geo_code=code,
            )
            # Le brassage ne vaut QUE pour les « Le meilleur de… ». Un
            # croisement thème × géographie est mono-thème par construction :
            # lui appliquer la règle ramènerait « Châteaux de Bretagne » à
            # vingt châteaux. Les deux portent pourtant le même `kind` ; c'est
            # l'absence de `theme_id` qui distingue les vraies collections
            # géographiques.
            built = _finalize(collection, members, config,
                              theme_share=config.collections.max_theme_share)
            if built:
                out.append(built)
    return out


def theme_lift(members: int, dans_la_zone: int, dans_le_pays: int, total: int) -> float:
    """À quel point ce territoire est-il CARACTÉRISTIQUE de ce thème ?

    Part du thème sur place, rapportée à sa part dans le pays. Un rapport de 1
    veut dire que ce territoire n'a rien de particulier — « Cathédrales de
    Provence-Alpes-Côte d'Azur » vaut exactement 1,0, et personne ne
    collectionne ça : c'est le thème national, découpé.

    Au-dessus, le territoire dit quelque chose : les volcans du Puy-de-Dôme
    valent ×37, les phares du Finistère ×17, les grottes de la Dordogne ×12,
    les châteaux du Centre-Val de Loire ×3.
    """
    if not dans_la_zone or not dans_le_pays or not total:
        return 0.0
    return (members / dans_la_zone) / (dans_le_pays / total)


def build_cross_collections(places: list[Place], config: Config) -> list[Collection]:
    """Croisements thème × géographie (« Châteaux du Cantal »).

    Soumis aux mêmes règles : la grande majorité des croisements est écartée
    faute de lieux, et c'est exactement l'effet recherché.
    """
    out: list[Collection] = []
    serres: list[tuple[float, int, str]] = []
    banals: list[tuple[float, int, str]] = []
    par_id = {place.wikidata_id: place for place in places}
    par_theme = Counter(place.theme_id for place in places)

    for level in config.collections.cross_theme_levels:
        buckets: dict[tuple[str, str], list[Place]] = defaultdict(list)
        par_zone: Counter[str] = Counter()
        for place in places:
            code = _geo_code(place, level)
            if code:
                buckets[(place.theme_id, code)].append(place)
                par_zone[code] += 1

        for (theme_id, code), members in buckets.items():
            zone = area(level, code)
            if zone is None:
                continue
            theme = config.theme(theme_id)
            collection = Collection(
                slug=f"{theme_id}-{level}-{code.lower()}",
                name=f"{theme.name} {zone.de_form}",
                kind="geo",
                theme_id=theme_id,
                geo_level=level,
                geo_code=code,
            )
            built = _finalize(collection, members, config)
            if not built:
                continue
            # Mesurée sur les lieux RETENUS, pas sur les candidats : c'est la
            # collection telle qu'elle s'affiche qu'on juge, et le plafond en
            # écarte parfois les extrémités.
            retenus = [par_id[m.place_id] for m in built.places]
            etendue = diameter_km(retenus)
            if etendue < config.collections.min_diameter_km:
                serres.append((etendue, len(built.places), built.name))
                continue
            rapport = theme_lift(
                len(built.places), par_zone[code], par_theme[theme_id], len(places)
            )
            if rapport < config.collections.min_theme_lift:
                banals.append((rapport, len(built.places), built.name))
                continue
            out.append(built)

    if serres:
        # Trente et un ponts dans neuf kilomètres : ces croisements existent
        # parce que la machine croise tout, pas parce que quelqu'un voudrait
        # les collectionner. Écarter la collection écarte aussi les lieux
        # qu'elle seule justifiait — le pont de Tolbiac disparaît du catalogue,
        # le pont Neuf reste. C'est l'effet recherché.
        LOG.info(
            "%s croisement(s) écartés, trop resserrés pour être un voyage "
            "(moins de %.0f km) : %s",
            len(serres),
            config.collections.min_diameter_km,
            ", ".join(f"{nom} ({n} lieux, {d:.0f} km)"
                      for d, n, nom in sorted(serres)),
        )
    if banals:
        # Un croisement où le territoire ne dit rien du thème n'est que le
        # thème national redécoupé. « Cathédrales de Provence-Alpes-Côte
        # d'Azur » vaut exactement la moyenne du pays ; les volcans du
        # Puy-de-Dôme valent trente-sept fois cette moyenne, et c'est cette
        # collection-là qu'on veut voir dans la liste.
        LOG.info(
            "%s croisement(s) écartés, le territoire n'a rien de particulier "
            "pour ce thème (moins de ×%.1f) : %s",
            len(banals),
            config.collections.min_theme_lift,
            ", ".join(f"{nom} (×{r:.1f})" for r, n, nom in sorted(banals)[:8]),
        )
    return out


def _geo_code(place: Place, level: str) -> str | None:
    if level == "departement":
        return place.departement_code
    if level == "region":
        return place.region_code
    if level == "country":
        return FRANCE.code
    return None


def apply_geographic_scope(places: list[Place], config: Config) -> list[Place]:
    """Écarte les lieux qu'on ne sait pas rattacher à un département français.

    Sans département, un lieu n'entre dans aucune collection géographique : il
    ne peut apparaître que dans « Le meilleur de France », où il se retrouve à
    concurrencer le Mont Blanc. C'est le cas des collectivités d'outre-mer, qui
    n'ont pas de code de département — les DOM, eux, en ont un et restent.
    """
    if not config.collections.require_departement:
        return places

    kept = [place for place in places if place.departement_code]
    dropped = [place for place in places if not place.departement_code]
    if dropped:
        LOG.warning(
            "hors périmètre : %s lieux sans département écartés (ex. %s). "
            "Si des lieux de métropole s'y trouvent, c'est que Wikidata ne les "
            "situe pas — lance `enrich` pour les rattacher par coordonnées.",
            len(dropped),
            ", ".join(place.name for place in dropped[:3]),
        )
    return kept


def dedupe_across_themes(places: list[Place], config: Config) -> list[Place]:
    """Un lieu n'appartient qu'à un seul thème.

    Le château de Versailles est aussi un palais, le Louvre est un palais et un
    musée : sans ce filtre, ils entreraient deux fois au catalogue, gonfleraient
    les compteurs et se retrouveraient à relire en double.

    Le thème retenu est le premier déclaré dans `themes.yaml`, dont l'ordre va
    du plus spécifique au plus générique — un lieu à la fois cathédrale et
    monument est une cathédrale.

    **Sauf** quand il n'est entré que par une classe GÉNÉRIQUE. Le Petit Palais
    est un « musée d'art », classe propre du thème `musees` ; il est aussi une
    « maison », classe générique du thème `maisons` — déclaré plus tôt pour
    protéger les maisons-musées. L'ordre seul en faisait donc une maison
    d'artiste, avec tous les musées-palais.

    Une porte large ne vaut pas une porte précise : une entrée générique cède
    devant n'importe quelle entrée spécifique, quel que soit l'ordre. C'est la
    règle « du plus spécifique au plus générique » appliquée jusqu'au bout —
    et elle ne demande d'énumérer aucune classe fautive, là où interdire
    « palais » aux maisons aurait mal rangé un palais qui serait vraiment une
    maison d'artiste.
    """
    rank = {theme.id: index for index, theme in enumerate(config.themes)}
    best: dict[str, Place] = {}
    collisions: list[tuple[str, str, str]] = []

    for place in places:
        current = best.get(place.wikidata_id)
        if current is None:
            best[place.wikidata_id] = place
            continue
        # Un lieu épinglé impose son thème : c'est un choix explicite.
        if place.pinned != current.pinned:
            winner, loser = (place, current) if place.pinned else (current, place)
        else:
            # (entrée générique ?, rang du thème) : le premier critère prime.
            def key(p: Place) -> tuple[int, int]:
                return (1 if p.via_broad_class else 0, rank.get(p.theme_id, 99))

            winner, loser = (
                (place, current) if key(place) < key(current) else (current, place)
            )
        best[place.wikidata_id] = winner
        collisions.append((winner.name, winner.theme_id, loser.theme_id))

    if collisions:
        LOG.info(
            "thèmes croisés : %s lieux rattachés à un seul thème (ex. %s)",
            len(collisions),
            ", ".join(f"{n} → {w} plutôt que {l}" for n, w, l in collisions[:3]),
        )
    return list(best.values())


def _ville(commune_code: str) -> str:
    """Le code de la VILLE, arrondissements réunis.

    Paris, Lyon et Marseille sont découpés en arrondissements, et l'INSEE leur
    donne à chacun son code : 75101 à 75120, 69381 à 69389, 13201 à 13216. Un
    plafond posé sur le code de commune s'y appliquait donc vingt fois, et
    laissait passer vingt fois trop — c'est exactement ce qu'on voulait éviter.

    Personne ne pense « j'ai fait le 5e » : on fait Paris. La ville est la
    bonne maille.
    """
    if commune_code.startswith("751") and len(commune_code) == 5:
        return "75056"   # Paris
    if commune_code.startswith("6938") and len(commune_code) == 5:
        return "69123"   # Lyon
    if commune_code.startswith("132") and len(commune_code) == 5:
        return "13055"   # Marseille
    return commune_code


def apply_theme_cap(places: list[Place], config: Config) -> list[Place]:
    """Combien de lieux d'un thème le CATALOGUE garde, tous territoires confondus.

    À ne pas confondre avec `cap`, qui borne la collection nationale d'un thème.
    Le catalogue portait cent quatre-vingt-treize cathédrales alors que la
    collection « Cathédrales et basiliques » en montrait soixante et une : les
    cent trente-deux autres vivaient dans les collections départementales et
    régionales, et toutes s'affichaient sur la carte. « Ce n'est plus un guide,
    ça devient un recensement. »

    Trois réservations, dans cet ordre, avant que le classement ne remplisse le
    reste :

    1. **Les lieux épinglés À LA MAIN.** Une ligne de places.csv est un lieu que
       le curateur a ajouté lui-même ; le plafond n'a pas à défaire ce geste.
    2. **Un minimum par région.** Sans lui, les quatre cathédrales des DOM
       tombaient d'un bloc : elles sont seules dans leur région, donc jamais
       dans les quatre-vingts meilleures de France. La métropole, elle, se
       répartit déjà toute seule — de cinq à onze par région sans qu'on lui
       demande rien.
    3. **Les listes officielles finies.** Même critère que le plancher de
       notoriété : `makes_collection` dit qu'une liste est assez courte et
       assez choisie pour valoir dispense. Sans quoi le plafond couperait
       dans la curation humaine qu'on a passé des jours à saisir — les cent
       quatre-vingt-sept Plus Beaux Villages SONT la liste de l'association.

    Le reste se remplit dans l'ordre du LOT, et le lot est classé par la
    hiérarchie de revue avant de l'être par le score : monté d'un niveau
    devant, intact ensuite, descendu en dernier. Un verdict `keep` ne réserve
    RIEN — il y en a mille cinq cent cinquante-cinq, et le curateur en avait
    gardé cent soixante-treize pour un plafond de quatre-vingts. « Si c'est
    juste un keep mais que ce dernier se situe à la fin du classement c'est
    normal qu'il sorte. » Le total ne dépasse jamais le plafond.
    """
    caps = {theme.id: theme.catalogue_cap for theme in config.themes
            if theme.catalogue_cap}
    if not caps:
        return places

    mini = config.collections.min_per_region
    curees = {label.id for label in config.labels if label.makes_collection}
    par_theme: dict[str, list[Place]] = defaultdict(list)
    intacts: list[Place] = []
    for place in places:
        (par_theme[place.theme_id] if place.theme_id in caps else intacts).append(place)

    kept = list(intacts)
    for theme_id, lot in par_theme.items():
        cap = caps[theme_id]
        # La hiérarchie du curateur d'abord, le score ensuite. `tier_shift`
        # porte le verdict de revue : -1 monté d'un niveau, 0 intact, +1
        # descendu. Trier au seul score revenait à demander à Wikipédia
        # d'arbitrer ce que le curateur avait déjà tranché à la main.
        lot.sort(key=lambda place: (place.tier_shift, -place.score))
        if len(lot) <= cap:
            kept.extend(lot)
            continue

        pris: dict[str, Place] = {}
        par_region: dict[str, list[Place]] = defaultdict(list)
        for place in lot:
            par_region[region_of(place.departement_code or "").code
                       if place.departement_code
                       and region_of(place.departement_code) else ""].append(place)

        def reserve(place: Place) -> None:
            if len(pris) < cap:
                pris.setdefault(place.wikidata_id, place)

        # Épinglé À LA MAIN seulement. Un verdict `keep` pose le même drapeau,
        # et il y en a mille cinq cent cinquante-cinq : les compter comme des
        # dispenses remplissait le plafond avant qu'une région n'ait eu sa part,
        # et les quatre cathédrales d'outre-mer tombaient quand même.
        for place in lot:
            if place.pinned and not place.kept_in_review:
                reserve(place)
        # Une région n'a droit à sa garantie que si le thème y EXISTE. Sans
        # cette condition, le minimum forçait un lieu « côtier » dans chaque
        # région sans côte, et le lieu forcé était par construction le plus
        # mauvais du lot : la presqu'île de Gennevilliers — le port industriel
        # de Paris — entrait 120e sur 120 pour l'Île-de-France, Le Saussois
        # (une falaise d'escalade sur l'Yonne) pour la Bourgogne, la plage de
        # la confluence pour le Centre.
        #
        # Le seuil se lit dans le vivier, et la séparation est franche : les
        # quatre régions enclavées offrent UN candidat, la plus pauvre des
        # régions côtières en offre treize.
        seuil = config.theme(theme_id).min_region_pool
        for _code, membres in sorted(par_region.items()):
            if len(membres) < seuil:
                continue
            for place in membres[:mini]:
                reserve(place)
        for place in lot:
            if curees & set(place.labels):
                reserve(place)
        for place in lot:
            reserve(place)

        kept.extend(pris.values())
        LOG.info(
            "plafond de thème : %s gardés sur %s %s (minimum %s par région) — "
            "le dernier entré est %s",
            len(pris), len(lot), theme_id, mini,
            min(pris.values(), key=lambda p: p.score).name,
        )
    return kept


def apply_list_membership(places: list[Place], config: Config) -> list[Place]:
    """Un thème nourri par des listes ne garde que les membres de ces listes.

    Le thème « villages » n'a aucune classe Wikidata : il n'existe que par les
    Plus Beaux Villages et les Plus Beaux Détours. Mais une fois collectée, une
    commune restait au catalogue même retirée de la liste — elle franchissait le
    plancher de notoriété comme n'importe quel lieu, et rien ne la sortait.

    Amélie-les-Bains, saisie par erreur, comptait cinq versions linguistiques ;
    Baugé, trente. Le plancher est à trois. Effacer leur ligne du CSV les
    dépouillait de leur label et les laissait au catalogue, devenues des
    « villages de caractère » que personne n'avait choisis.

    Pour ces thèmes-là, la liste officielle n'est pas un bonus : c'est la
    définition. Un lieu qui en sort, sort.

    Le lieu ÉPINGLÉ fait exception, comme partout : le curateur a vu le lieu,
    pas la règle.
    """
    par_liste = {
        theme.id: set(theme.from_labels)
        for theme in config.themes
        if theme.from_labels and not theme.wikidata_classes
    }
    if not par_liste:
        return places

    kept: list[Place] = []
    sortis: dict[str, list[str]] = defaultdict(list)
    for place in places:
        listes = par_liste.get(place.theme_id)
        if listes is None or place.pinned or listes & set(place.labels):
            kept.append(place)
        else:
            sortis[place.theme_id].append(place.name)

    for theme_id, noms in sortis.items():
        LOG.info(
            "%s : %s lieux sortis, plus sur aucune liste officielle — %s%s",
            theme_id, len(noms), ", ".join(sorted(noms)[:6]),
            f" (+{len(noms) - 6})" if len(noms) > 6 else "",
        )
    return kept


def saturated_themes(places: list[Place], config: Config) -> set[str]:
    """Les thèmes qui ont atteint leur plafond de catalogue.

    Le repêchage géographique comble un TERRITOIRE pauvre ; il n'a pas à
    rouvrir un quota que le curateur a fermé. Sans cette liste, il remontait
    des cathédrales restées sous le plancher pour garnir un département, et le
    plafond de quatre-vingts n'était plus qu'une indication.
    """
    compte: Counter[str] = Counter(place.theme_id for place in places)
    return {
        theme.id for theme in config.themes
        if theme.catalogue_cap and compte[theme.id] >= theme.catalogue_cap
    }


def apply_commune_cap(places: list[Place], config: Config) -> list[Place]:
    """Au plus `max_par_commune` lieux d'un même thème dans une même commune.

    Paris comptait cent soixante-deux lieux ; Marseille, la deuxième ville du
    catalogue, en comptait vingt et un. Sur cent trente-cinq jardins français,
    cinquante et un étaient parisiens — la commune suivante en avait quatre.

    Ce n'est pas que Paris soit huit fois plus riche : c'est que le plancher
    mesure la documentation, et qu'un square parisien a un article de Wikipédia
    là où un beau jardin du Gers n'en a pas. Le score récompense la densité de
    couverture autant que l'intérêt du lieu.

    Le plafond porte sur le couple COMMUNE × THÈME, et pas sur la commune
    seule. Un simple « les trente meilleurs de Paris » garderait le musée
    Grévin, dix-huitième au score, et jetterait la Sainte-Chapelle,
    trente-et-unième : les musées parisiens écrasent tout avec leurs millions
    de visiteurs. Par thème, Paris garde ses six musées, ses six jardins, ses
    six monuments, et la liste ressemble à une ville.

    La règle est générale mais ne mord presque que là : à six, elle retire cent
    vingt lieux à Paris et deux à Toulouse. C'est la mesure d'une anomalie, pas
    une exception écrite pour une ville.
    """
    defaut = config.collections.max_per_commune
    if not defaut:
        return places

    par_commune: dict[tuple[str, str], list[Place]] = defaultdict(list)

    sans_commune: list[Place] = []
    for place in places:
        if place.commune_code:
            par_commune[(_ville(place.commune_code), place.theme_id)].append(place)
        else:
            # Un phare en mer n'a pas de commune. Le plafond ne peut rien dire
            # de lui, et le silence vaut mieux qu'un rangement arbitraire.
            sans_commune.append(place)

    kept = list(sans_commune)
    retires: dict[str, int] = defaultdict(int)
    derogations = config.collections.commune_overrides
    for (_code, _theme), lot in par_commune.items():
        # Une dérogation ne vaut que pour le couple ville × thème qu'elle nomme.
        cap = derogations.get(_code, {}).get(_theme, defaut)
        # Épinglé À LA MAIN veut dire épinglé : une ligne de places.csv est
        # un lieu que le curateur a ajouté lui-même, et le plafond n'a pas à
        # défaire ce geste. Un verdict `keep` pose le même drapeau et ne
        # réserve rien : il y en a mille cinq cent cinquante-cinq, ils
        # remplissaient le plafond à eux seuls. « Si c'est juste un keep mais
        # que ce dernier se situe à la fin du classement c'est normal qu'il
        # sorte. » Vient ensuite la hiérarchie de revue, puis le score.
        lot.sort(key=lambda place: (
            not (place.pinned and not place.kept_in_review),
            place.tier_shift,
            -place.score,
        ))
        kept.extend(lot[:cap])
        for place in lot[cap:]:
            retires[place.commune_name or place.commune_code or "?"] += 1

    if retires:
        total = sum(retires.values())
        detail = ", ".join(
            f"{nom} {n}" for nom, n in sorted(retires.items(), key=lambda kv: -kv[1])[:5]
        )
        LOG.info(
            "plafond par commune (%s par thème%s) : %s lieux retirés — %s",
            defaut,
            "".join(
                f" ; {ville} " + ", ".join(f"{t} {n}" for t, n in sorted(p.items()))
                for ville, p in sorted(derogations.items())
            ),
            total, detail,
        )
    return kept


def apply_notoriety_floor(places: list[Place], config: Config) -> list[Place]:
    """Écarte les lieux sous le plancher éditorial de leur thème.

    Ce filtre vit ici, et non dans la requête Wikidata, pour qu'ajuster un seuil
    coûte une seconde plutôt qu'une nouvelle collecte.
    """
    kept: list[Place] = []
    dropped: dict[str, int] = defaultdict(int)
    saved: dict[str, int] = defaultdict(int)
    # Un lieu que le plancher écarte ALORS QU'IL FIGURE sur la liste officielle
    # qui alimente son thème. Le plancher mesure la documentation ; la liste est
    # une curation humaine, finie et motivée. Quand les deux se contredisent,
    # c'est un arbitrage éditorial, et il doit se voir plutôt que se subir.
    listes: dict[str, int] = defaultdict(int)
    par_theme = {theme.id: set(theme.from_labels) for theme in config.themes}
    curees = {label.id for label in config.labels if label.makes_collection}

    for place in places:
        try:
            floor = config.theme(place.theme_id).min_sitelinks
        except KeyError:
            continue
        # Un lieu épinglé par le curateur passe outre : le plancher mesure la
        # documentation d'un lieu, pas son intérêt. Giverny et le château
        # d'Auvers-sur-Oise attirent le monde entier sans être documentés en
        # dix langues.
        #
        # Une LISTE OFFICIELLE de son thème passe outre pour la même raison, et
        # celle-là est mesurée : sur les deux cent trente et une Maisons des
        # Illustres, cent quarante-sept étaient écartées sur un décompte de
        # versions linguistiques de Wikipédia. Le ministère de la Culture a déjà
        # fait le travail de curation ; lui demander d'être ratifié par
        # Wikipédia, c'est renverser l'ordre des autorités.
        #
        # Toute liste officielle FINIE vaut dispense, pas seulement celle qui
        # alimente le thème : un Grand Site de France rangé en « gorges » ne
        # profitait de rien, alors que la même curation d'État le sauvait s'il
        # tombait en « maisons ». Le critère est `makes_collection` — il dit
        # déjà, dans labels.yaml, qu'une liste est assez courte et assez choisie
        # pour être une collection à elle seule. « Monument historique
        # inscrit », avec ses quarante mille membres, ne l'est pas et ne
        # dispense de rien.
        sur_liste = bool(
            (par_theme.get(place.theme_id, set()) | curees) & set(place.labels)
        )
        if place.pinned or sur_liste or place.sitelinks >= floor:
            kept.append(place)
            if sur_liste and place.sitelinks < floor:
                listes[place.theme_id] += 1
        elif rescued(place, config):
            kept.append(place)
            saved[place.theme_id] += 1
        else:
            dropped[place.theme_id] += 1

    if listes:
        LOG.info(
            "%s lieux gardés sous leur plancher parce qu'ils figurent sur une "
            "liste officielle : %s",
            sum(listes.values()),
            ", ".join(f"{k} {v}" for k, v in sorted(listes.items(), key=lambda x: -x[1])),
        )

    if dropped:
        LOG.info(
            "plancher de notoriété : %s lieux écartés (%s)",
            sum(dropped.values()),
            ", ".join(f"{k} {v}" for k, v in sorted(dropped.items(), key=lambda x: -x[1])),
        )
    if saved:
        # Le réglage doit être visible pour être réglable : sans ce compte, le
        # repêchage agirait sans qu'on sache jamais sur combien de lieux.
        LOG.info(
            "%s lieux repêchés sous leur plancher — accueil du public attesté "
            "et score ≥ %s : %s",
            sum(saved.values()),
            config.scoring.rescue_score,
            ", ".join(f"{k} {v}" for k, v in sorted(saved.items(), key=lambda x: -x[1])),
        )
    return kept


def apply_access_filter(places: list[Place], config: Config) -> list[Place]:
    """Écarte les lieux dont OpenStreetMap dit l'accès explicitement refusé.

    L'application se joue sur place : on valide un lieu en s'y rendant. Un lieu
    où l'on ne peut pas entrer n'est donc pas collectionnable, si intéressante
    que soit son histoire — le château d'Hérouville en est l'exemple.

    Le signal est rare et délibéré : `access=private` ou `access=no` est posé à
    la main par un contributeur, et ne concerne qu'une vingtaine de lieux sur
    près de deux mille. Il ne s'agit donc pas d'une heuristique mais d'un fait,
    et un malus de score ne suffisait pas à s'en débarrasser.

    Deux échappatoires : un lieu épinglé — le curateur reste le dernier mot, et
    ce qui se voit très bien depuis la route est son choix — et un lieu qui
    affiche par ailleurs des HORAIRES, car une grotte aménagée porte souvent
    `access=no` parce qu'on n'y entre pas seul, la visite y étant guidée.

    Un simple site web ne suffit PAS à faire cette exception, et c'est un
    correctif : le château d'Hérouville en a un — descriptif, patrimonial —
    sans être ouvert au public, et se faisait donc réadmettre par la première
    version de ce filtre alors qu'il en est l'exemple même. Un site web prouve
    qu'un lieu existe et qu'on en parle ; seuls des horaires prouvent qu'on
    peut s'y rendre à une heure donnée.
    """
    refused = [
        p for p in places
        # Seuls des horaires renversent un accès refusé — un site web ne le
        # prouve pas, voir la docstring pour le cas du château d'Hérouville.
        if p.visitable is False and not p.pinned and not p.opening_hours
    ]
    excluded = {id(p) for p in refused}
    kept = [p for p in places if id(p) not in excluded]
    if refused:
        LOG.info(
            "accès refusé : %s lieux écartés (%s)",
            len(refused),
            ", ".join(p.name for p in refused[:5]),
        )
    return kept


def apply_alpine_filter(places: list[Place], config: Config) -> list[Place]:
    """Écarte les sommets qui, faute de preuve du contraire, ne se rejoignent
    qu'en alpinisme.

    Le château d'Hérouville avait un signal explicite — `access=private` — qui
    permet de l'écarter avec certitude. Un sommet à 3 000 m n'en a aucun : le
    pipeline ne collecte les sommets que sur Wikidata, qui ne dit rien d'un
    chemin de randonnée ou d'un accès équipé. Il n'y a donc ni preuve qu'on
    s'y rend à pied, ni preuve du contraire.

    Faute de ce signal positif, l'ambiguïté se résout par le principe que le
    curateur a posé pour ce cas précis : au moindre doute, on écarte. Un
    sommet réellement accessible malgré son altitude — l'Aiguille du Midi, le
    Pic du Midi — revient par un épinglage manuel ou une proposition de la
    communauté, jamais par une supposition du pipeline.
    """
    threshold = config.alerts.alpine_elevation_m
    kept: list[Place] = []
    dropped: list[Place] = []

    for place in places:
        suspect = (
            place.theme_id == "sommets"
            and place.elevation_m is not None
            and place.elevation_m >= threshold
        )
        if suspect and not place.pinned:
            dropped.append(place)
        else:
            kept.append(place)

    if dropped:
        LOG.info(
            "accès alpin : %s sommets écartés au-dessus de %s m, faute d'un "
            "signal d'accès prouvé (%s)",
            len(dropped),
            threshold,
            ", ".join(p.name for p in dropped[:5]),
        )
    return kept


def apply_class_exclusion(places: list[Place], config: Config) -> list[Place]:
    """Écarte les lieux qui relèvent d'une classe disqualifiante.

    Un parc d'attractions entre au catalogue par la porte des musées, parce
    qu'un de ses équipements est classé comme aquarium et qu'un aquarium public
    est, chez Wikidata, une sorte de musée. Le rattachement n'est pas faux ;
    c'est le lieu qui n'a rien à faire dans Roam.

    Le retrait est ici et non à la collecte pour deux raisons : il se rejoue en
    une seconde quand la liste change, et il peut NOMMER ce qu'il enlève. Une
    exclusion par classe est assez brutale pour mériter d'être relue — le
    Jardin des plantes abrite une ménagerie.

    Un lieu épinglé y échappe : le curateur a déjà tranché.
    """
    # Retirer une classe de `themes.yaml` ne retire RIEN de la collecte : les
    # lieux qu'elle a ramenés dorment dans `data/raw/<thème>.json` et le build
    # continue de les servir jusqu'à la prochaine collecte de ce thème. Ajouter
    # une classe demande un `fetch` ; en retirer une aussi, et c'est moins
    # évident.
    #
    # On ne peut le détecter que pour les classes GÉNÉRIQUES, seules à laisser
    # une trace sur le lieu (`via_broad_class`). C'est une couverture partielle,
    # et il vaut mieux le dire que le taire : « théâtre » a été retiré du thème
    # `monuments` après avoir fait passer le catalogue de 72 à 109 monuments, et
    # sans cette ligne les trente-sept salles de spectacle y seraient restées.
    #
    # Les lieux venus d'un label portent le même drapeau sans venir d'une classe
    # générique : ils sont exclus du compte.
    orphelins: dict[str, int] = defaultdict(int)
    sans_generique = {
        theme.id for theme in config.themes if not theme.broad_classes
    }
    for place in places:
        if place.via_broad_class and place.source != "label" and place.theme_id in sans_generique:
            orphelins[place.theme_id] += 1
    if orphelins:
        LOG.warning(
            "%s lieux viennent d'une classe générique QUE LEUR THÈME NE DÉCLARE "
            "PLUS : %s. Retirer une classe ne vide pas la collecte — relance "
            "`fetch --only %s`.",
            sum(orphelins.values()),
            ", ".join(f"{t} {n}" for t, n in sorted(orphelins.items(), key=lambda kv: -kv[1])),
            ",".join(sorted(orphelins)),
        )

    # Un thème peut, lui aussi, attendre une classe : `monuments` attend celle
    # des salles de spectacle depuis qu'on s'est aperçu que l'Opéra Garnier
    # n'était nulle part. Tant qu'elle n'est pas résolue, le thème tourne sans
    # elle — et rien ne le disait, puisque l'avertissement de `fetch` ne se
    # déclenche que pour un thème SANS aucune classe.
    attente = [
        (theme.id, terme) for theme in config.themes for terme in theme.search
    ]
    if attente:
        LOG.warning(
            "%s classe(s) de thème sans Q-id — ces lieux ne sont pas collectés : "
            "%s. `probe` nomme la classe sur une entité, `suggest-qids` propose.",
            len(attente),
            ", ".join(f"{theme} « {terme} »" for theme, terme in attente),
        )

    # Un terme d'exclusion resté sans Q-id n'écarte rien, et n'écartait rien en
    # silence. « épave » a été écrit le jour où deux navires coulés sont entrés
    # au catalogue par la porte de « site archéologique » : tant qu'il n'est pas
    # résolu, ils y restent, et seule cette ligne le dit.
    if config.exclusions.search:
        LOG.warning(
            "%s terme(s) d'exclusion sans Q-id — ils n'écartent RIEN : %s. "
            "`suggest-qids` propose, `verify-qids` confirme.",
            len(config.exclusions.search),
            ", ".join(config.exclusions.search),
        )

    if not config.exclusions.qids:
        return places

    kept: list[Place] = []
    dropped: list[Place] = []
    for place in places:
        if place.excluded_class and not place.pinned:
            dropped.append(place)
        else:
            kept.append(place)

    if dropped:
        by_class: dict[str, list[str]] = {}
        for place in dropped:
            by_class.setdefault(place.excluded_class or "?", []).append(place.name)
        LOG.info("classes écartées : %s lieux retirés", len(dropped))
        for label, names in sorted(by_class.items(), key=lambda kv: -len(kv[1])):
            shown = ", ".join(sorted(names)[:8])
            more = f" (+{len(names) - 8})" if len(names) > 8 else ""
            LOG.info("    %-24s %3d — %s%s", label, len(names), shown, more)

    # Le filtre ne peut écarter que ce qu'il a REGARDÉ, et son drapeau vient
    # d'`enrich`, qui interroge Wikidata. Un lieu jamais vérifié le traverse
    # sans un mot : le Parc Astérix, Nigloland et Marineland sont ainsi rentrés
    # trois fois en quatre jours, chaque fois en silence. Le silence était le
    # vrai défaut — c'est lui qu'on corrige ici.
    jamais_vus = [place for place in places if place.excluded_class is None]
    if jamais_vus:
        LOG.warning(
            "%s lieux n'ont jamais été passés au filtre des classes : ils entrent "
            "sans avoir été regardés. Lance `enrich` pour les vérifier (ex. %s)",
            len(jamais_vus),
            ", ".join(place.name for place in jamais_vus[:3]),
        )
    return kept


def _funnel(stages: list[tuple[str, list[Place]]], config: Config) -> None:
    """Combien de lieux chaque thème conserve, étape par étape.

    Chaque étape journalise déjà ce qu'elle écarte, mais chacune compte sur
    une population différente : « plancher : dunes-marais 9 » désigne neuf
    lieux parmi ceux qui ATTEIGNENT le plancher, pas parmi les candidats
    bruts. Soustraire ces lignes entre elles donne des résultats faux — je
    m'y suis laissé prendre en cherchant quinze dunes qui n'avaient jamais
    disparu.

    Un tableau qui suit les mêmes lieux d'un bout à l'autre rend la question
    lisible d'un coup d'œil, comme celui de `discover` pour les candidats.
    """
    themes = [theme.id for theme in config.themes]
    header = "".join(f"{label[:9]:>10}" for label, _ in stages)
    lines = [f"\n  Ce que chaque thème conserve, étape par étape :",
             f"      {'thème':<16}{header}"]

    for theme_id in themes:
        counts = [sum(1 for p in group if p.theme_id == theme_id) for _, group in stages]
        # Un thème qui n'a jamais eu de lieu n'apprend rien : il est déjà
        # signalé par l'avertissement des thèmes sans collection.
        if not counts[0]:
            continue
        lines.append(f"      {theme_id:<16}" + "".join(f"{n:>10}" for n in counts))

    LOG.info("\n".join(lines))


def rescue_thin_departements(
    au_dessus: list[Place], sous_le_plancher: list[Place], config: Config
) -> list[Place]:
    """Repêche les meilleurs lieux des départements que le plancher a vidés.

    Le plancher compte les langues d'un article : il mesure la notoriété
    INTERNATIONALE d'un lieu, et la France rurale n'en a pas. La Creuse gardait
    un lieu sur seize, les Ardennes trois sur vingt-neuf — pendant que Paris en
    gardait deux cent dix-huit. Ce qu'il écartait n'était pas du remplissage :
    le château d'Oiron, les boiseries de Moutier-d'Ahun, les Pierres Jaumâtres.

    C'est le pendant géographique du quota par département des collections
    nationales. Là on empêchait Paris d'occuper toute la place ; ici on empêche
    un département de n'en avoir aucune.

    Trois garanties. Les mieux notés d'abord, jamais au-delà du compte visé.
    Aucun sosie : une seconde fiche Wikidata du même site — « abbaye royale
    de Saint-Denis » à côté de « basilique Saint-Denis » — échappe au
    dédoublonnage, qui ne compare qu'à l'intérieur d'un thème. Et aucun thème
    ne rafle le département : le premier jet donnait sept châteaux sur douze
    en Seine-Saint-Denis et sept sur douze au Territoire de Belfort. Un
    « meilleur de » qui n'est qu'une liste de châteaux ne donne envie d'aucun
    des douze.

    Comme le quota géographique des collections nationales, celui-ci ne
    RÉTRÉCIT jamais : si le département n'a vraiment que des châteaux à
    offrir, un second passage lève le plafond. Mieux vaut sept châteaux qu'un
    département à neuf lieux.
    """
    cible = config.collections.min_per_departement
    if not cible:
        return au_dessus

    compte: Counter[str] = Counter(
        place.departement_code for place in au_dessus if place.departement_code
    )
    deja = [(place.lat, place.lon) for place in au_dessus]
    candidats: dict[str, list[Place]] = defaultdict(list)
    for place in sorted(sous_le_plancher, key=lambda p: -p.score):
        if place.departement_code and compte[place.departement_code] < cible:
            candidats[place.departement_code].append(place)

    repeches: list[Place] = []
    for code, lot in candidats.items():
        manque = cible - compte[code]
        # Aucun thème au-delà du tiers des places à pourvoir, avec deux comme
        # plancher : sur trois places à combler, interdire un deuxième château
        # reviendrait à préférer un lieu médiocre d'un autre thème.
        plafond = max(2, math.ceil(manque / 3))
        par_theme: Counter[str] = Counter()
        retenus: set[str] = set()

        def accepter(place: Place) -> bool:
            if any(haversine_m(place.lat, place.lon, lat, lon) < DUPLICATE_DISTANCE_M
                   for lat, lon in deja):
                return False
            place.geo_rescued = True
            repeches.append(place)
            deja.append((place.lat, place.lon))
            retenus.add(place.wikidata_id)
            par_theme[place.theme_id] += 1
            return True

        # Le plafond MONTE d'un cran tant qu'il reste des places, il ne saute
        # pas : le supprimer d'un coup rendait la main au score seul, qui
        # reprenait des châteaux alors que des jardins attendaient. On sert
        # donc un deuxième château quand chaque thème a eu son premier.
        # Le plafond borné par le lot garantit la sortie : au-delà, aucun
        # compteur de thème ne peut plus l'atteindre, donc le dernier passage a
        # forcément examiné tous les candidats. Un candidat refusé comme sosie
        # n'entre jamais dans `retenus` — s'en servir comme condition d'arrêt
        # faisait boucler sans fin.
        limite = max(plafond, len(lot))
        while manque > 0 and plafond <= limite:
            avant = manque
            for place in lot:
                if manque <= 0:
                    break
                if place.wikidata_id in retenus:
                    continue
                if par_theme[place.theme_id] >= plafond:
                    continue
                if accepter(place):
                    manque -= 1
            if manque == avant:  # plus rien à prendre à ce plafond
                plafond += 1

    if repeches:
        par_dept = Counter(p.departement_code for p in repeches)
        LOG.info(
            "repêchage géographique : %s lieux dans %s départements sous %s "
            "(les plus fournis : %s)",
            len(repeches), len(par_dept), cible,
            ", ".join(f"{c} {n}" for c, n in par_dept.most_common(5)),
        )
    return au_dessus + repeches


def build_all(places: list[Place], config: Config) -> tuple[list[Place], list[Collection]]:
    # L'ordre compte : on fixe d'abord le thème de chaque lieu, puis on lui
    # applique le plancher de CE thème, puis on écarte les doublons de lieu.
    #
    # Les étapes sont déroulées une à une plutôt qu'imbriquées : c'est ce qui
    # permet de garder chaque population intermédiaire et d'en tirer
    # l'entonnoir par thème.
    en_france = apply_geographic_scope(places, config)
    un_theme = dedupe_across_themes(en_france, config)
    dans_le_sujet = apply_class_exclusion(un_theme, config)
    # Pour un thème qui n'existe que par ses listes, en sortir c'est sortir.
    sur_liste = apply_list_membership(dans_le_sujet, config)
    accessible = apply_access_filter(sur_liste, config)
    non_alpin = apply_alpine_filter(accessible, config)
    au_dessus = apply_notoriety_floor(non_alpin, config)
    # Le plafond par commune vient APRÈS le plancher : il ne doit trancher
    # qu'entre des lieux déjà jugés dignes.
    sous_plafond = apply_commune_cap(au_dessus, config)
    # Les sosies partent AVANT le comptage par département. Compter d'abord
    # faisait croire un département complet alors qu'une de ses douze fiches
    # était un doublon promis à disparaître : les Ardennes et le Val-de-Marne
    # finissaient à onze, sans que rien ne le dise.
    # Le plafond de thème AVANT le repêchage, mais le repêchage est prévenu :
    # c'est la seule composition qui tienne. Après lui, le plafond vidait les
    # départements que le repêchage venait de remplir — les Landes, l'Orne,
    # l'Essonne et le Territoire de Belfort perdaient leur « Le meilleur de… ».
    # Avant lui et sans précaution, le repêchage remontait des cathédrales
    # restées sous le plancher pour combler ces mêmes départements, et
    # quatre-vingts redevenaient quatre-vingt-dix-sept.
    sous_cap = apply_theme_cap(sous_plafond, config)
    sans_sosie = dedupe(sous_cap)
    # Le plancher mesure la documentation, qui est très inégalement répartie sur
    # le territoire. On rend leur part aux départements qu'il a vidés. Les
    # candidats sont ceux que le PLANCHER a écartés — pas les sosies, qui ont
    # déjà leur représentant au catalogue, ni les thèmes dont le plafond est
    # atteint : le repêchage comble un territoire, il ne rouvre pas un quota.
    gardes = {place.wikidata_id for place in au_dessus}
    # Le repêchage reste ouvert aux thèmes qui ont de la place — neuf musées
    # partis en doublons en laissent — mais le plafond repasse APRÈS lui pour
    # tenir le compte. Sans ce second passage il ajoutait sans budget : cent
    # cinquante musées devenaient cent soixante-huit.
    satures = saturated_themes(sans_sosie, config)
    complete = rescue_thin_departements(
        sans_sosie,
        [p for p in non_alpin
         if p.wikidata_id not in gardes and p.theme_id not in satures],
        config,
    )
    # Second passage : les repêchés peuvent se doublonner entre eux.
    dedouble = dedupe(complete)
    # Et le plafond une seconde fois, qui tient le compte final. Il ne peut pas
    # remplacer le premier : appliqué SEUL après le repêchage, il vidait les
    # départements que celui-ci venait de remplir. Appliqué seul avant, il
    # laissait le repêchage le dépasser. Les deux ensemble laissent le
    # repêchage garnir les départements pauvres — c'est ainsi que l'écomusée de
    # Martinique, quatre langues pour un plancher à douze, reste au catalogue —
    # sans que le thème dépasse son compte.
    kept = apply_theme_cap(dedouble, config)

    _funnel(
        [
            ("bruts", places),
            ("France", en_france),
            ("1 thème", un_theme),
            ("sujet", dans_le_sujet),
            ("sur liste", sur_liste),
            ("accès", accessible),
            ("non alpin", non_alpin),
            ("plancher", au_dessus),
            ("commune", sous_plafond),
            ("plafond thème", sous_cap),
            ("sosies", sans_sosie),
            ("dépt pauvre", complete),
            ("dédoublé", dedouble),
            ("cap final", kept),
        ],
        config,
    )
    collections = drop_twin_collections(
        build_theme_collections(kept, config)
        + build_label_collections(kept, config)
        + build_geo_collections(kept, config)
        + build_cross_collections(kept, config)
    )

    # Un lieu qui n'entre dans aucune collection ne sert à rien : on le sort.
    used = {cp.place_id for c in collections for cp in c.places}
    retained = [p for p in kept if p.wikidata_id in used]
    LOG.info(
        "%s collections, %s lieux retenus (%s écartés faute de collection)",
        len(collections),
        len(retained),
        len(kept) - len(retained),
    )
    return retained, collections
