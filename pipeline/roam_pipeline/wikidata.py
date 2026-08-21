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


class SparqlError(RuntimeError):
    pass


class SparqlClient:
    def __init__(
        self,
        endpoint: str = ENDPOINT,
        user_agent: str = USER_AGENT,
        min_interval_s: float = 1.5,
        timeout_s: int = 180,
        max_retries: int = 4,
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

def theme_query(class_qids: list[str], min_sitelinks: int, with_admin: bool = True) -> str:
    """Lieux français d'un thème, avec notoriété et rattachement administratif.

    Le filtre sur `wikibase:sitelinks` est appliqué tôt : c'est lui qui rend la
    requête tenable, et c'est aussi le premier filtre de qualité.
    """
    values = " ".join(f"wd:{q}" for q in class_qids)
    admin_block = (
        f"""
  OPTIONAL {{ ?item wdt:{P_INSEE_DEPT} ?directDept. }}
  OPTIONAL {{ ?item wdt:{P_ADMIN_ENTITY}+ ?deptEntity. ?deptEntity wdt:{P_INSEE_DEPT} ?parentDept. }}
  OPTIONAL {{ ?item wdt:{P_ADMIN_ENTITY}+ ?regEntity. ?regEntity wdt:{P_INSEE_REGION} ?parentRegion. }}"""
        if with_admin
        else ""
    )
    return f"""
SELECT DISTINCT ?item ?itemLabel ?coord ?sitelinks ?image ?commons ?elevation
                ?directDept ?parentDept ?parentRegion ?frwiki
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
  OPTIONAL {{ ?frwiki schema:about ?item ; schema:isPartOf <https://fr.wikipedia.org/> . }}{admin_block}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "fr,en". }}
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
    return f"""
SELECT DISTINCT ?item ?itemLabel ?coord ?sitelinks ?image WHERE {{
  ?item {predicate[kind]} wd:{qid} .
  ?item wdt:{P_COUNTRY} wd:{Q_FRANCE} .
  OPTIONAL {{ ?item wdt:{P_COORDINATE} ?coord. }}
  OPTIONAL {{ ?item wikibase:sitelinks ?sitelinks. }}
  OPTIONAL {{ ?item wdt:{P_IMAGE} ?image. }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "fr,en". }}
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
