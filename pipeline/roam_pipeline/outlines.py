"""Contours administratifs pour la carte de conquête.

Colorier un département suppose de savoir où il commence. Ces contours ne
dépendent ni du catalogue ni des visites : ils sont produits une fois, versionnés
avec l'application, et celle-ci n'a donc rien à télécharger pour dessiner la
France.

Deux exigences se contredisent.

**La légèreté.** Les tracés de l'IGN pèsent 3,6 Mo pour les seuls départements.
Embarqués tels quels, ils pèseraient plus que tout le reste de l'application
réunie, pour un détail invisible : à l'échelle où l'on regarde un département,
un mètre de côte ne se distingue pas de son voisin.

**La jointivité.** Deux départements limitrophes doivent garder *exactement* le
même tracé de frontière commune. Simplifier chaque polygone dans son coin trahit
cette exigence : les deux versions de la frontière divergent de quelques mètres,
et la carte se fend d'un liseré de fond entre chaque aplat de couleur — un
défaut qu'on ne voit pas sur un fond blanc mais qui saute aux yeux dès que les
territoires sont coloriés.

D'où la méthode, empruntée à TopoJSON : reconstruire la topologie (le découpage
des contours en **arcs** partagés), simplifier chaque arc **une seule fois**,
puis recoudre les polygones. Les frontières restent jointives par construction,
pas par chance.
"""

from __future__ import annotations

import heapq
import json
import logging
import math
from pathlib import Path
from typing import Sequence

import requests

LOG = logging.getLogger(__name__)

# Tracés IGN (Admin Express) convertis en GeoJSON, sous Licence ouverte Etalab.
# Les fichiers « avec-outre-mer » sont les seuls à couvrir les DROM, que Roam
# inclut ; ils ne sont pas pré-simplifiés, ce qui tombe bien puisqu'on veut
# maîtriser nous-mêmes la simplification pour préserver la topologie.
BASE = "https://raw.githubusercontent.com/gregoiredavid/france-geojson/master"
SOURCES: dict[str, str] = {
    "region": f"{BASE}/regions-avec-outre-mer.geojson",
    "departement": f"{BASE}/departements-avec-outre-mer.geojson",
}

ATTRIBUTION = "Contours IGN Admin Express — Licence ouverte (Etalab)"

#: Grille de quantification, en degrés. 1e-4° vaut environ onze mètres : le pas
#: est déjà plus fin que ce que rend un pixel à l'échelle d'un département, et
#: arrondir dès l'entrée soude au passage les sommets presque confondus.
GRID = 1e-4

#: Aire minimale d'un triangle, en km², sous laquelle un sommet ne raconte plus
#: rien à l'échelle regardée. Les départements en gardent davantage que les
#: régions : on les regarde de plus près.
DEFAULT_TOLERANCE_KM2: dict[str, float] = {"region": 1.2, "departement": 0.7}

#: Un polygone plus petit que cela disparaît — sauf s'il est le seul du
#: territoire. Ce sont les îlots et les rochers, invisibles à l'écran mais
#: coûteux en octets ; le garde-fou protège Mayotte comme Saint-Nazaire.
MIN_POLYGON_KM2: float = 1.0

Point = tuple[int, int]
"""Un sommet quantifié : (longitude, latitude) en pas de `GRID`."""

Arc = tuple[Point, ...]

# Un degré de latitude, en kilomètres. La longitude, elle, se resserre vers les
# pôles : son facteur dépend de la latitude du point (cf. `_planar`).
KM_PER_DEG_LAT = 110.574
KM_PER_DEG_LON_EQUATOR = 111.320


# --------------------------------------------------------------------------- #
# Quantification
# --------------------------------------------------------------------------- #


def quantize(lon: float, lat: float, grid: float = GRID) -> Point:
    return (round(lon / grid), round(lat / grid))


def dequantize(point: Point, grid: float = GRID) -> list[float]:
    # Le nombre de décimales suit le pas : arrondir à cinq décimales un pas de
    # 1e-4 rallongerait le fichier d'un chiffre qui ne dit rien.
    digits = max(0, -math.floor(math.log10(grid)))
    return [round(point[0] * grid, digits), round(point[1] * grid, digits)]


def _dedupe(points: Sequence[Point]) -> list[Point]:
    """Retire les sommets consécutifs confondus après quantification."""
    out: list[Point] = []
    for point in points:
        if not out or out[-1] != point:
            out.append(point)
    return out


def _close(ring: list[Point]) -> list[Point]:
    if len(ring) >= 2 and ring[0] != ring[-1]:
        ring = ring + [ring[0]]
    return ring


# --------------------------------------------------------------------------- #
# Géométrie
# --------------------------------------------------------------------------- #


def _planar(points: Sequence[Point], grid: float) -> list[tuple[float, float]]:
    """Projette en kilomètres, pour raisonner en aires plutôt qu'en degrés².

    Une aire exprimée en degrés² n'a pas de sens comparable entre Dunkerque et
    Mayotte : le degré de longitude y vaut 72 km contre 110. La projection
    équirectangulaire locale suffit largement — on s'en sert pour décider quel
    sommet est négligeable, pas pour mesurer un terrain.
    """
    out: list[tuple[float, float]] = []
    for x, y in points:
        lat = y * grid
        out.append(
            (
                x * grid * KM_PER_DEG_LON_EQUATOR * math.cos(math.radians(lat)),
                lat * KM_PER_DEG_LAT,
            )
        )
    return out


def _ring_area_km2(ring: Sequence[Point], grid: float) -> float:
    """Aire du polygone, par la formule du lacet."""
    flat = _planar(ring, grid)
    total = 0.0
    for (ax, ay), (bx, by) in zip(flat, flat[1:]):
        total += ax * by - bx * ay
    return abs(total) / 2.0


# --------------------------------------------------------------------------- #
# Simplification d'un arc (Visvalingam–Whyatt)
# --------------------------------------------------------------------------- #


def simplify(arc: Sequence[Point], tolerance_km2: float, grid: float = GRID) -> list[Point]:
    """Retire les sommets dont le triangle est plus petit que la tolérance.

    Visvalingam plutôt que Douglas–Peucker : à simplification agressive, le
    premier garde le caractère d'un trait de côte (les caps restent des caps)
    là où le second le réduit à une ligne brisée. C'est une carte qu'on regarde,
    pas un cadastre.

    **Les deux extrémités ne bougent jamais** : c'est ce qui permet de recoudre
    les arcs entre eux, et donc aux frontières de rester jointives.
    """
    if len(arc) <= 2:
        return list(arc)

    flat = _planar(arc, grid)
    n = len(arc)
    alive = [True] * n
    prev = list(range(-1, n - 1))
    nxt = list(range(1, n + 1))

    def area(i: int) -> float:
        a, b, c = flat[prev[i]], flat[i], flat[nxt[i]]
        return abs((b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1])) / 2.0

    heap: list[tuple[float, int]] = [(area(i), i) for i in range(1, n - 1)]
    heapq.heapify(heap)

    while heap:
        value, i = heapq.heappop(heap)
        if not alive[i]:
            continue
        # L'aire d'un sommet grandit quand ses voisins disparaissent : une
        # entrée périmée doit être recalculée, pas appliquée telle quelle.
        current = area(i)
        if current > value + 1e-12:
            heapq.heappush(heap, (current, i))
            continue
        if current >= tolerance_km2:
            break
        alive[i] = False
        nxt[prev[i]] = nxt[i]
        prev[nxt[i]] = prev[i]
        for neighbour in (prev[i], nxt[i]):
            if 0 < neighbour < n - 1 and alive[neighbour]:
                heapq.heappush(heap, (area(neighbour), neighbour))

    return [arc[i] for i in range(n) if alive[i]]


def _simplify_loop(ring: Sequence[Point], tolerance_km2: float, grid: float) -> list[Point]:
    """Simplifie un anneau fermé sans frontière partagée (une île, une côte).

    Le premier sommet sert de point fixe : sans lui, l'anneau ne serait plus
    fermé. Et l'anneau garde au moins un triangle, faute de quoi le polygone
    disparaîtrait au lieu de maigrir.
    """
    kept = simplify(ring, tolerance_km2, grid)
    if len(kept) < 4:
        return list(ring[:4]) if len(ring) >= 4 else list(ring)
    return kept


# --------------------------------------------------------------------------- #
# Topologie
# --------------------------------------------------------------------------- #

Shape = list[list[list[Point]]]
"""Un territoire : une liste de polygones, chacun une liste d'anneaux fermés."""


def _shape_of(geometry: dict, grid: float) -> Shape:
    kind = geometry["type"]
    if kind == "Polygon":
        polygons = [geometry["coordinates"]]
    elif kind == "MultiPolygon":
        polygons = geometry["coordinates"]
    else:  # pragma: no cover - les contours administratifs n'ont pas d'autre forme
        raise ValueError(f"géométrie inattendue : {kind}")

    out: Shape = []
    for polygon in polygons:
        rings = []
        for ring in polygon:
            points = _close(_dedupe([quantize(lon, lat, grid) for lon, lat in ring]))
            if len(points) >= 4:
                rings.append(points)
        if rings:
            out.append(rings)
    return out


def _edge_key(a: Point, b: Point) -> tuple[Point, Point]:
    return (a, b) if a <= b else (b, a)


def junctions(shapes: Sequence[Shape]) -> set[Point]:
    """Sommets où le tracé change de propriétaires — les bornes des arcs.

    Un sommet est une borne dès que les deux arêtes qui l'encadrent n'ont pas
    les mêmes propriétaires : c'est là que la frontière franco-belge cesse
    d'être aussi la frontière Nord–Pas-de-Calais. Les points de rebroussement
    et les points triples en sont aussi, par leur degré.
    """
    owners: dict[tuple[Point, Point], set[int]] = {}
    degree: dict[Point, set[Point]] = {}
    for index, shape in enumerate(shapes):
        for polygon in shape:
            for ring in polygon:
                for a, b in zip(ring, ring[1:]):
                    owners.setdefault(_edge_key(a, b), set()).add(index)
                    degree.setdefault(a, set()).add(b)
                    degree.setdefault(b, set()).add(a)

    found: set[Point] = set()
    for shape in shapes:
        for polygon in shape:
            for ring in polygon:
                inner = ring[:-1]
                for i, point in enumerate(inner):
                    before = owners[_edge_key(inner[i - 1], point)]
                    after = owners[_edge_key(point, inner[(i + 1) % len(inner)])]
                    if before != after:
                        found.add(point)
    # Un sommet qui n'a pas exactement deux voisins est un embranchement : le
    # couper évite qu'un arc n'en avale un autre.
    found.update(point for point, neighbours in degree.items() if len(neighbours) != 2)
    return found


def cut(ring: Sequence[Point], bounds: set[Point]) -> list[Arc]:
    """Découpe un anneau fermé en arcs bornés par `bounds`.

    Sans borne, l'anneau reste entier : c'est une île, personne ne la partage.
    """
    inner = list(ring[:-1])
    marks = [i for i, point in enumerate(inner) if point in bounds]
    if not marks:
        return [tuple(ring)]

    rotated = inner[marks[0] :] + inner[: marks[0]]
    positions = [i for i, point in enumerate(rotated) if point in bounds]
    arcs: list[Arc] = []
    for start, end in zip(positions, positions[1:]):
        arcs.append(tuple(rotated[start : end + 1]))
    # Le dernier arc reboucle sur la première borne.
    arcs.append(tuple(rotated[positions[-1] :] + [rotated[0]]))
    return arcs


def _canonical(arc: Arc) -> Arc:
    """Représentant unique d'un arc, quel que soit son sens de parcours.

    Le même segment de frontière est parcouru dans un sens par un département
    et dans l'autre par son voisin. Sans ce pivot, il serait simplifié deux
    fois — et différemment.
    """
    reverse = arc[::-1]
    return arc if arc <= reverse else reverse


# --------------------------------------------------------------------------- #
# Construction
# --------------------------------------------------------------------------- #


def build_outlines(
    features: Sequence[dict],
    tolerance_km2: float,
    grid: float = GRID,
    min_polygon_km2: float = MIN_POLYGON_KM2,
) -> list[dict]:
    """Simplifie une collection de territoires en préservant leurs frontières."""
    shapes = [_shape_of(feature["geometry"], grid) for feature in features]
    bounds = junctions(shapes)

    cache: dict[Arc, list[Point]] = {}

    def resolve(arc: Arc) -> list[Point]:
        key = _canonical(arc)
        if key not in cache:
            if key[0] == key[-1]:
                cache[key] = _simplify_loop(key, tolerance_km2, grid)
            else:
                cache[key] = simplify(key, tolerance_km2, grid)
        kept = cache[key]
        return kept if key == arc else kept[::-1]

    out: list[dict] = []
    for feature, shape in zip(features, shapes):
        polygons: list[list[list[list[float]]]] = []
        areas: list[float] = []
        for polygon in shape:
            rings: list[list[list[float]]] = []
            for index, ring in enumerate(polygon):
                rebuilt: list[Point] = []
                for arc in cut(ring, bounds):
                    kept = resolve(arc)
                    rebuilt.extend(kept if not rebuilt else kept[1:])
                rebuilt = _close(_dedupe(rebuilt))
                # Un anneau réduit à moins d'un triangle n'est plus une surface.
                if len(rebuilt) < 4:
                    if index == 0:
                        rings = []
                        break
                    continue
                rings.append([dequantize(point, grid) for point in rebuilt])
            if not rings:
                continue
            polygons.append(rings)
            areas.append(_ring_area_km2(polygon[0], grid))

        if not polygons:
            LOG.warning("contour vide : %s", feature["properties"].get("nom"))
            continue

        # Les îlots sous le seuil s'effacent, jamais le territoire lui-même.
        biggest = max(areas)
        kept = [
            polygon
            for polygon, area in zip(polygons, areas)
            if area >= min_polygon_km2 or area == biggest
        ]

        code = str(feature["properties"]["code"])
        out.append(
            {
                "type": "Feature",
                "id": code,
                "properties": {"code": code, "nom": feature["properties"]["nom"]},
                "geometry": (
                    {"type": "Polygon", "coordinates": kept[0]}
                    if len(kept) == 1
                    else {"type": "MultiPolygon", "coordinates": kept}
                ),
            }
        )
    return out


def fetch(level: str, timeout_s: int = 120) -> list[dict]:
    url = SOURCES[level]
    LOG.info("contours %s : %s", level, url)
    response = requests.get(url, timeout=timeout_s)
    response.raise_for_status()
    return response.json()["features"]


def export(
    destination: Path,
    tolerances: dict[str, float] | None = None,
    grid: float = GRID,
    source_dir: Path | None = None,
) -> dict[str, int]:
    """Écrit `outlines.json` : une collection GeoJSON par échelle."""
    tolerances = tolerances or DEFAULT_TOLERANCE_KM2
    payload: dict[str, object] = {"attribution": ATTRIBUTION}
    counts: dict[str, int] = {}

    for level in SOURCES:
        if source_dir is not None:
            raw = json.loads((source_dir / f"{level}.geojson").read_text(encoding="utf-8"))
            features = raw["features"]
        else:
            features = fetch(level)
        simplified = build_outlines(features, tolerances[level], grid)
        payload[level] = {"type": "FeatureCollection", "features": simplified}
        counts[level] = len(simplified)
        LOG.info(
            "%-12s %3d territoires, %6d sommets",
            level,
            len(simplified),
            sum(_vertices(feature) for feature in simplified),
        )

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    return counts


def _vertices(feature: dict) -> int:
    geometry = feature["geometry"]
    polygons = (
        [geometry["coordinates"]]
        if geometry["type"] == "Polygon"
        else geometry["coordinates"]
    )
    return sum(len(ring) for polygon in polygons for ring in polygon)
