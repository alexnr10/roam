"""Sorties du pipeline : JSON, feuille de revue éditoriale, seed SQL."""

from __future__ import annotations

import csv
import json
import logging
from collections import defaultdict
from pathlib import Path

from .config import Config
from .geo import departements, regions
from .models import Collection, Place

LOG = logging.getLogger(__name__)

REVIEW_HEADER = [
    "decision",       # à remplir : (vide)=en attente, keep, drop, promote, demote
    "curator_note",
    "name",
    "theme",
    "departement",
    "score",
    "sitelinks",
    "labels",
    "collections",
    "best_tier",
    "lat",
    "lon",
    "wikidata_id",
    "wikipedia_url",
    "image_url",
]


def write_json(places: list[Place], collections: list[Collection], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "places.json").write_text(
        json.dumps([p.to_dict() for p in places], ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out_dir / "collections.json").write_text(
        json.dumps([c.to_dict() for c in collections], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    LOG.info("JSON écrit dans %s", out_dir)


def write_review_csv(places: list[Place], collections: list[Collection], out_path: Path) -> None:
    """Feuille de revue éditoriale.

    C'est le vrai livrable du pipeline : la liste triée que quelqu'un doit relire
    ligne à ligne. Le pipeline propose, l'humain décide. La colonne `decision`
    est relue par `apply-review`.
    """
    membership: dict[str, list[str]] = defaultdict(list)
    best_tier: dict[str, int] = {}
    for collection in collections:
        for cp in collection.places:
            membership[cp.place_id].append(collection.slug)
            best_tier[cp.place_id] = min(best_tier.get(cp.place_id, 9), cp.tier)

    depts = departements()
    ordered = sorted(places, key=lambda p: (p.theme_id, -p.score, p.name))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(REVIEW_HEADER)
        for place in ordered:
            dept = depts.get(place.departement_code or "")
            writer.writerow(
                [
                    "",
                    "",
                    place.name,
                    place.theme_id,
                    dept.name if dept else "",
                    f"{place.score:.1f}",
                    place.sitelinks,
                    "|".join(place.labels),
                    len(membership.get(place.wikidata_id, [])),
                    best_tier.get(place.wikidata_id, ""),
                    f"{place.lat:.6f}",
                    f"{place.lon:.6f}",
                    place.wikidata_id,
                    place.wikipedia_url or "",
                    place.image_url or "",
                ]
            )
    LOG.info("feuille de revue : %s (%s lignes)", out_path, len(ordered))


def read_review_csv(path: Path) -> dict[str, tuple[str, str]]:
    """Relit les décisions de la feuille de revue : qid → (décision, note)."""
    decisions: dict[str, tuple[str, str]] = {}
    with path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            qid = (row.get("wikidata_id") or "").strip()
            decision = (row.get("decision") or "").strip().lower()
            if qid and decision:
                decisions[qid] = (decision, (row.get("curator_note") or "").strip())
    return decisions


def _sql_str(value: str | None) -> str:
    if value is None or value == "":
        return "null"
    return "'" + value.replace("'", "''") + "'"


def _sql_array(values: list[str]) -> str:
    if not values:
        return "'{}'"
    inner = ",".join(v.replace('"', '\\"') for v in values)
    return _sql_str("{" + inner + "}")


def write_seed_sql(
    places: list[Place], collections: list[Collection], config: Config, out_path: Path
) -> None:
    """Seed idempotent : référentiels, lieux (en `draft`), collections, appartenances."""
    lines: list[str] = [
        "-- Généré par roam_pipeline. Ne pas éditer à la main.",
        "-- Les lieux sont insérés en statut 'draft' : la publication est une",
        "-- décision humaine, jamais une sortie de pipeline.",
        "begin;",
        "",
        "-- Thèmes",
    ]

    for theme in config.themes:
        lines.append(
            "insert into themes (id, name, name_singular, icon, default_radius_m) values "
            f"({_sql_str(theme.id)}, {_sql_str(theme.name)}, {_sql_str(theme.name_singular)}, "
            f"{_sql_str(theme.icon)}, {theme.radius_m}) "
            "on conflict (id) do update set name = excluded.name, "
            "default_radius_m = excluded.default_radius_m;"
        )

    lines += ["", "-- Labels"]
    for label in config.labels:
        lines.append(
            "insert into labels (id, name, authority, score_bonus, makes_collection) values "
            f"({_sql_str(label.id)}, {_sql_str(label.name)}, {_sql_str(label.authority)}, "
            f"{label.score_bonus}, {str(label.makes_collection).lower()}) "
            "on conflict (id) do update set name = excluded.name, "
            "score_bonus = excluded.score_bonus;"
        )

    lines += ["", "-- Découpage administratif"]
    lines.append(
        "insert into geo_areas (id, level, code, name, parent_id) values "
        "('country:FR', 'country', 'FR', 'France', null) on conflict (id) do nothing;"
    )
    for region in regions().values():
        lines.append(
            "insert into geo_areas (id, level, code, name, parent_id) values "
            f"({_sql_str(region.id)}, 'region', {_sql_str(region.code)}, "
            f"{_sql_str(region.name)}, 'country:FR') on conflict (id) do nothing;"
        )
    for dept in departements().values():
        parent = f"region:{dept.parent_code}" if dept.parent_code else None
        lines.append(
            "insert into geo_areas (id, level, code, name, parent_id) values "
            f"({_sql_str(dept.id)}, 'departement', {_sql_str(dept.code)}, "
            f"{_sql_str(dept.name)}, {_sql_str(parent)}) on conflict (id) do nothing;"
        )

    lines += ["", "-- Lieux"]
    for place in places:
        dept_id = f"departement:{place.departement_code}" if place.departement_code else None
        region_id = f"region:{place.region_code}" if place.region_code else None
        lines.append(
            "insert into places (slug, name, theme_id, location, validation_radius_m, "
            "elevation_m, departement_id, region_id, score, inclusion_criteria, "
            "wikidata_id, wikipedia_url, commons_category, sitelink_count, cover_image_url, "
            "status, source) values ("
            f"{_sql_str(place.slug)}, {_sql_str(place.name)}, {_sql_str(place.theme_id)}, "
            f"ST_SetSRID(ST_MakePoint({place.lon}, {place.lat}), 4326)::geography, "
            f"{place.validation_radius_m}, "
            f"{place.elevation_m if place.elevation_m is not None else 'null'}, "
            f"{_sql_str(dept_id)}, {_sql_str(region_id)}, {place.score}, "
            f"{_sql_array(place.inclusion_criteria)}, {_sql_str(place.wikidata_id)}, "
            f"{_sql_str(place.wikipedia_url)}, {_sql_str(place.commons_category)}, "
            f"{place.sitelinks}, {_sql_str(place.image_url)}, 'draft', 'pipeline') "
            "on conflict (wikidata_id) do update set "
            "name = excluded.name, score = excluded.score, "
            "sitelink_count = excluded.sitelink_count, updated_at = now();"
        )
        for label_id in place.labels:
            lines.append(
                "insert into place_labels (place_id, label_id) select p.id, "
                f"{_sql_str(label_id)} from places p where p.wikidata_id = "
                f"{_sql_str(place.wikidata_id)} on conflict do nothing;"
            )

    lines += ["", "-- Collections"]
    for collection in collections:
        geo_id = (
            f"{collection.geo_level}:{collection.geo_code}"
            if collection.geo_level and collection.geo_code
            else None
        )
        tier_counts = "'{" + ",".join(str(n) for n in collection.tier_counts) + "}'"
        lines.append(
            "insert into collections (slug, name, kind, theme_id, label_id, geo_area_id, "
            "place_count, tier_counts, status) values ("
            f"{_sql_str(collection.slug)}, {_sql_str(collection.name)}, "
            f"{_sql_str(collection.kind)}, {_sql_str(collection.theme_id)}, "
            f"{_sql_str(collection.label_id)}, {_sql_str(geo_id)}, "
            f"{len(collection.places)}, {tier_counts}, 'draft') "
            "on conflict (slug) do update set name = excluded.name, "
            "place_count = excluded.place_count, tier_counts = excluded.tier_counts, "
            "updated_at = now();"
        )
        for cp in collection.places:
            lines.append(
                "insert into collection_places (collection_id, place_id, tier, rank) "
                f"select c.id, p.id, {cp.tier}, {cp.rank} from collections c, places p "
                f"where c.slug = {_sql_str(collection.slug)} and p.wikidata_id = "
                f"{_sql_str(cp.place_id)} on conflict (collection_id, place_id) "
                "do update set tier = excluded.tier, rank = excluded.rank;"
            )

    lines += ["", "commit;", ""]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    LOG.info("seed SQL : %s (%s instructions)", out_path, len(lines))
