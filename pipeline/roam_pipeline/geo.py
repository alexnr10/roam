"""Référentiel géographique : le deuxième échelon et le premier, par pays.

Le champ `de_form` porte la forme complète du complément de nom
(« du Cantal », « de la Manche », « des Landes », « de l'Ain »). Le français ne
permet pas de la dériver d'une règle simple, donc elle est stockée telle quelle :
c'est ce qui donne « Châteaux du Cantal » et non « Châteaux de Cantal ». La même
raison vaut d'un pays à l'autre — « des Pouilles » ne se dérive pas de
« Puglia ».

Les noms sont FRANÇAIS, y compris pour les provinces italiennes : le catalogue
est écrit en français, et une collection s'appelle « Châteaux de Toscane ». Le
jour où l'application proposera d'autres langues, ce sont ces tables qui auront
leur équivalent, pas la mécanique qui les lit.

Un pays par exécution : le pipeline charge une configuration, donc un pays, et
`utiliser_pays()` dit lequel avant que quoi que ce soit ne lise une table.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "reference"

#: Le pays dont on lit le référentiel. La France est à la racine — elle est le
#: pays d'origine du dépôt et ses fichiers y sont versionnés depuis le début ;
#: les autres ont leur sous-dossier, comme les contours de `geo/<code>/`.
_PAYS = "FR"


def utiliser_pays(code: str) -> None:
    """Choisit le référentiel à lire. Appelé une fois, au démarrage.

    Les tables sont mises en cache : en changer en cours de route rendrait des
    départements français et des provinces italiennes selon l'ordre des appels.
    Le cache est donc vidé ici, et nulle part ailleurs.
    """
    global _PAYS
    if code.upper() == _PAYS:
        return
    _PAYS = code.upper()
    regions.cache_clear()
    departements.cache_clear()


def _dossier() -> Path:
    """Le dossier du référentiel courant."""
    return DATA_DIR if _PAYS == "FR" else DATA_DIR / _PAYS.lower()


@dataclass(frozen=True)
class Area:
    code: str
    name: str
    de_form: str
    level: str
    parent_code: str | None = None

    @property
    def id(self) -> str:
        return f"{self.level}:{self.code}"


@lru_cache(maxsize=None)
def regions() -> dict[str, Area]:
    out: dict[str, Area] = {}
    with (_dossier() / "regions.csv").open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            out[row["code"]] = Area(
                code=row["code"], name=row["name"], de_form=row["de_form"], level="region"
            )
    return out


@lru_cache(maxsize=None)
def departements() -> dict[str, Area]:
    out: dict[str, Area] = {}
    with (_dossier() / "departements.csv").open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            out[row["code"]] = Area(
                code=row["code"],
                name=row["name"],
                de_form=row["de_form"],
                level="departement",
                parent_code=row["region_code"],
            )
    return out


# Le pays du catalogue, sous la forme d'une zone comme les autres.
#
# Il vient de `scoring.yaml` : c'est la même donnée que le Q-id des requêtes, et
# deux sources pour un seul pays finiraient par diverger.
def country_area(config) -> Area:
    return Area(
        code=config.country.code, name=config.country.name,
        de_form=config.country.de_form, level="country",
    )


#: Le pays par défaut, pour les appels qui n'ont pas de configuration sous la
#: main. Tout ce qui EXPORTE doit passer par `country_area`.
FRANCE = Area(code="FR", name="France", de_form="de France", level="country")


def area(level: str, code: str) -> Area | None:
    if level == "country":
        # Le nom et le complément du pays vivent dans la configuration, pas
        # ici : `country_area(config)` est le seul chemin juste. Rendre la
        # France par défaut a un sens tant qu'il n'y a qu'elle ; en Italie, ce
        # serait intituler une collection « Le meilleur de France » sur des
        # lieux italiens — une faute qui ne plante pas et qu'on lirait dans
        # l'application.
        return FRANCE if _PAYS == "FR" else None
    if level == "region":
        return regions().get(code)
    if level == "departement":
        return departements().get(code)
    return None


def region_of(departement_code: str) -> Area | None:
    dept = departements().get(departement_code)
    if dept is None or dept.parent_code is None:
        return None
    return regions().get(dept.parent_code)


def departement_du_code_communal(code: str | None) -> str | None:
    """Le département que PRÉFIXE un code de commune, quel que soit le pays.

    `departement_from_insee` connaît la France et elle seule : deux chiffres,
    trois pour l'outre-mer, une lettre pour la Corse. Les codes ISTAT en font
    trois pour la province et six pour la commune, si bien qu'`align_departements`
    — « c'est la commune qui gagne » — ne gagnait rien du tout hors de France.

    Mesuré sur le premier catalogue italien : un seul lieu s'en trouvait mal,
    mais spectaculairement. La péninsule italienne portait la commune 066018,
    dans la province de L'Aquila, ET le département 099, Rimini. Rien ne
    tranchait, parce que rien ne savait lire un code italien.

    On cherche donc le plus LONG préfixe qui soit un département connu. La
    règle retrouve les trois cas français d'elle-même : 97411 → 974 avant 97,
    2A004 → 2A, 75056 → 75.
    """
    if not code:
        return None
    code = code.strip().upper()
    connus = departements()
    for taille in range(min(len(code) - 1, 5), 0, -1):
        if code[:taille] in connus:
            return code[:taille]
    return None


def normalize_dept_code(raw: str | None) -> str | None:
    """Normalise un code INSEE de département venant de Wikidata ('1' → '01')."""
    if not raw:
        return None
    code = raw.strip().upper()
    if code in departements():
        return code
    if code.isdigit():
        padded = code.zfill(2)
        if padded in departements():
            return padded
        if code in departements():
            return code
    return None
