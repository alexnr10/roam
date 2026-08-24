"""Construction des collections et attribution des niveaux.

Règle cardinale : une collection n'existe que si elle a assez de lieux pour être
une collection. Sans ce garde-fou, croiser N thèmes par M échelons géographiques
produit des milliers de collections vides du type « Cascades de la Creuse :
2 lieux » — ce qui casse le jeu au lieu de l'enrichir.
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict

from .config import Config
from .geo import FRANCE, area, departements, regions
from .models import Collection, CollectionPlace, Place
from .score import assign_tiers, rescued

LOG = logging.getLogger(__name__)

EARTH_RADIUS_M = 6_371_000.0
# Deux lieux du même thème à moins de cette distance sont presque toujours deux
# entrées Wikidata pour le même site (le château et sa chapelle, par exemple).
DUPLICATE_DISTANCE_M = 150.0


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def dedupe(places: list[Place]) -> list[Place]:
    """Écarte les doublons de proximité, en gardant le mieux scoré."""
    kept: list[Place] = []
    by_theme: dict[str, list[Place]] = defaultdict(list)

    for place in sorted(places, key=lambda p: -p.score):
        neighbours = by_theme[place.theme_id]
        if any(
            haversine_m(place.lat, place.lon, other.lat, other.lon) < DUPLICATE_DISTANCE_M
            for other in neighbours
        ):
            LOG.debug("doublon écarté : %s (%s)", place.name, place.wikidata_id)
            continue
        neighbours.append(place)
        kept.append(place)

    LOG.info("déduplication : %s lieux gardés sur %s", len(kept), len(places))
    return kept


def _finalize(
    collection: Collection, members: list[Place], config: Config, cap: int | None = None
) -> Collection | None:
    """Applique plancher, plafond et niveaux. Renvoie None si la collection n'existe pas."""
    rules = config.collections
    if len(members) < rules.min_places:
        return None

    limit = cap or rules.max_places
    ordered = sorted(members, key=lambda p: (-p.score, p.name))[:limit]

    collection.places = [
        CollectionPlace(place_id=place.wikidata_id, tier=tier, rank=rank)
        for place, tier, rank in assign_tiers(ordered, config.tiers)
    ]
    return collection


def build_theme_collections(places: list[Place], config: Config) -> list[Collection]:
    by_theme: dict[str, list[Place]] = defaultdict(list)
    for place in places:
        by_theme[place.theme_id].append(place)

    out = []
    starved: list[str] = []
    for theme in config.themes:
        collection = Collection(
            slug=f"theme-{theme.id}",
            name=theme.name,
            kind="theme",
            theme_id=theme.id,
        )
        members = by_theme.get(theme.id, [])
        built = _finalize(collection, members, config, cap=theme.cap)
        if built:
            out.append(built)
        else:
            starved.append(f"{theme.id} {len(members)}")

    if starved:
        # Un thème déclaré qui ne produit AUCUNE collection nationale disparaît
        # sinon sans un mot : ses lieux ne survivent qu'au hasard des
        # collections géographiques, et l'onglet du thème reste vide dans
        # l'application. C'est le symptôme d'un thème à revoir ou à fusionner,
        # pas un détail de construction.
        LOG.warning(
            "%s thème(s) sans collection nationale, faute d'atteindre %s lieux : %s",
            len(starved),
            config.collections.min_places,
            ", ".join(starved),
        )
    return out


def build_label_collections(places: list[Place], config: Config) -> list[Collection]:
    out = []
    for label in config.labels:
        if not label.makes_collection:
            continue
        members = [p for p in places if label.id in p.labels]
        collection = Collection(
            slug=f"label-{label.id}",
            name=label.name,
            kind="label",
            label_id=label.id,
        )
        # Un label est une liste officielle et finie : on ne la tronque pas,
        # sinon la collection ne correspond plus au label qu'elle affiche.
        built = _finalize(collection, members, config, cap=len(members) or 1)
        if built:
            out.append(built)
    return out


def build_geo_collections(places: list[Place], config: Config) -> list[Collection]:
    """Collections « le meilleur de X », tous thèmes confondus."""
    out: list[Collection] = []

    for level in config.collections.geo_levels:
        buckets: dict[str, list[Place]] = defaultdict(list)
        for place in places:
            code = _geo_code(place, level)
            if code:
                buckets[code].append(place)

        for code, members in buckets.items():
            zone = area(level, code)
            if zone is None:
                continue
            collection = Collection(
                slug=f"geo-{level}-{code.lower()}",
                name=f"Le meilleur {zone.de_form}",
                kind="geo",
                geo_level=level,
                geo_code=code,
            )
            built = _finalize(collection, members, config)
            if built:
                out.append(built)
    return out


def build_cross_collections(places: list[Place], config: Config) -> list[Collection]:
    """Croisements thème × géographie (« Châteaux du Cantal »).

    Soumis aux mêmes règles : la grande majorité des croisements est écartée
    faute de lieux, et c'est exactement l'effet recherché.
    """
    out: list[Collection] = []

    for level in config.collections.cross_theme_levels:
        buckets: dict[tuple[str, str], list[Place]] = defaultdict(list)
        for place in places:
            code = _geo_code(place, level)
            if code:
                buckets[(place.theme_id, code)].append(place)

        for (theme_id, code), members in buckets.items():
            zone = area(level, code)
            if zone is None:
                continue
            theme = config.theme(theme_id)
            collection = Collection(
                slug=f"{theme_id}-{level}-{code.lower()}",
                name=f"{theme.name} {zone.de_form}",
                kind="geo",
                theme_id=theme_id,
                geo_level=level,
                geo_code=code,
            )
            built = _finalize(collection, members, config)
            if built:
                out.append(built)
    return out


def _geo_code(place: Place, level: str) -> str | None:
    if level == "departement":
        return place.departement_code
    if level == "region":
        return place.region_code
    if level == "country":
        return FRANCE.code
    return None


def apply_geographic_scope(places: list[Place], config: Config) -> list[Place]:
    """Écarte les lieux qu'on ne sait pas rattacher à un département français.

    Sans département, un lieu n'entre dans aucune collection géographique : il
    ne peut apparaître que dans « Le meilleur de France », où il se retrouve à
    concurrencer le Mont Blanc. C'est le cas des collectivités d'outre-mer, qui
    n'ont pas de code de département — les DOM, eux, en ont un et restent.
    """
    if not config.collections.require_departement:
        return places

    kept = [place for place in places if place.departement_code]
    dropped = [place for place in places if not place.departement_code]
    if dropped:
        LOG.warning(
            "hors périmètre : %s lieux sans département écartés (ex. %s). "
            "Si des lieux de métropole s'y trouvent, c'est que Wikidata ne les "
            "situe pas — lance `enrich` pour les rattacher par coordonnées.",
            len(dropped),
            ", ".join(place.name for place in dropped[:3]),
        )
    return kept


def dedupe_across_themes(places: list[Place], config: Config) -> list[Place]:
    """Un lieu n'appartient qu'à un seul thème.

    Le château de Versailles est aussi un palais, le Louvre est un palais et un
    musée : sans ce filtre, ils entreraient deux fois au catalogue, gonfleraient
    les compteurs et se retrouveraient à relire en double.

    Le thème retenu est le premier déclaré dans `themes.yaml`, dont l'ordre va
    du plus spécifique au plus générique — un lieu à la fois cathédrale et
    monument est une cathédrale.
    """
    rank = {theme.id: index for index, theme in enumerate(config.themes)}
    best: dict[str, Place] = {}
    collisions: list[tuple[str, str, str]] = []

    for place in places:
        current = best.get(place.wikidata_id)
        if current is None:
            best[place.wikidata_id] = place
            continue
        # Un lieu épinglé impose son thème : c'est un choix explicite.
        if place.pinned != current.pinned:
            winner, loser = (place, current) if place.pinned else (current, place)
        else:
            winner, loser = (
                (place, current)
                if rank.get(place.theme_id, 99) < rank.get(current.theme_id, 99)
                else (current, place)
            )
        best[place.wikidata_id] = winner
        collisions.append((winner.name, winner.theme_id, loser.theme_id))

    if collisions:
        LOG.info(
            "thèmes croisés : %s lieux rattachés à un seul thème (ex. %s)",
            len(collisions),
            ", ".join(f"{n} → {w} plutôt que {l}" for n, w, l in collisions[:3]),
        )
    return list(best.values())


def apply_notoriety_floor(places: list[Place], config: Config) -> list[Place]:
    """Écarte les lieux sous le plancher éditorial de leur thème.

    Ce filtre vit ici, et non dans la requête Wikidata, pour qu'ajuster un seuil
    coûte une seconde plutôt qu'une nouvelle collecte.
    """
    kept: list[Place] = []
    dropped: dict[str, int] = defaultdict(int)
    saved: dict[str, int] = defaultdict(int)

    for place in places:
        try:
            floor = config.theme(place.theme_id).min_sitelinks
        except KeyError:
            continue
        # Un lieu épinglé par le curateur passe outre : le plancher mesure la
        # documentation d'un lieu, pas son intérêt. Giverny et le château
        # d'Auvers-sur-Oise attirent le monde entier sans être documentés en
        # dix langues.
        if place.pinned or place.sitelinks >= floor:
            kept.append(place)
        elif rescued(place, config):
            kept.append(place)
            saved[place.theme_id] += 1
        else:
            dropped[place.theme_id] += 1

    if dropped:
        LOG.info(
            "plancher de notoriété : %s lieux écartés (%s)",
            sum(dropped.values()),
            ", ".join(f"{k} {v}" for k, v in sorted(dropped.items(), key=lambda x: -x[1])),
        )
    if saved:
        # Le réglage doit être visible pour être réglable : sans ce compte, le
        # repêchage agirait sans qu'on sache jamais sur combien de lieux.
        LOG.info(
            "%s lieux repêchés sous leur plancher — accueil du public attesté "
            "et score ≥ %s : %s",
            sum(saved.values()),
            config.scoring.rescue_score,
            ", ".join(f"{k} {v}" for k, v in sorted(saved.items(), key=lambda x: -x[1])),
        )
    return kept


def apply_access_filter(places: list[Place], config: Config) -> list[Place]:
    """Écarte les lieux dont OpenStreetMap dit l'accès explicitement refusé.

    L'application se joue sur place : on valide un lieu en s'y rendant. Un lieu
    où l'on ne peut pas entrer n'est donc pas collectionnable, si intéressante
    que soit son histoire — le château d'Hérouville en est l'exemple.

    Le signal est rare et délibéré : `access=private` ou `access=no` est posé à
    la main par un contributeur, et ne concerne qu'une vingtaine de lieux sur
    près de deux mille. Il ne s'agit donc pas d'une heuristique mais d'un fait,
    et un malus de score ne suffisait pas à s'en débarrasser.

    Deux échappatoires : un lieu épinglé — le curateur reste le dernier mot, et
    ce qui se voit très bien depuis la route est son choix — et un lieu qui
    affiche par ailleurs des HORAIRES, car une grotte aménagée porte souvent
    `access=no` parce qu'on n'y entre pas seul, la visite y étant guidée.

    Un simple site web ne suffit PAS à faire cette exception, et c'est un
    correctif : le château d'Hérouville en a un — descriptif, patrimonial —
    sans être ouvert au public, et se faisait donc réadmettre par la première
    version de ce filtre alors qu'il en est l'exemple même. Un site web prouve
    qu'un lieu existe et qu'on en parle ; seuls des horaires prouvent qu'on
    peut s'y rendre à une heure donnée.
    """
    refused = [
        p for p in places
        # Seuls des horaires renversent un accès refusé — un site web ne le
        # prouve pas, voir la docstring pour le cas du château d'Hérouville.
        if p.visitable is False and not p.pinned and not p.opening_hours
    ]
    excluded = {id(p) for p in refused}
    kept = [p for p in places if id(p) not in excluded]
    if refused:
        LOG.info(
            "accès refusé : %s lieux écartés (%s)",
            len(refused),
            ", ".join(p.name for p in refused[:5]),
        )
    return kept


def apply_alpine_filter(places: list[Place], config: Config) -> list[Place]:
    """Écarte les sommets qui, faute de preuve du contraire, ne se rejoignent
    qu'en alpinisme.

    Le château d'Hérouville avait un signal explicite — `access=private` — qui
    permet de l'écarter avec certitude. Un sommet à 3 000 m n'en a aucun : le
    pipeline ne collecte les sommets que sur Wikidata, qui ne dit rien d'un
    chemin de randonnée ou d'un accès équipé. Il n'y a donc ni preuve qu'on
    s'y rend à pied, ni preuve du contraire.

    Faute de ce signal positif, l'ambiguïté se résout par le principe que le
    curateur a posé pour ce cas précis : au moindre doute, on écarte. Un
    sommet réellement accessible malgré son altitude — l'Aiguille du Midi, le
    Pic du Midi — revient par un épinglage manuel ou une proposition de la
    communauté, jamais par une supposition du pipeline.
    """
    threshold = config.alerts.alpine_elevation_m
    kept: list[Place] = []
    dropped: list[Place] = []

    for place in places:
        suspect = (
            place.theme_id == "sommets"
            and place.elevation_m is not None
            and place.elevation_m >= threshold
        )
        if suspect and not place.pinned:
            dropped.append(place)
        else:
            kept.append(place)

    if dropped:
        LOG.info(
            "accès alpin : %s sommets écartés au-dessus de %s m, faute d'un "
            "signal d'accès prouvé (%s)",
            len(dropped),
            threshold,
            ", ".join(p.name for p in dropped[:5]),
        )
    return kept


def build_all(places: list[Place], config: Config) -> tuple[list[Place], list[Collection]]:
    # L'ordre compte : on fixe d'abord le thème de chaque lieu, puis on lui
    # applique le plancher de CE thème, puis on écarte les doublons de lieu.
    kept = dedupe(
        apply_notoriety_floor(
            apply_alpine_filter(
                apply_access_filter(
                    dedupe_across_themes(apply_geographic_scope(places, config), config), config
                ),
                config,
            ),
            config,
        )
    )
    collections = (
        build_theme_collections(kept, config)
        + build_label_collections(kept, config)
        + build_geo_collections(kept, config)
        + build_cross_collections(kept, config)
    )

    # Un lieu qui n'entre dans aucune collection ne sert à rien : on le sort.
    used = {cp.place_id for c in collections for cp in c.places}
    retained = [p for p in kept if p.wikidata_id in used]
    LOG.info(
        "%s collections, %s lieux retenus (%s écartés faute de collection)",
        len(collections),
        len(retained),
        len(kept) - len(retained),
    )
    return retained, collections
