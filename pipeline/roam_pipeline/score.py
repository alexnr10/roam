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


def score_breakdown(place: Place, config: Config) -> dict[str, float]:
    """Détail du score, poste par poste.

    Un classement qu'on ne peut pas auditer ne peut pas être corrigé : le
    relecteur doit voir POURQUOI un lieu est devant un autre, sinon il ne peut
    que constater le résultat.
    """
    s: Scoring = config.scoring
    # log1p : le passage de 2 à 6 langues est bien plus significatif que de 40 à 44.
    parts = {
        "notoriete": round(s.sitelinks_weight * math.log1p(max(place.sitelinks, 0)), 1),
        "labels": round(label_bonus(place.labels, config), 1),
        # Taille rapportée au millier d'octets, atténuée : un article deux fois
        # plus long n'est pas deux fois plus remarquable.
        "article": round(s.article_weight * math.log1p(max(place.article_bytes, 0) / 1000), 1),
        "image": s.has_image_bonus if (place.image_url or place.commons_category) else 0.0,
        "frwiki": s.has_frwiki_bonus if place.has_frwiki else 0.0,
        # Le seul poste qui ne mesure pas la documentation d'un lieu mais sa
        # visitabilité. `None` ne vaut rien : l'absence de balise dans
        # OpenStreetMap ne dit pas qu'un lieu est fermé, elle ne dit rien.
        "acces": _access_score(place, s),
        # Le seul poste qui mesure l'AFFLUENCE. Les autres mesurent ce qu'on
        # écrit d'un lieu ; celui-ci, combien de gens s'y rendent.
        "visiteurs": _visitors_score(place, config),
        # Ce que le public FRANCOPHONE va chercher sur un lieu, quand les
        # langues ne disent que ce que le monde en écrit.
        "consultations": _pageviews_score(place, config),

    }
    parts["total"] = round(sum(parts.values()), 1)
    return parts


def _visitors_score(place: Place, config: Config) -> float:
    """Bonus de fréquentation. Jamais de malus.

    Wikidata ne renseigne la fréquentation que d'une minorité de sites.
    Pénaliser les autres reviendrait à noter le zèle des contributeurs, pas
    l'intérêt des lieux — c'est le raisonnement déjà tenu pour l'ouverture au
    public, et il vaut ici mot pour mot.

    `log1p` comme pour la notoriété : l'écart qui compte est celui entre un
    musée de sous-préfecture et un site national, pas entre le Louvre et
    Versailles.
    """
    rule = config.visitors
    if not rule.active or not place.visitors_per_year:
        return 0.0
    return round(rule.weight * math.log1p(place.visitors_per_year / rule.scale), 1)


def _pageviews_score(place: Place, config: Config) -> float:
    """Bonus de consultation. Jamais de malus, et nul tant qu'il n'est pas pesé.

    Le décompte de langues mesure la documentation INTERNATIONALE d'un lieu.
    Le Champ-de-Mars figure dans cinquante-six langues parce que la tour Eiffel
    s'y trouve ; les jardins de la Fontaine, un des plus beaux jardins
    classiques d'Europe, dans six. Les consultations de l'article francophone
    disent autre chose : combien de gens d'ici s'y intéressent.

    Ce n'est pas « ça vaut le détour » — aucune donnée gratuite ne le mesure.
    C'est la curiosité, qui en est le plus proche parent gratuit.
    """
    rule = config.pageviews
    if not rule.active or not place.pageviews_per_month:
        return 0.0
    return round(rule.weight * math.log1p(place.pageviews_per_month / rule.scale), 1)


def _access_score(place: Place, s: Scoring) -> float:
    if place.visitable is True:
        return s.visitable_bonus
    if place.visitable is False:
        return -s.not_visitable_malus
    return 0.0


def rescued(place: Place, config: Config) -> bool:
    """Ce lieu sous son plancher mérite-t-il d'être conservé quand même ?

    Deux conditions, et la première n'est pas négociable : **son accueil du
    public doit être attesté**. Le plancher mesure la documentation d'un lieu ;
    le franchir avec plus de documentation n'aurait aucun sens, et c'est
    l'erreur qu'a produite la première version — un score seuil à 70 repêchait
    2 757 lieux, parce que photo et article francophone valent treize points
    d'office et que presque tout monument français en a. Dans le bas du
    classement, le score est presque constant : il ne discrimine rien.

    Les horaires d'OpenStreetMap, eux, sont une preuve d'une autre nature — un
    fait de terrain, posé par quelqu'un passé devant. C'est ce qui manquait au
    musée des impressionnismes de Giverny, cinq langues et pourtant visité du
    monde entier.

    Le score sert alors de second filtre, pour ne pas repêcher tout ce qui
    ouvre une billetterie.
    """
    threshold = config.scoring.rescue_score
    return bool(threshold and place.visitable is True and place.score >= threshold)


def compute_score(place: Place, config: Config) -> float:
    return score_breakdown(place, config)["total"]


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

    La décision du curateur déplace le lieu d'EXACTEMENT un cran, dans la limite
    des trois niveaux, et c'est ce qui la rend fiable : un lieu monté monte, un
    lieu descendu descend, quel que soit son voisinage.

    Le décompte des places porte sur le niveau FINAL, jamais sur celui qu'on
    aurait donné sans la décision. Un lieu descendu libère donc sa place de
    niveau 1 pour le suivant — sans quoi il l'occuperait sans y figurer, et le
    lieu d'après reculerait sans que personne l'ait voulu.

    Un `promote` peut en revanche porter une collection à onze lieux de niveau 1,
    quand il remonte un lieu que le plafond avait déjà refoulé. C'est assumé :
    le plafond est une heuristique, la décision est un jugement, et faire
    redescendre quelqu'un d'autre en silence serait pire.
    """
    ordered = sorted(ranked, key=lambda p: (-p.score, p.name))
    juges: list[tuple[Place, int]] = []
    tier1_used = 0
    tier2_used = 0

    for place in ordered:
        if tier1_used < tiers.tier1_size and place.score >= tiers.tier1_min_score:
            tier = 1
        elif tier2_used < tiers.tier2_size and place.score >= tiers.tier2_min_score:
            tier = 2
        else:
            tier = 3
        tier = min(3, max(1, tier + place.tier_shift))
        # Les places se comptent sur le niveau FINAL, pas sur celui qu'on aurait
        # donné sans la décision. Autrement un lieu descendu occuperait une
        # place de niveau 1 sans y figurer, et le lieu suivant se retrouverait
        # au niveau 2 sans que personne l'ait voulu : cinquante-huit lieux
        # gardés reculaient ainsi d'un cran à la première mesure.
        if tier == 1:
            tier1_used += 1
        elif tier == 2:
            tier2_used += 1
        juges.append((place, tier))

    # Renumérotés dans l'ordre des niveaux : sans cela, un lieu descendu
    # garderait son rang et la liste afficherait un niveau 3 avant un niveau 1.
    juges.sort(key=lambda couple: (couple[1], -couple[0].score, couple[0].name))
    return [(place, tier, index) for index, (place, tier) in enumerate(juges, start=1)]
