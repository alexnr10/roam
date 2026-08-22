"""Client SPARQL Wikidata Query Service.

WDQS impose un User-Agent identifiable et applique un throttling agressif.
Le client sérialise les requêtes, temporise entre deux appels et respecte
l'en-tête `Retry-After` quand le service le renvoie.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Iterable, Iterator

import requests

LOG = logging.getLogger(__name__)

ENDPOINT = "https://query.wikidata.org/sparql"
SEARCH_ENDPOINT = "https://www.wikidata.org/w/api.php"
USER_AGENT = "RoamCatalogBot/0.1 (https://github.com/alexnr10/roam) python-requests"

# France, et propriétés utilisées par les requêtes
Q_FRANCE = "Q142"
P_INSTANCE_OF = "P31"
P_SUBCLASS_OF = "P279"
P_COUNTRY = "P17"
P_COORDINATE = "P625"
P_ADMIN_ENTITY = "P131"
P_IMAGE = "P18"
P_HERITAGE = "P1435"
P_MEMBER_OF = "P463"
P_INSEE_DEPT = "P2586"
P_INSEE_REGION = "P2585"
P_ELEVATION = "P2044"
P_COMMONS_CATEGORY = "P373"
P_DISSOLVED = "P576"   # date de dissolution, démolition ou disparition


class SparqlError(RuntimeError):
    pass


class SparqlClient:
    def __init__(
        self,
        endpoint: str = ENDPOINT,
        user_agent: str = USER_AGENT,
        min_interval_s: float = 1.5,
        # WDQS coupe lui-même à 60 s : attendre plus longtemps n'apporte rien.
        timeout_s: int = 90,
        max_retries: int = 6,
    ) -> None:
        self.endpoint = endpoint
        self.timeout_s = timeout_s
        self.max_retries = max_retries
        self.min_interval_s = min_interval_s
        self._last_call = 0.0
        self._session = requests.Session()
        self._session.headers.update(
            {"User-Agent": user_agent, "Accept": "application/sparql-results+json"}
        )

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_call
        if elapsed < self.min_interval_s:
            time.sleep(self.min_interval_s - elapsed)
        self._last_call = time.monotonic()

    def query(self, sparql: str) -> list[dict[str, Any]]:
        """Exécute une requête et renvoie les bindings aplatis."""
        delay = 2.0
        last_error: Exception | None = None

        for attempt in range(1, self.max_retries + 1):
            self._throttle()
            try:
                resp = self._session.post(
                    self.endpoint, data={"query": sparql}, timeout=self.timeout_s
                )
            except requests.RequestException as exc:  # réseau, DNS, timeout
                last_error = exc
                LOG.warning("tentative %s/%s échouée : %s", attempt, self.max_retries, exc)
            else:
                if resp.status_code == 200:
                    return _flatten(resp.json())
                if resp.status_code in (429, 503):
                    wait = float(resp.headers.get("Retry-After", delay))
                    LOG.warning("WDQS %s, attente de %.0fs", resp.status_code, wait)
                    time.sleep(wait)
                    delay *= 2
                    continue
                last_error = SparqlError(f"HTTP {resp.status_code} : {resp.text[:400]}")
                LOG.warning("tentative %s/%s : %s", attempt, self.max_retries, last_error)

            time.sleep(delay)
            delay *= 2

        raise SparqlError(f"échec après {self.max_retries} tentatives") from last_error


    def search(self, term: str, limit: int = 6) -> list[dict[str, str]]:
        """Recherche d'entités par libellé (wbsearchentities).

        Sert à trouver un Q-id à partir d'un mot plutôt que de l'écrire de
        mémoire — c'est ainsi qu'on évite de reproduire une erreur d'identifiant,
        qui ne lève aucune exception et fait juste rater un thème en silence.
        """
        self._throttle()
        response = self._session.get(
            SEARCH_ENDPOINT,
            params={
                "action": "wbsearchentities",
                "search": term,
                "language": "fr",
                "uselang": "fr",
                "type": "item",
                "limit": limit,
                "format": "json",
            },
            timeout=self.timeout_s,
        )
        response.raise_for_status()
        return [
            {
                "id": hit.get("id", ""),
                "label": hit.get("label", ""),
                "description": hit.get("description", ""),
            }
            for hit in response.json().get("search", [])
        ]


def _flatten(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for binding in payload.get("results", {}).get("bindings", []):
        rows.append({key: value.get("value") for key, value in binding.items()})
    return rows


def qid_from_uri(uri: str | None) -> str | None:
    """`http://www.wikidata.org/entity/Q243` → `Q243`."""
    if not uri:
        return None
    return uri.rsplit("/", 1)[-1] or None


def parse_point(wkt: str | None) -> tuple[float, float] | None:
    """`Point(2.2945 48.8584)` → `(48.8584, 2.2945)` (lat, lon)."""
    if not wkt or not wkt.upper().startswith("POINT"):
        return None
    inner = wkt[wkt.index("(") + 1 : wkt.index(")")]
    parts = inner.split()
    if len(parts) != 2:
        return None
    try:
        lon, lat = float(parts[0]), float(parts[1])
    except ValueError:
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    return lat, lon


def chunked(items: Iterable[Any], size: int) -> Iterator[list[Any]]:
    batch: list[Any] = []
    for item in items:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


# ---------------------------------------------------------------------------
# Requêtes
# ---------------------------------------------------------------------------

def theme_query(
    class_qids: list[str],
    min_sitelinks: int,
    limit: int | None = None,
    offset: int = 0,
) -> str:
    """Lieux français d'un thème, avec notoriété et commune de rattachement.

    Le filtre sur `wikibase:sitelinks` est appliqué tôt : c'est lui qui rend la
    requête tenable, et c'est aussi le premier filtre de qualité.

    La remontée département / région se faisait ici, par un chemin transitif
    `P131+/P2586`. C'était la cause des délais dépassés sur les classes
    volumineuses (châteaux, abbayes, cathédrales). On ne récupère plus que la
    commune, en lien direct, et la hiérarchie est résolue ensuite par
    `admin_codes_query` sur l'ensemble borné des communes rencontrées.
    """
    values = " ".join(f"wd:{q}" for q in class_qids)
    page = f"\nORDER BY ?item\nLIMIT {limit} OFFSET {offset}" if limit else ""
    return f"""
SELECT DISTINCT ?item ?itemLabel ?coord ?sitelinks ?image ?commons ?elevation ?admin ?frwiki
WHERE {{
  VALUES ?class {{ {values} }}
  ?item wdt:{P_INSTANCE_OF}/wdt:{P_SUBCLASS_OF}* ?class .
  ?item wdt:{P_COUNTRY} wd:{Q_FRANCE} .
  ?item wdt:{P_COORDINATE} ?coord .
  ?item wikibase:sitelinks ?sitelinks .
  FILTER(?sitelinks >= {min_sitelinks})
  OPTIONAL {{ ?item wdt:{P_IMAGE} ?image. }}
  OPTIONAL {{ ?item wdt:{P_COMMONS_CATEGORY} ?commons. }}
  OPTIONAL {{ ?item wdt:{P_ELEVATION} ?elevation. }}
  OPTIONAL {{ ?item wdt:{P_ADMIN_ENTITY} ?admin. }}
  OPTIONAL {{ ?frwiki schema:about ?item ; schema:isPartOf <https://fr.wikipedia.org/> . }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "fr,en". }}
}}{page}
"""


def admin_codes_query(admin_qids: list[str]) -> str:
    """Codes INSEE de département et de région pour des entités administratives.

    Bornée par `VALUES`, donc rapide, là où le même chemin transitif appliqué à
    tous les lieux d'une classe faisait dépasser le délai.
    """
    values = " ".join(f"wd:{q}" for q in admin_qids)
    return f"""
SELECT ?admin ?deptCode ?regionCode WHERE {{
  VALUES ?admin {{ {values} }}
  OPTIONAL {{ ?admin wdt:{P_ADMIN_ENTITY}*/wdt:{P_INSEE_DEPT} ?deptCode. }}
  OPTIONAL {{ ?admin wdt:{P_ADMIN_ENTITY}*/wdt:{P_INSEE_REGION} ?regionCode. }}
}}
"""


def items_query(qids: list[str]) -> str:
    """Mêmes attributs que `theme_query`, pour une liste d'entités connues.

    Utilisé par les thèmes alimentés par des labels plutôt que par une classe :
    les listes officielles sont déjà une curation humaine, finie et fiable.
    """
    values = " ".join(f"wd:{q}" for q in qids)
    return f"""
SELECT DISTINCT ?item ?itemLabel ?coord ?sitelinks ?image ?commons ?elevation ?admin ?frwiki
WHERE {{
  VALUES ?item {{ {values} }}
  ?item wdt:{P_COORDINATE} ?coord .
  ?item wikibase:sitelinks ?sitelinks .
  OPTIONAL {{ ?item wdt:{P_IMAGE} ?image. }}
  OPTIONAL {{ ?item wdt:{P_COMMONS_CATEGORY} ?commons. }}
  OPTIONAL {{ ?item wdt:{P_ELEVATION} ?elevation. }}
  OPTIONAL {{ ?item wdt:{P_ADMIN_ENTITY} ?admin. }}
  OPTIONAL {{ ?frwiki schema:about ?item ; schema:isPartOf <https://fr.wikipedia.org/> . }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "fr,en". }}
}}
"""


def entity_flags_query(qids: list[str]) -> str:
    """Signaux d'alerte pour des lieux déjà collectés.

    `P576` marque ce qui a été démoli ou a disparu ; l'altitude sert à repérer
    les sommets qu'on n'atteint pas en marchant. Ni l'un ni l'autre n'exclut
    automatiquement — un château en ruine se visite très bien, un sommet de
    3 800 m peut avoir un téléphérique. Ce sont des signaux pour le relecteur.
    """
    values = " ".join(f"wd:{q}" for q in qids)
    return f"""
SELECT ?item ?dissolved ?elevation WHERE {{
  VALUES ?item {{ {values} }}
  OPTIONAL {{ ?item wdt:{P_DISSOLVED} ?dissolved. }}
  OPTIONAL {{ ?item wdt:{P_ELEVATION} ?elevation. }}
}}
"""


def label_members_query(kind: str, qid: str) -> str:
    """Membres d'un label. `kind` ∈ {heritage, member_of, instance}."""
    predicate = {
        "heritage": f"wdt:{P_HERITAGE}",
        "member_of": f"wdt:{P_MEMBER_OF}",
        "instance": f"wdt:{P_INSTANCE_OF}/wdt:{P_SUBCLASS_OF}*",
    }
    if kind not in predicate:
        raise ValueError(f"type de requête de label non géré : {kind}")
    # Seul l'identifiant est exploité : demander les libellés et les coordonnées
    # multipliait le volume par dix, jusqu'à tronquer la réponse sur les gros
    # labels (30 000 monuments historiques inscrits).
    return f"""
SELECT DISTINCT ?item WHERE {{
  ?item {predicate[kind]} wd:{qid} .
  ?item wdt:{P_COUNTRY} wd:{Q_FRANCE} .
}}
"""


def entity_labels_query(qids: list[str]) -> str:
    """Libellé et description de Q-ids — sert à vérifier la configuration."""
    values = " ".join(f"wd:{q}" for q in qids)
    return f"""
SELECT ?item ?itemLabel ?itemDescription WHERE {{
  VALUES ?item {{ {values} }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "fr,en". }}
}}
"""
