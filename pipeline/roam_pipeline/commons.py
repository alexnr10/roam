"""Crédit d'une photo Wikimedia Commons : auteur et licence.

Une image de Commons n'est pas libre de droits : elle est sous licence, et la
plupart des licences exigent de citer l'auteur. Le catalogue en affiche deux
mille — les publier sans crédit n'est pas une négligence de forme, c'est une
violation des conditions qui les rendent utilisables.

Wikidata donne l'adresse du fichier, jamais son crédit. Il faut le demander à
Commons, qui le range dans `extmetadata` — des champs remplis à la main par les
contributeurs, en HTML, et souvent absents. On en tire deux choses seulement,
celles qu'une fiche peut afficher sans devenir un formulaire juridique :
l'auteur et le nom court de la licence.
"""

from __future__ import annotations

import html
import logging
import re
import time
from urllib.parse import unquote

import requests

LOG = logging.getLogger(__name__)

API = "https://commons.wikimedia.org/w/api.php"
USER_AGENT = "RoamCatalogBot/0.1 (https://github.com/alexnr10/roam) python-requests"
# `prop=imageinfo` accepte cinquante titres par appel pour un client anonyme.
BATCH = 50

_BALISES = re.compile(r"<[^>]+>")
_ESPACES = re.compile(r"\s+")


def file_title(image_url: str | None) -> str | None:
    """`.../Special:FilePath/Tour%20Eiffel.jpg` → `File:Tour Eiffel.jpg`.

    L'adresse porte le nom du fichier encodé ; l'API veut le titre décodé,
    préfixé de son espace de noms. Le tiret bas y vaut l'espace — MediaWiki ne
    les distingue pas, et Wikidata écrit l'un quand le curateur écrit l'autre :
    les confondre ferait redemander le crédit d'une photo qui n'a pas changé.
    """
    if not image_url or "Special:FilePath/" not in image_url:
        return None
    nom = unquote(image_url.rsplit("Special:FilePath/", 1)[-1]).split("?", 1)[0]
    nom = nom.replace("_", " ").strip()
    return f"File:{nom}" if nom else None


def texte(valeur: str | None) -> str | None:
    """Le texte d'un champ `extmetadata`, débarrassé de son HTML.

    L'auteur y est presque toujours un lien — parfois deux, parfois une phrase
    entière avec un logo. Une fiche n'affiche pas du HTML : on garde les mots,
    tous les mots. Un crédit se cite entier ou ne se cite pas ; c'est
    l'affichage qui décide de le tronquer à l'œil, pas la collecte.
    """
    if not valeur:
        return None
    net = _ESPACES.sub(" ", html.unescape(_BALISES.sub(" ", valeur))).strip()
    return net or None


class CommonsClient:
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

    def category_files(self, category: str, limit: int = 50) -> list[str]:
        """Les fichiers d'une catégorie Commons, pour choisir autrement.

        Wikidata ne donne qu'une image par lieu, et la catégorie Commons en
        contient parfois cent. C'est là que se trouve la photo qu'on aurait
        voulue — celle prise du ciel, celle de la façade entière — et il n'y a
        aucun moyen de la connaître sans la demander.

        Seuls les fichiers, pas les sous-catégories : on cherche une photo, pas
        un plan de classement.
        """
        if not category:
            return []
        titre = category if category.startswith("Category:") else f"Category:{category}"
        self._throttle()
        response = self._session.get(
            API,
            params={
                "action": "query",
                "format": "json",
                "formatversion": "2",
                "list": "categorymembers",
                "cmtitle": titre,
                "cmtype": "file",
                "cmlimit": str(limit),
            },
            timeout=self.timeout_s,
        )
        response.raise_for_status()
        membres = response.json().get("query", {}).get("categorymembers", [])
        return [m["title"] for m in membres if m.get("title")]

    def credits(self, titles: list[str]) -> dict[str, tuple[str | None, str | None]]:
        """`{titre de fichier: (auteur, licence)}` pour un lot de cinquante.

        Un fichier qui EXISTE rend une entrée, même quand Commons n'en
        documente ni l'auteur ni la licence : « demandé, rien à dire » et
        « jamais demandé » sont deux états différents, et les confondre faisait
        redemander à chaque passe les mêmes fichiers muets — et signaler à
        chaque construction des lieux pour lesquels il n'y a rien à faire.

        Un titre absent de la réponse — fichier supprimé, renommé — n'apparaît
        pas : l'appelant sait alors qu'il ne pourra pas afficher l'image.
        """
        credits: dict[str, tuple[str | None, str | None]] = {}
        if not titles:
            return credits

        self._throttle()
        response = self._session.get(
            API,
            params={
                "action": "query",
                "format": "json",
                "formatversion": "2",
                "prop": "imageinfo",
                "iiprop": "extmetadata",
                "iiextmetadatafilter": "Artist|LicenseShortName",
                "titles": "|".join(titles),
            },
            timeout=self.timeout_s,
        )
        response.raise_for_status()
        for page in response.json().get("query", {}).get("pages", []):
            infos = page.get("imageinfo") or []
            if not infos:
                continue
            meta = infos[0].get("extmetadata") or {}
            credits[page.get("title", "")] = (
                texte((meta.get("Artist") or {}).get("value")),
                texte((meta.get("LicenseShortName") or {}).get("value")),
            )
        return credits
