"""Collecte des lieux candidats depuis Wikidata."""

from __future__ import annotations

import csv
import json
import logging
from pathlib import Path

from . import wikidata as wd
from .config import Config, Label, Theme
from .geo import normalize_dept_code, region_of
from .models import Place

LOG = logging.getLogger(__name__)


def fetch_theme(client: wd.SparqlClient, theme: Theme) -> list[Place]:
    """Lieux candidats pour un thème.

    Les classes sont interrogées par lots : une requête sur toutes les classes
    d'un coup dépasse régulièrement le timeout de WDQS.
    """
    by_qid: dict[str, Place] = {}

    for batch in wd.chunked(theme.wikidata_classes, 2):
        LOG.info("thème %s : classes %s", theme.id, ", ".join(batch))
        rows = client.query(wd.theme_query(batch, theme.min_sitelinks))
        for row in rows:
            place = _row_to_place(row, theme)
            if place is None:
                continue
            existing = by_qid.get(place.wikidata_id)
            # Une même entité peut remonter via plusieurs classes : on garde la
            # variante la mieux renseignée.
            if existing is None or _completeness(place) > _completeness(existing):
                by_qid[place.wikidata_id] = place

    LOG.info("thème %s : %s lieux candidats", theme.id, len(by_qid))
    return list(by_qid.values())


def _completeness(place: Place) -> int:
    return sum(
        1
        for value in (place.image_url, place.departement_code, place.elevation_m, place.wikipedia_url)
        if value
    )


def _row_to_place(row: dict[str, str], theme: Theme) -> Place | None:
    qid = wd.qid_from_uri(row.get("item"))
    coords = wd.parse_point(row.get("coord"))
    name = row.get("itemLabel")

    if not qid or not coords or not name:
        return None
    # Un libellé resté sous forme de Q-id signifie une entité sans nom exploitable.
    if name == qid:
        return None

    dept = normalize_dept_code(row.get("directDept") or row.get("parentDept"))
    region_code = row.get("parentRegion")
    if not region_code and dept:
        region = region_of(dept)
        region_code = region.code if region else None

    return Place(
        wikidata_id=qid,
        name=name,
        theme_id=theme.id,
        lat=coords[0],
        lon=coords[1],
        sitelinks=int(row.get("sitelinks") or 0),
        has_frwiki=bool(row.get("frwiki")),
        wikipedia_url=row.get("frwiki"),
        image_url=row.get("image"),
        commons_category=row.get("commons"),
        elevation_m=_as_int(row.get("elevation")),
        departement_code=dept,
        region_code=region_code,
        validation_radius_m=theme.radius_m,
    )


def _as_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


def fetch_label_members(client: wd.SparqlClient, label: Label, manual_dir: Path) -> set[str]:
    """Q-ids des lieux portant un label."""
    if label.is_manual:
        return _read_manual_label(label, manual_dir)

    rows = client.query(wd.label_members_query(label.query_kind, label.qid or ""))
    qids = {qid for qid in (wd.qid_from_uri(r.get("item")) for r in rows) if qid}
    LOG.info("label %s : %s membres", label.id, len(qids))
    return qids


def _read_manual_label(label: Label, manual_dir: Path) -> set[str]:
    path = manual_dir / f"{label.id}.csv"
    if not path.exists():
        LOG.warning(
            "label %s : pas de source Wikidata et %s absent — label ignoré",
            label.id,
            path,
        )
        return set()
    with path.open(encoding="utf-8") as fh:
        qids = {row["wikidata_id"].strip() for row in csv.DictReader(fh) if row.get("wikidata_id")}
    LOG.info("label %s : %s membres (liste manuelle)", label.id, len(qids))
    return qids


def apply_labels(places: list[Place], label_members: dict[str, set[str]]) -> None:
    """Reporte les labels sur les lieux déjà collectés."""
    for place in places:
        place.labels = sorted(
            label_id for label_id, qids in label_members.items() if place.wikidata_id in qids
        )


def run_fetch(client: wd.SparqlClient, config: Config, out_dir: Path, manual_dir: Path) -> list[Place]:
    out_dir.mkdir(parents=True, exist_ok=True)

    label_members: dict[str, set[str]] = {}
    for label in config.labels:
        try:
            label_members[label.id] = fetch_label_members(client, label, manual_dir)
        except Exception as exc:  # un label en échec ne doit pas tuer la collecte
            LOG.error("label %s : collecte échouée (%s)", label.id, exc)
            label_members[label.id] = set()

    places: list[Place] = []
    for theme in config.themes:
        try:
            places.extend(fetch_theme(client, theme))
        except Exception as exc:
            LOG.error("thème %s : collecte échouée (%s)", theme.id, exc)

    apply_labels(places, label_members)

    raw_path = out_dir / "places_raw.json"
    raw_path.write_text(
        json.dumps([p.to_dict() for p in places], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    LOG.info("%s lieux écrits dans %s", len(places), raw_path)
    return places
