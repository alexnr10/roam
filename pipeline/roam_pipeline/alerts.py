"""Signaux d'alerte pour la revue éditoriale.

La charte exclut déjà ce qui a disparu et ce qui n'est pas atteignable. Encore
faut-il que le relecteur le repère : sur mille six cents lieux, ces cas se
noient. Ces signaux les font remonter — ils n'excluent rien tout seuls, parce
qu'aucun d'eux n'est concluant :

- une ruine porte une date de démolition mais se visite parfaitement ;
- un sommet à 3 800 m peut avoir un téléphérique ;
- un lieu sans photo est souvent obscur, parfois simplement mal documenté.
"""

from __future__ import annotations

import math
import re
import unicodedata

from .config import Config
from .models import Place


def _nom_nu(nom: str) -> str:
    """Le nom, sans accents ni ponctuation, pour comparer des graphies."""
    sans = unicodedata.normalize("NFD", nom or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", sans.lower()).strip()


def _metres(a: Place, b: Place) -> float:
    return math.hypot(
        (a.lat - b.lat) * 110_540,
        (a.lon - b.lon) * 111_320 * math.cos(math.radians(a.lat)),
    )


#: Longueur minimale d'un nom pour servir de préfixe.
#
# Sans elle, la commune d'« Eu » serait le préfixe de la moitié de la France.
# C'est une erreur déjà commise, sur une recherche par sous-chaîne : le
# garde-fou est écrit ici pour qu'elle ne se refasse pas.
_NOM_MINIMAL = 8

#: Un fac-similé n'est pas sur le site : Lascaux IV est à 800 m de la grotte,
#: Cosquer Méditerranée à vingt kilomètres de la calanque.
_PORTEE_M = 25_000


def remplacants(places: list[Place]) -> dict[str, Place]:
    """Pour chaque lieu FERMÉ, ce qu'on visite à sa place — quand ça existe.

    La grotte de Lascaux est au catalogue et ne se visite pas ; ce qu'on visite
    est Lascaux IV, qui n'était collecté sous aucun nom. Chauvet, elle, avait
    son fac-similé. Rien ne signalait la différence : un lieu fermé et un lieu
    fermé-mais-doublé se ressemblent trait pour trait dans les données.

    La règle est le NOM PARTAGÉ en préfixe : « grotte chauvet » ouvre sur
    « grotte chauvet 2 ardeche ». C'est étroit à dessein — le voisin visitable
    le plus proche, lui, rend n'importe quoi : sur les cent douze lieux fermés
    de la collecte, il proposait le château d'en face et le menhir d'à côté.
    """
    par_nom: list[tuple[str, Place]] = [
        (_nom_nu(p.name), p) for p in places if p.visitable is not False
    ]
    trouves: dict[str, Place] = {}
    for place in places:
        if place.visitable is not False:
            continue
        nu = _nom_nu(place.name)
        if len(nu) < _NOM_MINIMAL:
            continue
        for autre_nu, autre in par_nom:
            if autre.wikidata_id == place.wikidata_id:
                continue
            # Un préfixe SUIVI D'UNE FRONTIÈRE de mot : « grotte chauvet »
            # ouvre sur « grotte chauvet 2 », pas sur « grotte chauveterie ».
            if not autre_nu.startswith(nu) or (
                len(autre_nu) > len(nu) and autre_nu[len(nu)] != " "
            ):
                continue
            if _metres(place, autre) <= _PORTEE_M:
                trouves[place.wikidata_id] = autre
                break
    return trouves


def alerts_for(
    place: Place, config: Config, doubles: dict[str, Place] | None = None
) -> list[str]:
    """Points à vérifier avant de garder ce lieu.

    `doubles` vient de `remplacants` : il dit, pour un lieu fermé, ce qu'on
    visite à sa place. Absent, l'alerte se tait plutôt que d'accuser à tort.
    """
    found: list[str] = []

    if place.dissolved:
        year = place.dissolved[:4] if len(place.dissolved) >= 4 else place.dissolved
        found.append(f"disparu ou démoli ({year})")

    if (
        place.theme_id == "sommets"
        and place.elevation_m
        and place.elevation_m >= config.alerts.alpine_elevation_m
    ):
        found.append(f"{place.elevation_m} m — accès alpin ?")

    # Seul l'accès explicitement refusé est signalé. L'absence d'horaires ne
    # l'est pas : elle concerne 62 % des lieux rapprochés, et signalerait donc
    # la moitié du catalogue sans rien apprendre à personne.
    if place.visitable is False:
        double = (doubles or {}).get(place.wikidata_id)
        if double is not None:
            found.append(f"fermé — on visite « {double.name} » à la place")
        elif doubles is not None:
            # Le cas de Lascaux : fermé, au catalogue, et RIEN au catalogue ne
            # le remplace. Soit le fac-similé manque à la collecte, soit le
            # lieu n'a rien à faire dans un guide.
            found.append("fermé, et rien ne le remplace — fac-similé manquant ?")
        else:
            found.append("accès privé ou interdit")

    if not place.image_url and not place.commons_category:
        found.append("aucune photo")

    return found
