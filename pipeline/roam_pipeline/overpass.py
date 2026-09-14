"""OpenStreetMap, via Overpass.

Wikidata dit si un lieu est DOCUMENTÉ. Il ne dit pas s'il se visite. C'est la
faille de fond du catalogue : le château d'Hérouville y figure alors qu'il est
fermé, et les jardins de Giverny en sont absents alors qu'on y vient du monde
entier.

OpenStreetMap répond à l'autre question. Un lieu qui porte des `opening_hours`,
un `website` ou un `fee` est un site géré, qui accueille du public — c'est un
fait de terrain, pas une mesure de notoriété. Ces balises sont posées par des
gens qui sont passés devant.

Deux usages en découlent :

- pour un lieu déjà au catalogue, savoir s'il se visite ;
- pour un lieu absent, le proposer comme candidat.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

import requests

LOG = logging.getLogger(__name__)

ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
USER_AGENT = "RoamCatalogBot/0.1 (https://github.com/alexnr10/roam) python-requests"

# Emprise de la France métropolitaine, découpée en cellules : une requête
# unique sur tout le pays dépasse le temps imparti par Overpass.
#
# Une emprise est un RECTANGLE, et celui de la France en couvre six voisins :
# l'Allemagne rhénane, la Suisse, le nord de l'Italie, la Catalogne, la
# Belgique et le sud de l'Angleterre. La première version des candidats en
# était pleine — Zoo Basel, Pinacoteca di Brera, Museu Picasso. Le rectangle
# sert à découper le travail, il ne dit pas où est la France : c'est
# `FRANCE_AREA` ci-dessous qui la délimite.
FRANCE_BBOX = (41.3, -5.2, 51.2, 9.6)
CELL_DEGREES = 2.0

# Frontière du pays telle qu'OpenStreetMap la trace. Overpass la résout en zone
# et l'applique à chaque clause : aucun objet situé hors du territoire ne peut
# plus remonter.
#
# Le code ISO vient de la configuration — c'est la SEULE chose qui change d'un
# pays à l'autre dans cette requête, avec le rectangle de découpe. Tant qu'il
# vivait en dur ici, `discover` refusait de tourner ailleurs qu'en France, et
# le catalogue italien est resté sans une seule donnée d'accueil du public.
def pays_area(code: str = "FR") -> str:
    return f'area["ISO3166-1"="{code.upper()}"][admin_level=2]->.pays;'


FRANCE_AREA = pays_area("FR")

# Emprise minuscule au centre de Paris — le Louvre, l'Orangerie, les Tuileries.
# Toute requête correcte y trouve quelque chose. Une réponse vide ne peut donc
# vouloir dire qu'une chose : la zone du pays n'a pas été résolue. Sans ce
# contrôle, la collecte entière reviendrait vide au bout de vingt minutes sans
# qu'aucune erreur ne soit levée.
#
# Hors de France, le témoin se dérive du catalogue : voir `temoin_autour`.
PROBE_CELL = (48.855, 2.32, 48.87, 2.35)


def temoin_autour(lat: float, lon: float, cote: float = 0.015):
    """Une cellule témoin autour d'un lieu que l'on sait présent chez OSM.

    Le témoin parisien ne vaut que pour la France. Ailleurs, le meilleur lieu
    du catalogue fait l'affaire — le Colisée, la basilique Saint-Pierre : s'ils
    ne remontent pas, c'est la zone du pays qui n'a pas été résolue, et non la
    région qui serait vide.
    """
    return (lat - cote, lon - cote, lat + cote, lon + cote)

# Catégories susceptibles de porter un lieu de visite.
#
# La première version en ramenait 290 000 sur la France. Quatre catégories
# faisaient l'essentiel du volume sans jamais désigner un lieu de collection :
# `historic=memorial` (chaque monument aux morts communal), `tourism=artwork`
# (chaque statue de square), `tourism=viewpoint` (chaque banc panoramique) et
# `natural=peak` (chaque cote de l'IGN dans les Alpes). Elles sont retirées.
#
# `natural=peak` et `natural=beach` restent par ailleurs mieux servis par
# Wikidata, qui distingue le sommet remarquable de la simple altitude nommée.
TAG_FILTERS = [
    'tourism~"^(museum|gallery|zoo|aquarium|theme_park|attraction)$"',
    'historic~"^(castle|fort|manor|monument|ruins|archaeological_site|city_gate|aqueduct)$"',
    # `nature_reserve` est parti avec sa porte : rangé dans « Littoral et
    # plages », il rapportait 630 aires protégées en Italie — 42 % de la
    # feuille — et zéro lieu retenu en France. Voir `discover.THEME_BY_TAG`.
    'leisure~"^(garden)$"',
    'natural~"^(cave_entrance|waterfall)$"',
    # `waterway=waterfall` est l'étiquette réelle des chutes d'eau : demander
    # `natural=waterfall` seul rendait cinq objets pour toute la France.
    'waterway~"^(waterfall)$"',
]


@dataclass
class OsmPlace:
    """Un site de visite tel qu'OpenStreetMap le décrit."""

    osm_id: str
    name: str
    lat: float
    lon: float
    wikidata_id: str | None = None
    opening_hours: str | None = None
    website: str | None = None
    fee: str | None = None
    wikipedia: str | None = None
    access: str | None = None
    tags: dict[str, str] = field(default_factory=dict)
    departement: str | None = None

    @property
    def closed(self) -> bool:
        """Accès explicitement refusé au public.

        C'est le seul signal négatif fiable d'OpenStreetMap. L'absence
        d'horaires n'en est pas un : la plupart des objets n'en portent pas,
        même quand le lieu se visite.
        """
        return self.access in {"private", "no"}

    @property
    def managed(self) -> bool:
        """Site manifestement ouvert au public.

        Des horaires d'ouverture, un site web ou une mention de tarif ne se
        posent que sur un lieu qui accueille des visiteurs. C'est le signal
        qu'aucune source encyclopédique ne donne.
        """
        return bool(self.opening_hours or self.website or self.fee)


def cells(bbox: tuple[float, float, float, float] = FRANCE_BBOX, size: float = CELL_DEGREES):
    """Découpe une emprise en cellules, pour rester sous le temps imparti."""
    min_lat, min_lon, max_lat, max_lon = bbox
    lat = min_lat
    while lat < max_lat:
        lon = min_lon
        while lon < max_lon:
            yield (lat, lon, min(lat + size, max_lat), min(lon + size, max_lon))
            lon += size
        lat += size


def cell_query(
    cell: tuple[float, float, float, float],
    timeout_s: int = 180,
    tags: list[str] | None = None,
    pays: str = "FR",
) -> str:
    """Requête Overpass pour une cellule.

    Seuls les objets NOMMÉS sont demandés : un site de visite sans nom n'est
    pas exploitable, et l'écarter tôt divise le volume par plusieurs. Et seuls
    ceux qui tombent en France : la cellule découpe, la zone délimite.

    `tags` restreint la requête. Vérifier une hypothèse sur les cascades ne
    demande pas de rapporter neuf cents musées : la question se juge sur trente
    lignes, pas sur mille.
    """
    box = f"{cell[0]},{cell[1]},{cell[2]},{cell[3]}"
    clauses = "\n  ".join(
        f'nwr[{tag}]["name"](area.pays)({box});' for tag in (tags or TAG_FILTERS)
    )
    return f"""[out:json][timeout:{timeout_s}];
{pays_area(pays)}
(
  {clauses}
);
out center tags;
"""


class OverpassClient:
    def __init__(self, min_interval_s: float = 3.0, timeout_s: int = 240,
                 max_retries: int = 3, pays: str = "FR") -> None:
        self.min_interval_s = min_interval_s
        self.timeout_s = timeout_s
        self.max_retries = max_retries
        self.pays = pays
        self._last_call = 0.0
        self._endpoint = 0
        # Une cellule abandonnée rend une liste vide, exactement comme une
        # cellule sans résultat. Sans ce compte, une collecte à moitié tombée
        # se lit comme une collecte complète et bredouille.
        self.abandonnees: list[tuple[float, float, float, float]] = []
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": USER_AGENT})

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_call
        if elapsed < self.min_interval_s:
            time.sleep(self.min_interval_s - elapsed)
        self._last_call = time.monotonic()

    def fetch_cell(
        self, cell: tuple[float, float, float, float], tags: list[str] | None = None
    ) -> list[OsmPlace]:
        delay = 5.0
        for attempt in range(1, self.max_retries + 1):
            self._throttle()
            endpoint = ENDPOINTS[self._endpoint % len(ENDPOINTS)]
            try:
                response = self._session.post(
                    endpoint,
                    data={"data": cell_query(cell, tags=tags, pays=self.pays)},
                    timeout=self.timeout_s
                )
            except requests.RequestException as exc:
                LOG.warning("Overpass %s : %s", endpoint, exc)
            else:
                if response.status_code == 200:
                    return parse_elements(response.json().get("elements", []))
                # 429 et 504 sont les réponses habituelles d'un service saturé :
                # on change de miroir plutôt que d'insister sur le même.
                LOG.warning("Overpass %s : HTTP %s", endpoint, response.status_code)

            self._endpoint += 1
            time.sleep(delay)
            delay *= 2

        LOG.error("Overpass : cellule %s abandonnée", cell)
        self.abandonnees.append(cell)
        return []


def parse_elements(elements: list[dict]) -> list[OsmPlace]:
    """Transforme la réponse Overpass en lieux exploitables."""
    out: list[OsmPlace] = []
    for element in elements:
        tags = element.get("tags") or {}
        name = tags.get("name")
        if not name:
            continue

        # Les nœuds portent leurs coordonnées ; chemins et relations ont un
        # centre calculé par `out center`.
        lat = element.get("lat", (element.get("center") or {}).get("lat"))
        lon = element.get("lon", (element.get("center") or {}).get("lon"))
        if lat is None or lon is None:
            continue

        out.append(
            OsmPlace(
                osm_id=f"{element.get('type')}/{element.get('id')}",
                name=name,
                lat=float(lat),
                lon=float(lon),
                wikidata_id=tags.get("wikidata"),
                opening_hours=tags.get("opening_hours"),
                website=tags.get("website") or tags.get("contact:website"),
                fee=tags.get("fee"),
                wikipedia=tags.get("wikipedia"),
                access=tags.get("access"),
                tags=tags,
            )
        )
    return out
