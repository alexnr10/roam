"""Rattachement administratif par les coordonnées.

Wikidata ne renseigne pas systématiquement `P131` (entité administrative) —
et surtout pas sur les sites naturels. Une cascade n'a souvent que ses
coordonnées. Résultat, huit cent vingt lieux de métropole se retrouvaient sans
département, donc hors de toute collection géographique.

Le point de départ ne peut donc pas être la hiérarchie Wikidata : ce sont les
coordonnées, qui elles sont toujours présentes. L'API Adresse de l'État fait le
géocodage inverse en masse, gratuitement et sans clé, et renvoie le code INSEE
de la commune — dont le code de département se déduit exactement.
"""

from __future__ import annotations

import csv
import io
import logging
import time

import requests

LOG = logging.getLogger(__name__)

REVERSE_CSV = "https://api-adresse.data.gouv.fr/reverse/csv/"
COMMUNES = "https://geo.api.gouv.fr/communes"
USER_AGENT = "RoamCatalogBot/0.1 (https://github.com/alexnr10/roam) python-requests"
# L'API accepte de gros lots ; on reste modeste pour rester poli et pouvoir
# reprendre sans tout perdre en cas d'échec.
BATCH = 500


def departement_from_insee(citycode: str | None) -> str | None:
    """Code de département depuis un code INSEE de commune.

    Trois cas : l'outre-mer sur trois chiffres (97xxx), la Corse sur une lettre
    (2A004, 2B033), le reste sur deux chiffres.
    """
    if not citycode:
        return None
    code = citycode.strip().upper()
    if len(code) < 4:
        return None
    if code.startswith("97") or code.startswith("98"):
        return code[:3]
    if code.startswith(("2A", "2B")):
        return code[:2]
    return code[:2] if code[:2].isdigit() else None


class AddressClient:
    def __init__(self, min_interval_s: float = 1.0, timeout_s: int = 120) -> None:
        self.min_interval_s = min_interval_s
        self.timeout_s = timeout_s
        self._last_call = 0.0
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": USER_AGENT})

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_call
        if elapsed < self.min_interval_s:
            time.sleep(self.min_interval_s - elapsed)
        self._last_call = time.monotonic()

    def reverse(self, points: list[tuple[str, float, float]]) -> dict[str, str]:
        """`[(identifiant, lat, lon)]` → `{identifiant: code INSEE de commune}`."""
        if not points:
            return {}

        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["id", "latitude", "longitude"])
        for identifier, lat, lon in points:
            writer.writerow([identifier, f"{lat:.6f}", f"{lon:.6f}"])

        self._throttle()
        response = self._session.post(
            REVERSE_CSV,
            files={"data": ("points.csv", buffer.getvalue(), "text/csv")},
            timeout=self.timeout_s,
        )
        response.raise_for_status()

        out: dict[str, str] = {}
        for row in csv.DictReader(io.StringIO(response.text)):
            identifier = row.get("id")
            citycode = row.get("result_citycode")
            if identifier and citycode:
                out[identifier] = citycode
        return out


class CommuneClient:
    """Commune contenant un point, par l'API Géo.

    L'API Adresse cherche l'ADRESSE la plus proche : une cascade au fond d'une
    forêt vosgienne n'en a aucune à portée, et la requête revient vide. C'est ce
    qui laissait des centaines de sites naturels sans département alors qu'ils
    sont en pleine métropole.

    L'API Géo, elle, répond par appartenance au polygone communal. C'est la
    bonne question à poser pour un lieu qui n'est pas une adresse — au prix d'un
    appel par point, là où l'API Adresse traite un lot entier.
    """

    def __init__(self, min_interval_s: float = 0.05, timeout_s: int = 20,
                 max_retries: int = 3) -> None:
        self.min_interval_s = min_interval_s
        self.timeout_s = timeout_s
        self.max_retries = max_retries
        self._last_call = 0.0
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": USER_AGENT})

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_call
        if elapsed < self.min_interval_s:
            time.sleep(self.min_interval_s - elapsed)
        self._last_call = time.monotonic()

    def locate(self, lat: float, lon: float) -> tuple[str, str] | None:
        """`(code de département, code de région)`, ou None hors de France."""
        delay = 1.0
        for attempt in range(1, self.max_retries + 1):
            self._throttle()
            try:
                response = self._session.get(
                    COMMUNES,
                    params={
                        "lat": f"{lat:.6f}",
                        "lon": f"{lon:.6f}",
                        "fields": "codeDepartement,codeRegion",
                        "format": "json",
                    },
                    timeout=self.timeout_s,
                )
            except requests.RequestException:
                time.sleep(delay)
                delay *= 2
                continue

            if response.status_code == 429:
                time.sleep(delay)
                delay *= 2
                continue
            if response.status_code != 200:
                return None

            payload = response.json()
            if not payload:
                return None
            first = payload[0]
            dept = first.get("codeDepartement")
            return (dept, first.get("codeRegion")) if dept else None

        LOG.debug("API Géo : abandon après %s tentatives", self.max_retries)
        return None
