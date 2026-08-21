"""Calcul du score et attribution des niveaux.

Rappel : le score CLASSE, il ne DÉCIDE pas. Rien n'est publié sans validation
humaine (cf. docs/curation-charter.md).
"""

from __future__ import annotations

import math

from .config import Config, Scoring, Tiers
from .models import Place


def label_bonus(place_labels: list[str], config: Config) -> float:
    """Bonus de label, empilement limité.

    Seul le bonus le plus élevé s'applique pleinement, plus la moitié du
    deuxième : sans ça, un empilement de petits labels dépasserait un site
    UNESCO, ce qui n'a aucun sens.
    """
    bonuses = sorted(
        (config.label(lid).score_bonus for lid in place_labels if _known(lid, config)),
        reverse=True,
    )
    if not bonuses:
        return 0.0
    if config.scoring.label_stacking == "half_second" and len(bonuses) > 1:
        return bonuses[0] + bonuses[1] / 2
    return bonuses[0]


def _known(label_id: str, config: Config) -> bool:
    try:
        config.label(label_id)
    except KeyError:
        return False
    return True


def compute_score(place: Place, config: Config) -> float:
    s: Scoring = config.scoring

    # log1p : le passage de 2 à 6 langues est bien plus significatif que de 40 à 44.
    notoriety = s.sitelinks_weight * math.log1p(max(place.sitelinks, 0))

    score = notoriety + label_bonus(place.labels, config)
    if place.image_url or place.commons_category:
        score += s.has_image_bonus
    if place.has_frwiki:
        score += s.has_frwiki_bonus
    return round(score, 3)


def score_all(places: list[Place], config: Config) -> list[Place]:
    for place in places:
        place.score = compute_score(place, config)
        place.inclusion_criteria = derive_criteria(place, config)
    return places


def derive_criteria(place: Place, config: Config) -> list[str]:
    """Critères de la charte satisfaits par le lieu (C1..C5)."""
    criteria: list[str] = []
    if any(_known(lid, config) and config.label(lid).makes_collection for lid in place.labels):
        criteria.append("C1")
    if any(lid.startswith("monument-historique") for lid in place.labels) and place.wikipedia_url:
        criteria.append("C2")
    if place.sitelinks >= 4:
        criteria.append("C3")
    if "parc-national" in place.labels:
        criteria.append("C4")
    return criteria


def assign_tiers(ranked: list[Place], tiers: Tiers) -> list[tuple[Place, int, int]]:
    """Attribue un niveau à chaque lieu d'une collection, par rang décroissant.

    Le niveau est RELATIF à la collection : les meilleurs prennent le niveau 1.
    Un plancher de score absolu s'applique quand même — une collection peut
    avoir moins de 10 lieux au niveau 1 si le vivier ne suit pas. On ne remplit
    pas pour remplir.
    """
    ordered = sorted(ranked, key=lambda p: (-p.score, p.name))
    out: list[tuple[Place, int, int]] = []
    tier1_used = 0
    tier2_used = 0

    for index, place in enumerate(ordered, start=1):
        if tier1_used < tiers.tier1_size and place.score >= tiers.tier1_min_score:
            tier = 1
            tier1_used += 1
        elif tier2_used < tiers.tier2_size and place.score >= tiers.tier2_min_score:
            tier = 2
            tier2_used += 1
        else:
            tier = 3
        out.append((place, tier, index))
    return out
