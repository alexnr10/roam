"""Où tombe ce point ? Rattachement administratif sans aucun service national.

Le pipeline demandait sa commune et son département à deux API de l'État
français — `api-adresse.data.gouv.fr` et `geo.api.gouv.fr`. Gratuites, sans
clé, excellentes, et strictement françaises : c'était, de tout le pipeline, la
dépendance la plus difficile à porter ailleurs.

Or on télécharge DÉJÀ les contours administratifs pour dessiner la carte de
conquête. La même donnée répond à la question « quel territoire contient ce
point ? », localement, sans réseau et sans attendre. Ce module ne fait que
poser la question au bon endroit.

Il ne connaît ni la France ni l'Italie : il reçoit des couches de zones — un
code, un nom, un parent, des polygones — et répond. Ce sont la configuration
et les fichiers qui disent de quel pays on parle.

**Le rayon-casting plutôt qu'une bibliothèque.** Shapely ferait cela mieux et
plus vite, mais elle demande GEOS compilé, ce qu'un téléphone sous Termux
n'offre pas sans peine. La règle du pair-impair tient en trente lignes, et son
seul piège — un sommet exactement à la latitude du rayon, compté deux fois —
se règle par la comparaison asymétrique `(y1 > y) != (y2 > y)`.
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

LOG = logging.getLogger(__name__)

Anneau = list[tuple[float, float]]
"""Un contour fermé, en (longitude, latitude)."""


@dataclass(frozen=True)
class Zone:
    """Un territoire : ce qu'il faut pour le reconnaître et le nommer."""

    code: str
    name: str
    level: str
    parent_code: str | None
    #: (ouest, sud, est, nord) — le filtre à un coup avant tout calcul.
    bbox: tuple[float, float, float, float]
    #: Chaque polygone est son contour suivi de ses trous.
    polygones: list[list[Anneau]] = field(default_factory=list)

    def contient(self, lon: float, lat: float) -> bool:
        ouest, sud, est, nord = self.bbox
        if not (ouest <= lon <= est and sud <= lat <= nord):
            return False
        return any(_dans_polygone(lon, lat, anneaux) for anneaux in self.polygones)


def _dans_anneau(lon: float, lat: float, anneau: Anneau) -> bool:
    """Règle du pair-impair : un rayon vers l'est croise-t-il un nombre impair d'arêtes ?"""
    dedans = False
    n = len(anneau)
    for i in range(n):
        x1, y1 = anneau[i]
        x2, y2 = anneau[(i + 1) % n]
        # Asymétrique à dessein : un sommet pile à la latitude du rayon
        # appartient à l'arête du dessus et pas à celle du dessous, sans quoi
        # il compte deux fois et le point bascule du mauvais côté.
        if (y1 > lat) != (y2 > lat):
            x = x1 + (lat - y1) * (x2 - x1) / (y2 - y1)
            if lon < x:
                dedans = not dedans
    return dedans


def _dans_polygone(lon: float, lat: float, anneaux: Sequence[Anneau]) -> bool:
    """Dans le contour et dans aucun trou. Un lac ne rattache pas sa commune."""
    if not anneaux or not _dans_anneau(lon, lat, anneaux[0]):
        return False
    return not any(_dans_anneau(lon, lat, trou) for trou in anneaux[1:])


def _bbox(polygones: Iterable[list[Anneau]]) -> tuple[float, float, float, float]:
    xs: list[float] = []
    ys: list[float] = []
    for anneaux in polygones:
        for x, y in anneaux[0]:
            xs.append(x)
            ys.append(y)
    if not xs:
        return (0.0, 0.0, -1.0, -1.0)   # emprise vide : ne contient rien
    return (min(xs), min(ys), max(xs), max(ys))


def _anneaux_de(geometry: dict) -> list[list[Anneau]]:
    """Les polygones d'une géométrie GeoJSON, qu'elle en porte un ou douze."""
    kind = geometry.get("type")
    if kind == "Polygon":
        bruts = [geometry.get("coordinates") or []]
    elif kind == "MultiPolygon":
        bruts = geometry.get("coordinates") or []
    else:
        return []
    return [
        [[(float(x), float(y)) for x, y, *_ in anneau] for anneau in polygone]
        for polygone in bruts
        if polygone
    ]


def zones_depuis_geojson(
    donnees: dict,
    level: str,
    code_key: str = "code",
    name_key: str = "nom",
    parent_key: str | None = None,
) -> list[Zone]:
    """Lit une couche GeoJSON. Les clés varient d'un pays à l'autre, pas le reste."""
    zones: list[Zone] = []
    for feature in donnees.get("features") or []:
        props = feature.get("properties") or {}
        code = props.get(code_key)
        if code is None:
            continue
        polygones = _anneaux_de(feature.get("geometry") or {})
        if not polygones:
            continue
        zones.append(Zone(
            code=str(code),
            name=str(props.get(name_key) or ""),
            level=level,
            parent_code=str(props[parent_key]) if parent_key and props.get(parent_key) else None,
            bbox=_bbox(polygones),
            polygones=polygones,
        ))
    return zones


def charge_couche(chemin: Path, level: str, **cles) -> list[Zone]:
    with chemin.open(encoding="utf-8") as fh:
        return zones_depuis_geojson(json.load(fh), level, **cles)


#: Côté d'une case de l'index, en degrés. Un degré fait à peu près la taille
#: d'un département : plus fin multiplierait les cases sans rien filtrer de
#: plus, plus large ferait tester la moitié du pays à chaque point.
CASE = 1.0


class Localisateur:
    """Quel territoire contient ce point ?

    Un index par cases d'un degré évite de tester cent un départements pour
    chaque point : on ne teste que ceux dont l'emprise touche la case du point.
    Sur le catalogue français — onze mille lieux — la différence est celle
    entre quelques secondes et plusieurs minutes.
    """

    def __init__(self, zones: Sequence[Zone]) -> None:
        self.zones = list(zones)
        self._cases: dict[tuple[int, int], list[Zone]] = {}
        for zone in self.zones:
            ouest, sud, est, nord = zone.bbox
            if est < ouest:
                continue
            for cx in range(math.floor(ouest / CASE), math.floor(est / CASE) + 1):
                for cy in range(math.floor(sud / CASE), math.floor(nord / CASE) + 1):
                    self._cases.setdefault((cx, cy), []).append(zone)

    def __len__(self) -> int:
        return len(self.zones)

    def contenant(self, lat: float, lon: float) -> Zone | None:
        """La zone qui contient ce point, ou None s'il n'en touche aucune."""
        case = (math.floor(lon / CASE), math.floor(lat / CASE))
        for zone in self._cases.get(case, ()):
            if zone.contient(lon, lat):
                return zone
        return None

    def autour(
        self, lat: float, lon: float, rayons: Sequence[int] = (500, 1500, 3000)
    ) -> Zone | None:
        """Comme `contenant`, mais accepte de chercher un peu à côté.

        Un contour administratif s'arrête au trait de côte. La plage de
        Pampelonne, dont Wikidata place le point à un kilomètre au large,
        n'appartenait à aucune commune — donc à aucun département, donc à
        aucune collection géographique, alors qu'elle marque le meilleur score
        du littoral de PACA après la presqu'île de Giens.

        La question devient « ce point est-il à moins de trois kilomètres d'un
        territoire ? ». Huit azimuts par rayon, du plus proche au plus
        lointain, et le premier territoire atteint gagne.

        Le rattachement reste JUSTE près d'une frontière terrestre : les
        couches ne portent que les territoires du pays, donc un sommet à cheval
        sur l'Espagne rend son versant français, jamais l'espagnol. Un point
        réellement à l'étranger ne rend rien à aucun azimut.
        """
        trouve = self.contenant(lat, lon)
        if trouve is not None:
            return trouve
        for rayon in rayons:
            for azimut in range(0, 360, 45):
                angle = math.radians(azimut)
                dlat = rayon * math.cos(angle) / 110_540
                dlon = rayon * math.sin(angle) / (
                    111_320 * math.cos(math.radians(lat)) or 1.0
                )
                trouve = self.contenant(lat + dlat, lon + dlon)
                if trouve is not None:
                    return trouve
        return None


#: Rayons de la recherche aux alentours, en mètres.
#
# Mesuré sur les 2 079 lieux du catalogue français, en comparant au verdict des
# API de l'État :
#
#     rayons                          accord   introuvables   désaccords
#     aucun (contour seul)            95,4 %             86            9
#     500 / 1500 / 3000               99,3 %              5            9
#     500 / 1500 / 3000 / 6000        99,4 %              4            9
#     + 12000                         99,4 %              2           10
#
# On s'arrête à six kilomètres : au-delà, on récupère un phare et on en perd
# un autre. À douze, Cordouan — au milieu de l'estuaire de la Gironde — se
# rattache à la Charente-Maritime, qui est l'autre rive.
RAYONS = (500, 1500, 3000, 6000)


def couches_du_pays(config, racine: Path) -> dict[str, "Localisateur"]:
    """Les localisateurs des couches présentes sur le disque, par niveau.

    Une couche absente n'est pas une erreur : le rattachement retombe alors sur
    ce qu'il faisait avant. `geo-layers` la télécharge quand on la veut.
    """
    trouves: dict[str, Localisateur] = {}
    for level, couche in config.layers.items():
        chemin = racine / config.country.code.lower() / couche.fichier
        if not chemin.exists():
            LOG.info("couche %s absente (%s) — `geo-layers` la télécharge", level, chemin)
            continue
        zones = charge_couche(
            chemin, level, code_key=couche.code_key, name_key=couche.name_key,
            parent_key=couche.parent_key,
        )
        LOG.info("couche %s : %s territoires chargés", level, len(zones))
        trouves[level] = Localisateur(zones)
    return trouves
