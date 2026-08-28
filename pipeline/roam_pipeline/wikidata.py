"""Client SPARQL Wikidata Query Service.

WDQS impose un User-Agent identifiable et applique un throttling agressif.
Le client sérialise les requêtes, temporise entre deux appels et respecte
l'en-tête `Retry-After` quand le service le renvoie.
"""

from __future__ import annotations

import json
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
                    # `strict=False` : un libellé Wikidata peut contenir un
                    # caractère de contrôle brut, que le décodeur JSON refuse
                    # par défaut. Un lot entier de classes mourait pour un seul
                    # caractère, à la ligne 22 478 d'une réponse.
                    return _flatten(json.loads(resp.text, strict=False))
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


    def search(self, term: str, limit: int = 6, kind: str = "item") -> list[dict[str, str]]:
        """Recherche d'entités par libellé (wbsearchentities).

        `kind` vaut « item » (Q-ids) ou « property » (P-ids). Une propriété
        écrite de mémoire est aussi silencieuse qu'un Q-id faux : elle ne lève
        rien et ne rend rien.

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
                "type": kind,
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
    exclude_classes: list[str] | None = None,
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
    # `MINUS` ferme la ROUTE sans écarter le lieu du catalogue : il reste
    # disponible pour un thème déclaré plus loin. Un palais-musée cesse d'être
    # une maison d'artiste et redevient un musée.
    refused = ""
    if exclude_classes:
        bad = " ".join(f"wd:{q}" for q in exclude_classes)
        refused = (f"\n  MINUS {{ VALUES ?refuse {{ {bad} }} "
                   f"?item wdt:{P_INSTANCE_OF}/wdt:{P_SUBCLASS_OF}* ?refuse . }}")
    return f"""
SELECT DISTINCT ?item ?itemLabel ?coord ?sitelinks ?image ?commons ?elevation ?admin ?frwiki
WHERE {{
  VALUES ?class {{ {values} }}
  ?item wdt:{P_INSTANCE_OF}/wdt:{P_SUBCLASS_OF}* ?class .
  ?item wdt:{P_COUNTRY} wd:{Q_FRANCE} .
  ?item wdt:{P_COORDINATE} ?coord .
  ?item wikibase:sitelinks ?sitelinks .
  FILTER(?sitelinks >= {min_sitelinks}){refused}
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


def class_ancestry_query(item_qids: list[str], class_qids: list[str]) -> str:
    """Parmi ces lieux, lesquels descendent de l'une de ces classes ?

    Requête BORNÉE par `VALUES`, sur le même modèle que `admin_codes_query` :
    c'est ce qui la rend rapide. Poser le filtre dans `theme_query` aurait
    ajouté un chemin transitif de plus aux classes les plus volumineuses —
    exactement ce qui faisait dépasser le délai avant qu'on ne sorte la
    remontée administrative de cette requête.

    L'autre bénéfice est éditorial : l'exclusion se rejoue à `enrich`, en
    quelques secondes, sans repasser une demi-heure sur Wikidata à chaque fois
    qu'une classe s'ajoute à la liste.
    """
    items = " ".join(f"wd:{q}" for q in item_qids)
    classes = " ".join(f"wd:{q}" for q in class_qids)
    return f"""
SELECT DISTINCT ?item ?class ?classLabel WHERE {{
  VALUES ?item {{ {items} }}
  VALUES ?class {{ {classes} }}
  ?item wdt:{P_INSTANCE_OF}/wdt:{P_SUBCLASS_OF}* ?class .
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "fr,en". }}
}}
"""


#: Le corps commun du recensement : ce qui est en France, situé, et documenté.
def _notable_body(min_sitelinks: int) -> str:
    return f"""  ?item wdt:{P_COUNTRY} wd:{Q_FRANCE} .
  ?item wdt:{P_COORDINATE} ?coord .
  ?item wikibase:sitelinks ?sitelinks .
  FILTER(?sitelinks >= {min_sitelinks})"""


def class_census_query(min_sitelinks: int, limit: int = 300) -> str:
    """Combien de lieux français notoires par CLASSE déclarée.

    Première moitié du recensement des trous. L'agrégation se fait chez WDQS :
    la version paginée de cette requête devait trier des dizaines de milliers
    de lignes à chaque page, et mourait en 504 après six tentatives.

    `wdt:P31` sans `P279*` : on veut la classe réellement DÉCLARÉE, celle qu'il
    faudra écrire dans `themes.yaml`, pas toute son ascendance.
    """
    return f"""
SELECT ?class (COUNT(DISTINCT ?item) AS ?n) WHERE {{
{_notable_body(min_sitelinks)}
  ?item wdt:{P_INSTANCE_OF} ?class .
}}
GROUP BY ?class
ORDER BY DESC(?n)
LIMIT {limit}
"""


def class_members_query(class_qids: list[str], min_sitelinks: int) -> str:
    """Les lieux notoires de ces classes, pour en soustraire ce qu'on possède.

    Seconde moitié. Bornée par `VALUES` : c'est la classe qui mène la requête,
    et non l'ensemble des lieux de France, d'où un coût sans rapport.
    """
    values = " ".join(f"wd:{q}" for q in class_qids)
    return f"""
SELECT ?class ?item ?itemLabel WHERE {{
  VALUES ?class {{ {values} }}
  ?item wdt:{P_INSTANCE_OF} ?class .
{_notable_body(min_sitelinks)}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "fr,en". }}
}}
"""


def class_thresholds_query(class_qid: str, thresholds: list[int]) -> str:
    """Combien de lieux d'une classe survivent à chaque plancher de collecte.

    Répond à « si je descends le plancher à quatre, combien de lieux en plus ? »
    sans relancer une demi-heure de collecte pour le savoir.
    """
    lines = "\n".join(
        f"  (SUM(IF(?sitelinks >= {t}, 1, 0)) AS ?n{t})" for t in thresholds
    )
    return f"""
SELECT
{lines}
WHERE {{
  ?item wdt:{P_INSTANCE_OF} wd:{class_qid} .
  ?item wdt:{P_COUNTRY} wd:{Q_FRANCE} .
  ?item wdt:{P_COORDINATE} ?coord .
  ?item wikibase:sitelinks ?sitelinks .
}}
"""


def probe_query(qids: list[str]) -> str:
    """Tout ce qui décide du sort d'une entité, sans aucun filtre.

    L'inverse exact de `theme_query` : celle-ci n'exige rien — ni pays, ni
    coordonnées, ni notoriété — et rapporte justement ce qui manque. C'est ce
    qui permet de répondre à « pourquoi ce lieu emblématique n'est-il nulle
    part ? », question à laquelle `explain` ne peut pas répondre puisqu'il ne
    connaît que ce qui a déjà été collecté.
    """
    values = " ".join(f"wd:{q}" for q in qids)
    return f"""
SELECT ?item ?itemLabel ?itemDescription ?country ?countryLabel ?coord
       ?sitelinks ?frwiki ?class ?classLabel ?adminLabel
WHERE {{
  VALUES ?item {{ {values} }}
  OPTIONAL {{ ?item wdt:{P_COUNTRY} ?country. }}
  OPTIONAL {{ ?item wdt:{P_COORDINATE} ?coord. }}
  OPTIONAL {{ ?item wikibase:sitelinks ?sitelinks. }}
  OPTIONAL {{ ?item wdt:{P_INSTANCE_OF} ?class. }}
  OPTIONAL {{ ?item wdt:{P_ADMIN_ENTITY} ?admin. }}
  OPTIONAL {{ ?frwiki schema:about ?item ; schema:isPartOf <https://fr.wikipedia.org/> . }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "fr,en". }}
}}
"""


def visitors_query(qids: list[str], property_id: str) -> str:
    """Fréquentation annuelle de lieux déjà collectés.

    Bornée par `VALUES`, comme les autres requêtes d'enrichissement : elle se
    rejoue en quelques secondes, sans repasser par la collecte.

    Un lieu peut porter plusieurs chiffres — un par année mesurée. On les
    ramène tous et l'appelant garde le plus élevé : une fréquentation record
    dit mieux ce que vaut le lieu qu'une année de travaux.
    """
    values = " ".join(f"wd:{q}" for q in qids)
    return f"""
SELECT ?item ?visitors WHERE {{
  VALUES ?item {{ {values} }}
  ?item wdt:{property_id} ?visitors .
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
