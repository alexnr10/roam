"""Rapprochement du catalogue et des sites de visite d'OpenStreetMap.

Deux questions, une même source :

1. **Ce lieu se visite-t-il ?** Le catalogue contient des lieux fermés au
   public, faute d'un signal pour les repérer.
2. **Que manque-t-il au catalogue ?** Partir de la notoriété encyclopédique
   fait rater les lieux très visités mais peu documentés.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from collections.abc import Callable

from .collections import haversine_m
from .models import Place
from .overpass import OsmPlace

LOG = logging.getLogger(__name__)

# En deçà, on considère qu'OpenStreetMap et Wikidata décrivent le même site —
# à condition que les noms concordent.
SAME_PLACE_M = 350.0

# En deçà de cette distance, deux objets sont le même site quoi qu'en disent
# leurs noms : Wikidata place souvent son point au centre de l'édifice là où
# OpenStreetMap le pose sur l'entrée.
IDENTICAL_M = 80.0

# Mots vides des toponymes français : les garder ferait concorder « château de
# la Roche » avec « moulin de la Roche ».
STOPWORDS = {
    "de", "du", "des", "la", "le", "les", "l", "d", "au", "aux", "et", "en",
    "sur", "sous", "parc", "site", "ancien", "ancienne", "saint", "sainte",
    "notre", "dame",
}

# Le mot qui dit la NATURE du lieu. Il ne sert pas à rapprocher — « Roche » se
# retrouve dans tous les toponymes — mais à écarter : « château de la Roche »
# et « moulin de la Roche » partagent leur partie distinctive et désignent
# pourtant deux bâtiments différents.
#
# « mont » en est volontairement absent : l'abbaye du Mont-Saint-Michel et le
# Mont-Saint-Michel sont bien le même lieu.
TYPES = {
    "chateau", "moulin", "eglise", "cathedrale", "basilique", "abbaye",
    "prieure", "chapelle", "musee", "jardin", "grotte", "gouffre", "cascade",
    "pont", "viaduc", "aqueduc", "phare", "fort", "manoir", "tour", "ferme",
    "dolmen", "menhir", "villa", "maison",
}

# Catégories OpenStreetMap → thèmes Roam. Une proposition, pas un verdict :
# la colonne reste modifiable dans la feuille de candidats.
THEME_BY_TAG: list[tuple[str, str, str]] = [
    ("historic", "castle", "chateaux"),
    ("historic", "manor", "chateaux"),
    ("historic", "fort", "chateaux"),
    ("historic", "archaeological_site", "megalithes"),
    ("historic", "aqueduct", "ponts"),
    ("historic", "city_gate", "monuments"),
    ("historic", "monument", "monuments"),
    ("historic", "ruins", "monuments"),
    ("tourism", "museum", "musees"),
    ("tourism", "gallery", "musees"),
    ("tourism", "zoo", "musees"),
    ("tourism", "aquarium", "musees"),
    ("tourism", "theme_park", "musees"),
    ("tourism", "attraction", "monuments"),
    ("leisure", "garden", "jardins"),
    ("leisure", "nature_reserve", "plages"),
    ("natural", "cave_entrance", "grottes"),
    ("natural", "waterfall", "cascades"),
]


def _tokens(name: str) -> set[str]:
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    return {
        word
        for word in re.split(r"[^a-z0-9]+", plain)
        if len(word) >= 4 and word not in STOPWORDS
    }


def names_match(left: str, right: str) -> bool:
    """Deux noms désignent-ils vraisemblablement le même lieu ?

    Le rapprochement par simple distance apparie n'importe quoi dès que la
    densité augmente : un château et le point de vue d'en face sont à deux cents
    mètres l'un de l'autre. Le nom tranche, en deux temps — une nature de lieu
    qui diffère suffit à écarter, puis une partie distinctive commune à
    rapprocher.
    """
    a, b = _tokens(left), _tokens(right)
    left_type, right_type = a & TYPES, b & TYPES
    if left_type and right_type and not (left_type & right_type):
        return False

    distinctive_a, distinctive_b = a - TYPES, b - TYPES
    if not distinctive_a or not distinctive_b:
        return False
    return bool(distinctive_a & distinctive_b)


def guess_theme(tags: dict[str, str]) -> str | None:
    """Thème Roam le plus plausible pour un objet OpenStreetMap."""
    for key, value, theme_id in THEME_BY_TAG:
        if tags.get(key) == value:
            return theme_id
    return None


# Environ un kilomètre de côté : assez fin pour que chaque case ne contienne
# qu'une poignée de points, assez large pour que le voisinage tienne en neuf.
GRID = 100.0


def _key(lat: float, lon: float) -> tuple[int, int]:
    return (int(lat * GRID / 100 * 100), int(lon * GRID / 100 * 100))


class _Index:
    """Index spatial rudimentaire.

    Comparer chaque lieu du catalogue à chaque site d'OpenStreetMap ferait des
    dizaines de millions de calculs de distance. Un simple découpage en cases
    ramène la recherche au voisinage immédiat.
    """

    def __init__(self, items, position) -> None:
        self._cells: dict[tuple[int, int], list] = {}
        self._position = position
        for item in items:
            lat, lon = position(item)
            self._cells.setdefault(_key(lat, lon), []).append(item)

    def near(self, lat: float, lon: float, radius_m: float, name: str | None = None):
        """Voisin le plus proche. Avec un `name`, le nom doit concorder au-delà
        de la distance d'identité."""
        cx, cy = _key(lat, lon)
        best, best_distance = None, radius_m
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for item in self._cells.get((cx + dx, cy + dy), ()):
                    ilat, ilon = self._position(item)
                    distance = haversine_m(lat, lon, ilat, ilon)
                    if distance >= best_distance:
                        continue
                    if (
                        name is not None
                        and distance > IDENTICAL_M
                        and not names_match(name, getattr(item, "name", ""))
                    ):
                        continue
                    best, best_distance = item, distance
        return best


def apply_visit_info(places: list[Place], osm: list[OsmPlace]) -> int:
    """Reporte l'ouverture au public sur les lieux du catalogue.

    Le rapprochement se fait d'abord par identifiant Wikidata, qu'OpenStreetMap
    porte souvent, puis par proximité — deux descriptions du même site ne sont
    jamais à plus de quelques centaines de mètres l'une de l'autre.
    """
    by_qid = {o.wikidata_id: o for o in osm if o.wikidata_id}
    index = _Index(osm, lambda o: (o.lat, o.lon))
    matched = 0

    for place in places:
        found = by_qid.get(place.wikidata_id)
        if found is None:
            found = index.near(place.lat, place.lon, SAME_PLACE_M, place.name)
        if found is None:
            continue

        place.osm_id = found.osm_id
        place.opening_hours = found.opening_hours
        place.website = found.website
        # Trois états, et pas deux. Un site géré est ouvert ; un accès
        # explicitement refusé est fermé ; tout le reste reste inconnu.
        #
        # L'absence d'horaires ne dit rien : 62 % des objets rapprochés n'en
        # portent pas, y compris des lieux qui se visitent parfaitement. En
        # faire un signal de fermeture aurait signalé la moitié du catalogue.
        #
        # L'ordre compte, et c'est l'accueil qui l'emporte. Sur une grotte
        # aménagée, `access=no` dit qu'on n'entre pas seul — pas qu'on n'entre
        # pas : la visite est guidée, et les horaires en attestent. Prendre le
        # refus d'abord écartait la grotte des Planches et celle de Marsoulas,
        # qui se visitent l'une et l'autre.
        if found.managed:
            place.visitable = True
        elif found.closed:
            place.visitable = False
        matched += 1

    LOG.info(
        "ouverture au public : %s lieux rapprochés d'OpenStreetMap, dont %s ouverts",
        matched,
        sum(1 for p in places if p.visitable),
    )
    return matched


def _atteste(site: OsmPlace, sans_portes: set[str]) -> bool:
    """Ce site mérite-t-il d'être proposé au curateur ?

    Deux preuves possibles, et il en faut une.

    Un site GÉRÉ — horaires, tarif, site web — accueille manifestement du
    public. C'est le signal qu'aucune source encyclopédique ne donne, et il
    a ramené neuf cents lieux.

    Mais il ne se pose que là où quelqu'un ouvre et ferme, et il écartait
    donc la totalité des cascades : zéro sur les quatre-vingt-six du
    catalogue ne vient d'OpenStreetMap, alors que `natural=waterfall` est
    demandé à Overpass depuis le début. Une chute d'eau n'a ni guichet ni
    horaires — c'est le même biais que le bonus d'accueil du public dans le
    score, et il se corrige de la même façon.

    Sur un thème sans portes, la preuve devient donc encyclopédique : une fiche
    Wikidata. Elle n'ouvre pas la porte à tout ruisseau cartographié — il faut
    que quelqu'un ait écrit sur ce lieu — et elle ne dispense de rien ensuite :
    le candidat entre dans la revue comme les autres, non épinglé.

    Wikidata et non Wikipédia, pour une raison pratique : `adopt` exige un
    Q-id, et un candidat qu'on ne peut pas adopter n'a rien à faire dans la
    feuille. Ce que cette porte vise, ce sont les lieux qui ONT une fiche
    Wikidata mais trop peu de langues pour franchir le plancher de collecte —
    précisément la population que le plancher rend invisible.
    """
    if site.managed:
        return True
    theme_id = guess_theme(site.tags)
    return bool(theme_id in sans_portes and site.wikidata_id)


def find_candidates(
    places: list[Place], osm: list[OsmPlace], sans_portes: set[str] | None = None
) -> list[OsmPlace]:
    """Sites de visite qu'OpenStreetMap connaît et que le catalogue ignore.

    Un site géré est retenu d'office. Sur les thèmes sans portes ni horaires,
    où « géré » ne veut rien dire, un lien encyclopédique en tient lieu.
    """
    sans_portes = sans_portes or set()
    known_qids = {p.wikidata_id for p in places}
    index = _Index(places, lambda p: (p.lat, p.lon))
    candidates: list[OsmPlace] = []
    # « thème reconnu » ne figure pas dans l'entonnoir : toutes les catégories
    # demandées à Overpass ont une correspondance, l'étape ne retire jamais
    # rien. Compter un filtre qui ne filtre pas donne l'illusion d'un contrôle.
    funnel = {"lus": len(osm), "gérés": 0, "absents": 0, "documentés": 0}

    for site in osm:
        if not _atteste(site, sans_portes):
            continue
        funnel["gérés"] += 1
        if site.wikidata_id and site.wikidata_id in known_qids:
            continue
        if index.near(site.lat, site.lon, SAME_PLACE_M, site.name) is not None:
            continue
        funnel["absents"] += 1
        if guess_theme(site.tags) is None:
            continue
        if site.wikidata_id or site.wikipedia:
            funnel["documentés"] += 1
        candidates.append(site)

    # Les mieux documentés d'abord : un site avec horaires, tarif et lien
    # encyclopédique est un candidat plus sûr qu'un simple site web.
    candidates.sort(key=_confidence, reverse=True)
    LOG.info("entonnoir des candidats : %s", ", ".join(f"{k} {v}" for k, v in funnel.items()))
    return candidates


def keep_in_france(
    sites: list[OsmPlace], locate: Callable[[list[tuple[str, float, float]]], dict[str, str]]
) -> list[OsmPlace]:
    """Écarte les candidats situés hors de France, et situe les autres.

    La collecte OpenStreetMap part d'un rectangle, et un rectangle autour de la
    France déborde sur six pays. Rien en aval ne le rattrapait : les lieux du
    catalogue viennent de Wikidata, où la nationalité est filtrée à la source,
    si bien que le contrôle de périmètre ne s'appliquait qu'à eux. Les candidats
    y échappaient entièrement.

    Le contrôle porte donc ici, sur les coordonnées, seule information dont on
    dispose à coup sûr. Il rapporte au passage le département, qui rend la
    feuille de candidats lisible : savoir où est un lieu aide à juger s'il vaut
    le détour.
    """
    if not sites:
        return []

    found = locate([(site.osm_id, site.lat, site.lon) for site in sites])
    kept: list[OsmPlace] = []
    for site in sites:
        departement = found.get(site.osm_id)
        if not departement:
            continue
        site.departement = departement
        kept.append(site)

    rejected = len(sites) - len(kept)
    if rejected:
        # « sans commune » et non « hors de France » : un point posé en mer —
        # une réserve de baie, un phare sur son rocher — n'appartient à aucun
        # polygone communal sans être pour autant à l'étranger.
        LOG.info(
            "périmètre : %s candidats sans commune française écartés (hors de "
            "France, ou en mer) : %s",
            rejected,
            ", ".join(s.name for s in sites if s.departement is None)[:120],
        )
    return kept


def is_confident(site: OsmPlace) -> bool:
    """Candidat assez solide pour être proposé sans réserve.

    Un site web ne prouve pas grand-chose — beaucoup de lieux privés en ont un.
    Des horaires ou un tarif disent l'accueil du public, et un lien
    encyclopédique dit qu'il y a quelque chose à voir. Les deux ensemble
    décrivent exactement ce qui manquait au catalogue : très visité, peu
    documenté par les classes Wikidata.
    """
    return bool((site.opening_hours or site.fee) and (site.wikidata_id or site.wikipedia))


def _confidence(site: OsmPlace) -> tuple[int, str]:
    score = 0
    if site.wikidata_id or site.wikipedia:
        score += 4
    if site.opening_hours:
        score += 2
    if site.fee:
        score += 1
    if site.website:
        score += 1
    return (score, site.name)

