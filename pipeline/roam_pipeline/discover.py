"""Rapprochement du catalogue et des sites de visite d'OpenStreetMap.

Deux questions, une même source :

1. **Ce lieu se visite-t-il ?** Le catalogue contient des lieux fermés au
   public, faute d'un signal pour les repérer.
2. **Que manque-t-il au catalogue ?** Partir de la notoriété encyclopédique
   fait rater les lieux très visités mais peu documentés.
"""

from __future__ import annotations

import logging

from .collections import haversine_m
from .models import Place
from .overpass import OsmPlace

LOG = logging.getLogger(__name__)

# En deçà, on considère qu'OpenStreetMap et Wikidata décrivent le même site.
SAME_PLACE_M = 350.0

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
    ("historic", "memorial", "monuments"),
    ("historic", "ruins", "monuments"),
    ("tourism", "museum", "musees"),
    ("tourism", "gallery", "musees"),
    ("tourism", "zoo", "musees"),
    ("tourism", "aquarium", "musees"),
    ("tourism", "theme_park", "musees"),
    ("tourism", "viewpoint", "monuments"),
    ("tourism", "artwork", "monuments"),
    ("tourism", "attraction", "monuments"),
    ("leisure", "garden", "jardins"),
    ("leisure", "nature_reserve", "plages"),
    ("natural", "cave_entrance", "grottes"),
    ("natural", "waterfall", "cascades"),
    ("natural", "peak", "sommets"),
    ("natural", "beach", "plages"),
]


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

    def near(self, lat: float, lon: float, radius_m: float):
        cx, cy = _key(lat, lon)
        best, best_distance = None, radius_m
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for item in self._cells.get((cx + dx, cy + dy), ()):
                    ilat, ilon = self._position(item)
                    distance = haversine_m(lat, lon, ilat, ilon)
                    if distance < best_distance:
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
            found = index.near(place.lat, place.lon, SAME_PLACE_M)
        if found is None:
            continue

        place.osm_id = found.osm_id
        place.opening_hours = found.opening_hours
        place.website = found.website
        # Un site géré est ouvert au public. L'absence de balise ne prouve rien :
        # on laisse alors `None`, qui n'est pas « fermé ».
        if found.managed:
            place.visitable = True
        matched += 1

    LOG.info(
        "ouverture au public : %s lieux rapprochés d'OpenStreetMap, dont %s ouverts",
        matched,
        sum(1 for p in places if p.visitable),
    )
    return matched


def find_candidates(places: list[Place], osm: list[OsmPlace]) -> list[OsmPlace]:
    """Sites de visite qu'OpenStreetMap connaît et que le catalogue ignore.

    Seuls les sites manifestement gérés sont retenus : sans horaires, sans site
    web et sans mention de tarif, rien ne distingue un lieu de visite d'un
    simple point d'intérêt.
    """
    known_qids = {p.wikidata_id for p in places}
    index = _Index(places, lambda p: (p.lat, p.lon))
    candidates: list[OsmPlace] = []

    for site in osm:
        if not site.managed:
            continue
        if site.wikidata_id and site.wikidata_id in known_qids:
            continue
        if index.near(site.lat, site.lon, SAME_PLACE_M) is not None:
            continue
        if guess_theme(site.tags) is None:
            continue
        candidates.append(site)

    # Les mieux documentés d'abord : un site avec horaires, tarif et lien
    # encyclopédique est un candidat plus sûr qu'un simple site web.
    candidates.sort(key=_confidence, reverse=True)
    LOG.info("candidats : %s sites de visite absents du catalogue", len(candidates))
    return candidates


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

