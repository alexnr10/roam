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
from datetime import date, timedelta
from urllib.parse import quote, unquote

import requests

LOG = logging.getLogger(__name__)

API = "https://fr.wikipedia.org/w/api.php"
# Les consultations d'articles, servies par l'API REST de la Wikimedia
# Foundation. Libre, sans clé, sans quota déclaré pour un usage raisonnable.
PAGEVIEWS = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article"
USER_AGENT = "RoamCatalogBot/0.1 (https://github.com/alexnr10/roam) python-requests"
# L'API MediaWiki accepte cinquante titres par appel pour les clients anonymes.
BATCH = 50
# `prop=extracts` est plus coûteux et plafonné à vingt titres par requête.
EXTRACT_BATCH = 20


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

    def pageviews(self, title: str, months: int = 12) -> int | None:
        """Consultations mensuelles TYPIQUES de l'article, ou `None`.

        La médiane des douze derniers mois complets, pas la moyenne : un lieu
        qui passe au journal télévisé, ou qu'un incendie met à la une, gagne un
        pic qui écraserait tout. La médiane décrit le mois ordinaire, qui est
        ce qu'on veut mesurer — l'intérêt durable, pas l'actualité.

        `agent=user` exclut les robots et les moissonneurs, qui représentent une
        part considérable du trafic et ne disent rien de l'intérêt du public.

        `None` signifie « pas de données » et ne vaudra RIEN au score : ni
        bonus, ni malus. Même règle que la fréquentation et que l'accueil du
        public, et pour la même raison.
        """
        fin = date.today().replace(day=1) - timedelta(days=1)
        debut = (fin.replace(day=1) - timedelta(days=1)).replace(day=1)
        for _ in range(months - 1):
            debut = (debut - timedelta(days=1)).replace(day=1)

        url = (f"{PAGEVIEWS}/fr.wikipedia/all-access/user/{quote(title.replace(' ', '_'), safe='')}"
               f"/monthly/{debut:%Y%m%d}/{fin:%Y%m%d}")
        self._throttle()
        response = self._session.get(url, timeout=self.timeout_s)
        if response.status_code == 404:
            # L'article existe peut-être, mais aucune consultation n'est
            # enregistrée sur la période. Ce n'est pas zéro, c'est inconnu.
            return None
        response.raise_for_status()
        counts = sorted(item["views"] for item in response.json().get("items", []))
        if not counts:
            return None
        milieu = len(counts) // 2
        if len(counts) % 2:
            return counts[milieu]
        return (counts[milieu - 1] + counts[milieu]) // 2

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

    def intros(self, titles: list[str], sentences: int = 2) -> dict[str, str]:
        """Deux premières phrases de l'article, en texte brut.

        Sert de description dans l'application. Le contenu vient de Wikipédia,
        sous licence CC BY-SA : l'écran du lieu doit citer la source et pointer
        vers l'article, ce que fait déjà la fiche.
        """
        summaries: dict[str, str] = {}
        if not titles:
            return summaries

        self._throttle()
        response = self._session.get(
            API,
            params={
                "action": "query",
                "format": "json",
                "formatversion": "2",
                "prop": "extracts",
                "exintro": "1",
                "explaintext": "1",
                "exsentences": str(sentences),
                "titles": "|".join(titles),
                "redirects": "1",
            },
            timeout=self.timeout_s,
        )
        response.raise_for_status()
        payload = response.json().get("query", {})

        alias: dict[str, str] = {}
        for entry in payload.get("normalized", []):
            alias[entry["from"]] = entry["to"]
        for entry in payload.get("redirects", []):
            alias[entry["from"]] = entry["to"]

        by_title = {
            page["title"]: (page.get("extract") or "").strip()
            for page in payload.get("pages", [])
            if not page.get("missing")
        }

        for title in titles:
            resolved = title
            for _ in range(3):
                resolved = alias.get(resolved, resolved)
            text = by_title.get(resolved)
            if text:
                summaries[title] = text
        return summaries
