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

    def raw_metadata(self, title: str) -> tuple[str | None, dict[str, str]]:
        """Tout ce que Commons documente sur UN fichier, sans filtre ni tri.

        Un outil de diagnostic, pas une source. `credits` ne demande que deux
        champs — `Artist` et `LicenseShortName` — parce que ce sont les deux
        qu'une fiche affiche. Quand un crédit n'arrive pas, la question est
        justement de savoir si le fichier existe, sous quel titre Commons le
        connaît, et quels champs il porte VRAIMENT : un fichier importé depuis
        Flickr ou versé par une institution range parfois son auteur ailleurs.

        Renvoie le titre tel que Commons le nomme (`None` si le fichier
        n'existe pas) et la table complète de ses métadonnées.
        """
        self._throttle()
        response = self._session.get(
            API,
            params={
                "action": "query",
                "format": "json",
                "formatversion": "2",
                "prop": "imageinfo",
                "iiprop": "extmetadata",
                "titles": title,
                "redirects": "1",
            },
            timeout=self.timeout_s,
        )
        response.raise_for_status()
        pages = response.json().get("query", {}).get("pages", [])
        if not pages or pages[0].get("missing"):
            return None, {}
        page = pages[0]
        infos = page.get("imageinfo") or []
        meta = (infos[0].get("extmetadata") or {}) if infos else {}
        return page.get("title"), {
            clef: texte(valeur.get("value")) or ""
            for clef, valeur in meta.items()
            if isinstance(valeur, dict)
        }

    def credits(
        self, titles: list[str]
    ) -> dict[str, tuple[str | None, str | None] | None]:
        """`{titre de fichier: (auteur, licence)}` pour un lot de cinquante.

        Un fichier qui EXISTE rend une entrée, même quand Commons n'en
        documente ni l'auteur ni la licence : « demandé, rien à dire » et
        « jamais demandé » sont deux états différents, et les confondre faisait
        redemander à chaque passe les mêmes fichiers muets — et signaler à
        chaque construction des lieux pour lesquels il n'y a rien à faire.

        Un fichier que Commons dit INEXISTANT rend `None`, et c'est une
        troisième information, distincte des deux autres : elle permet de
        réparer un lieu dont l'image pointe dans le vide. Un titre absent du
        résultat n'est pas la même chose — c'est le lot entier qui a échoué, et
        il ne faut alors rien conclure ni rien effacer.

        Le résultat est indexé par le titre DEMANDÉ, jamais par celui que
        MediaWiki renvoie. Il normalise les siens — tiret bas, accents composés,
        redirections — et rendre le titre normalisé faisait manquer le crédit à
        celui qui l'avait demandé : la villa Savoye et la pagode Khánh-Anh
        étaient publiées sans attribution, redemandées à chaque passe et
        signalées à chaque construction, sans que rien ne puisse aboutir.
        """
        credits: dict[str, tuple[str | None, str | None] | None] = {}
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
                # Un fichier renommé garde une redirection : la suivre évite de
                # perdre le crédit d'une photo qui n'a fait que changer de nom.
                "redirects": "1",
            },
            timeout=self.timeout_s,
        )
        response.raise_for_status()
        payload = response.json().get("query", {})

        # MediaWiki normalise et suit les redirections : il faut refaire le
        # chemin en sens inverse pour rendre chaque crédit à son titre d'origine.
        alias: dict[str, str] = {}
        for entry in payload.get("normalized", []):
            alias[entry["from"]] = entry["to"]
        for entry in payload.get("redirects", []):
            alias[entry["from"]] = entry["to"]

        par_titre: dict[str, tuple[str | None, str | None] | None] = {}
        for page in payload.get("pages", []):
            if page.get("missing"):
                par_titre[page.get("title", "")] = None
                continue
            infos = page.get("imageinfo") or []
            if not infos:
                continue
            meta = infos[0].get("extmetadata") or {}
            par_titre[page.get("title", "")] = (
                texte((meta.get("Artist") or {}).get("value")),
                texte((meta.get("LicenseShortName") or {}).get("value")),
            )

        for title in titles:
            resolved = title
            for _ in range(3):  # normalisation puis redirection, au plus
                resolved = alias.get(resolved, resolved)
            if resolved in par_titre:
                credits[title] = par_titre[resolved]
        return credits
