"""Le catalogue brut, versionné et découpé par thème.

Deux problèmes se règlent au même endroit.

**La divergence.** Le catalogue ne se déduit pas du dépôt : il se collecte. Or
Wikidata bouge, les requêtes expirent, un thème échoue sans que rien ne
s'arrête. Deux machines qui lancent la même commande le même jour n'obtiennent
donc pas le même catalogue — et les décisions éditoriales, elles, portent sur
des Q-id précis. Une décision prise sur un catalogue que l'autre machine n'a
pas ne veut rien dire. La collecte n'est pas un produit de construction, c'est
une DONNÉE : elle doit vivre dans le dépôt.

**La perte silencieuse.** Une collecte complète écrivait un seul fichier. Quand
un thème échouait au milieu, ses lieux disparaissaient du fichier réécrit — le
journal le disait, mais la donnée était perdue jusqu'à la collecte suivante.
Un fichier par thème rend l'échec inoffensif : on ne réécrit que ce qu'on a
réellement recollecté, le reste ne bouge pas.

`places_raw.json` demeure, mais comme copie de travail reconstituée depuis ces
fichiers — c'est lui que lisent `enrich`, `build` et les diagnostics.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Iterable

from .models import Place

LOG = logging.getLogger(__name__)

# Ajouts manuels et candidats adoptés : ils appartiennent à des thèmes variés
# mais sont recollectés à chaque passage, y compris quand un seul thème est
# demandé. Les ranger dans le fichier de leur thème ferait perdre ceux des
# thèmes non recollectés ; ils ont donc leur propre fichier.
EXTRA_SHARD = "ajouts"
NO_THEME_SHARD = "sans-theme"


def shard_of(place: Place) -> str:
    """Le fichier qui possède ce lieu."""
    if place.pinned or place.source == "osm":
        return EXTRA_SHARD
    return place.theme_id or NO_THEME_SHARD


def _path(raw_dir: Path, shard: str) -> Path:
    return raw_dir / f"{shard}.json"


def _payload(place: Place) -> dict:
    """Le lieu tel qu'il s'écrit dans le dépôt.

    Sans le `slug`, qui se déduit du nom : une donnée dérivée dans un fichier
    versionné n'apporte rien et change en même temps que ce dont elle dérive.
    """
    payload = place.to_dict()
    payload.pop("slug", None)
    return payload


def write_raw(
    raw_dir: Path, places: Iterable[Place], replacing: Iterable[str]
) -> dict[str, int]:
    """Réécrit les seuls fichiers nommés dans `replacing`.

    Ce qui n'y figure pas n'est pas touché : c'est toute la protection. Un
    thème en échec n'est pas dans `replacing`, donc sa dernière collecte
    réussie survit — y compris quand la collecte du jour n'en a rien rendu.
    """
    raw_dir.mkdir(parents=True, exist_ok=True)
    grouped: dict[str, list[Place]] = {}
    for place in places:
        grouped.setdefault(shard_of(place), []).append(place)

    written: dict[str, int] = {}
    for shard in sorted(set(replacing)):
        path = _path(raw_dir, shard)
        members = grouped.get(shard, [])
        if not members:
            # Un thème retiré de la configuration, ou qui ne rend plus rien :
            # laisser le fichier ferait revivre ses lieux à chaque lecture.
            path.unlink(missing_ok=True)
            written[shard] = 0
            continue
        # Trié par Q-id : sans cela, deux collectes identiques produiraient des
        # fichiers différents et chaque `git diff` serait illisible.
        members = sorted(members, key=lambda p: p.wikidata_id)
        lines = ",\n".join(
            json.dumps(_payload(place), ensure_ascii=False, sort_keys=True)
            for place in members
        )
        # Un lieu par ligne : le format reste du JSON valide, et le dépôt voit
        # « trois lieux ajoutés » là où un document réindenté montrerait un
        # fichier entier réécrit.
        path.write_text(f"[\n{lines}\n]\n", encoding="utf-8")
        written[shard] = len(members)
    return written


def _load(path: Path) -> list[Place]:
    try:
        items = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        LOG.error("%s illisible (%s) — thème ignoré", path.name, exc)
        return []
    places = []
    for item in items:
        item.pop("slug", None)
        try:
            places.append(Place(**item))
        except TypeError as exc:
            LOG.error("%s : lieu illisible (%s)", path.name, exc)
    return places


def read_raw(raw_dir: Path) -> list[Place]:
    """Recompose le catalogue brut depuis les fichiers du dépôt.

    **Un même lieu peut figurer sous plusieurs thèmes**, et il le doit : le
    Louvre est un palais et un musée, Versailles est un château et un palais.
    C'est `dedupe_across_themes` qui tranche, à la construction, avec la règle
    du plus spécifique. Réduire ici à un lieu par Q-id lui retirerait le choix
    et laisserait l'ordre alphabétique des fichiers décider du thème.

    Les ajouts, eux, se comportent comme à la collecte : un lieu épinglé
    remplace tous ses rattachements automatiques, un candidat adopté ne comble
    que ce qui manque.
    """
    if not raw_dir.is_dir():
        return []

    par_theme: dict[tuple[str, str], Place] = {}
    extras: list[Place] = []
    for path in sorted(raw_dir.glob("*.json")):
        for place in _load(path):
            if path.stem == EXTRA_SHARD:
                extras.append(place)
            else:
                par_theme[(place.theme_id, place.wikidata_id)] = place

    pinned = {place.wikidata_id for place in extras if place.pinned}
    places = [p for p in par_theme.values() if p.wikidata_id not in pinned]
    places += [p for p in extras if p.pinned]

    # Les candidats adoptés ne complètent que ce qui manque : quand une requête
    # par classe a déjà trouvé le lieu, c'est ce rattachement-là qui vaut, pas
    # le thème deviné depuis une balise OpenStreetMap.
    known = {place.wikidata_id for place in places}
    places += [p for p in extras if not p.pinned and p.wikidata_id not in known]
    return places


def shards(raw_dir: Path) -> list[str]:
    """Les thèmes dont le dépôt porte une collecte."""
    if not raw_dir.is_dir():
        return []
    return sorted(path.stem for path in raw_dir.glob("*.json"))
