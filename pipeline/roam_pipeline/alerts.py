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

from .config import Config
from .models import Place


def alerts_for(place: Place, config: Config) -> list[str]:
    """Points à vérifier avant de garder ce lieu."""
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
        found.append("accès privé ou interdit")

    if not place.image_url and not place.commons_category:
        found.append("aucune photo")

    return found
