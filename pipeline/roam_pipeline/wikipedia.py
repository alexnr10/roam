"""Enrichissement depuis l'API MediaWiki francophone.

Le nombre de versions linguistiques est un bon signal — sauf pour les sites
naturels. Les cascades, gorges et plages n'ont presque jamais d'article hors du
français : leur notoriété est donc plate, et le classement à l'intérieur de ces
thèmes devient quasi arbitraire.

La **taille de l'article francophone** rattrape exactement ce cas. Une cascade
documentée sur 20 000 caractères n'est pas la même chose qu'une ébauche de trois
lignes, et cette différence est invisible depuis le seul décompte de langues.
"""

from __future__ import annotations

import logging
import time
from urllib.parse import unquote

import requests

LOG = logging.getLogger(__name__)

API = "https://fr.wikipedia.org/w/api.php"
USER_AGENT = "RoamCatalogBot/0.1 (https://github.com/alexnr10/roam) python-requests"
# L'API MediaWiki accepte cinquante titres par appel pour les clients anonymes.
BATCH = 50


def title_from_url(url: str | None) -> str | None:
    """`https://fr.wikipedia.org/wiki/Ch%C3%A2teau_de_Chambord` → `Château de Chambord`."""
    if not url or "/wiki/" not in url:
        return None
    slug = url.rsplit("/wiki/", 1)[-1]
    if not slug:
        return None
    return unquote(slug).replace("_", " ")


class WikipediaClient:
    def __init__(self, min_interval_s: float = 0.4, timeout_s: int = 30) -> None:
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

    def article_sizes(self, titles: list[str]) -> dict[str, int]:
        """Taille en octets de chaque article, indexée par le titre demandé."""
        sizes: dict[str, int] = {}
        if not titles:
            return sizes

        self._throttle()
        response = self._session.get(
            API,
            params={
                "action": "query",
                "format": "json",
                "formatversion": "2",
                "prop": "info",
                "titles": "|".join(titles),
                "redirects": "1",
            },
            timeout=self.timeout_s,
        )
        response.raise_for_status()
        payload = response.json().get("query", {})

        # MediaWiki normalise et suit les redirections : il faut refaire le
        # chemin en sens inverse pour rendre chaque taille à son titre d'origine.
        alias: dict[str, str] = {}
        for entry in payload.get("normalized", []):
            alias[entry["from"]] = entry["to"]
        for entry in payload.get("redirects", []):
            alias[entry["from"]] = entry["to"]

        by_title = {
            page["title"]: int(page.get("length", 0))
            for page in payload.get("pages", [])
            if not page.get("missing")
        }

        for title in titles:
            resolved = title
            for _ in range(3):  # normalisation puis redirection, au plus
                resolved = alias.get(resolved, resolved)
            if resolved in by_title:
                sizes[title] = by_title[resolved]
        return sizes
