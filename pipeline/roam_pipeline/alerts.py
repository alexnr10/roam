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
from collections import Counter, defaultdict

from .config import Config
from .models import Place


def _mots(nom: str) -> list[str]:
    """Les mots d'un nom, sans accents ni ponctuation, à partir de quatre lettres.

    Quatre, parce que « Eu » — la commune de Seine-Maritime — a déjà servi de
    sous-chaîne à la moitié de la France sur une recherche par nom. Un mot trop
    court ne distingue rien.
    """
    sans = unicodedata.normalize("NFD", nom or "").encode("ascii", "ignore").decode()
    return [m for m in re.split(r"[^a-z0-9]+", sans.lower()) if len(m) >= 4]


def _est_sa_commune(place: Place) -> bool:
    """Ce lieu EST sa commune — un village, pas un monument.

    Un lieu fermé n'est jamais remplacé par la ville qui l'entoure : l'abbaye
    Saint-Pierre de Beaulieu-sur-Dordogne ne se visite pas, et « on visite
    Beaulieu-sur-Dordogne à la place » ne répond à personne — c'est là qu'elle
    est, pas ce qu'elle est devenue.

    Écarter le nom de la commune des mots distinctifs, comme le fait la
    déduplication, ne marcherait pas ici : la commune de Lascaux IV s'appelle
    Montignac-Lascaux, et « lascaux » — le seul mot qui relie le fac-similé à
    la grotte — disparaîtrait avec elle. C'est le lieu ENTIER qui doit valoir
    sa commune, et non tel de ses mots.
    """
    def cle(nom: str) -> str:
        sans = unicodedata.normalize("NFD", nom or "").encode("ascii", "ignore").decode()
        return re.sub(r"[^a-z0-9]+", "", sans.lower())

    return bool(place.commune_name) and cle(place.name) == cle(place.commune_name)


def _metres(a: Place, b: Place) -> float:
    return math.hypot(
        (a.lat - b.lat) * 110_540,
        (a.lon - b.lon) * 111_320 * math.cos(math.radians(a.lat)),
    )


#: Au-delà de combien de noms un mot cesse d'être distinctif.
#
# « saint », « château », « grand » reviennent des centaines de fois : ils ne
# désignent personne. « lascaux » apparaît deux fois, « cosquer » trois. Le
# seuil se lit donc dans la collection elle-même plutôt que dans une liste de
# mots vides écrite à la main — ce qui vaut aussi pour un autre pays, où la
# liste serait à réécrire et le comptage, lui, marche tout seul.
_MOT_COMMUN = 5

#: Un fac-similé n'est pas sur le site : Lascaux IV est à 500 m de la grotte,
#: Cosquer Méditerranée à douze kilomètres de la calanque.
_PORTEE_M = 25_000


def remplacants(places: list[Place]) -> dict[str, Place]:
    """Pour chaque lieu FERMÉ, ce qu'on visite à sa place — quand ça existe.

    La grotte de Lascaux est au catalogue et ne se visite pas ; ce qu'on visite
    est Lascaux IV, à cinq cents mètres. Chauvet, elle, avait son fac-similé.
    Rien ne signalait la différence : un lieu fermé et un lieu fermé-mais-doublé
    se ressemblent trait pour trait dans les données.

    La règle est le MOT RARE PARTAGÉ, à moins de vingt-cinq kilomètres. Deux
    autres ont été essayées et mesurées sur les cent douze lieux fermés de la
    collecte :

    - le voisin visitable le plus proche : il propose le château d'en face et
      le menhir d'à côté, sur presque tous ;
    - le nom en préfixe : un seul résultat, Chauvet — il rate Lascaux IV, dont
      le nom ne commence pas par celui de la grotte.

    Le mot rare en trouve treize, dont les trois qui comptent. Un village ne
    peut pas être ce remplaçant : voir `_est_sa_commune`. Ce qu'il rend
    n'est pas un verdict mais une piste : « Grotte de Bruniquel → Châteaux de
    Bruniquel » est une bonne réponse pour un guide, et c'est au curateur de le
    dire.
    """
    par_mot: dict[str, list[Place]] = defaultdict(list)
    frequence: Counter[str] = Counter()
    for place in places:
        vus = set(_mots(place.name))
        frequence.update(vus)
        if place.visitable is not False and not _est_sa_commune(place):
            for mot in vus:
                par_mot[mot].append(place)

    trouves: dict[str, Place] = {}
    for place in places:
        if place.visitable is not False:
            continue
        rares = [m for m in _mots(place.name) if frequence[m] <= _MOT_COMMUN]
        candidats = {
            autre.wikidata_id: autre
            for mot in rares
            for autre in par_mot.get(mot, ())
            if autre.wikidata_id != place.wikidata_id
        }
        proches = [
            (_metres(place, autre), autre)
            for autre in candidats.values()
            if _metres(place, autre) <= _PORTEE_M
        ]
        if proches:
            trouves[place.wikidata_id] = min(proches, key=lambda x: (x[0], x[1].name))[1]
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
