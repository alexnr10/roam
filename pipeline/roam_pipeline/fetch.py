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


def fetch_theme(
    client: wd.SparqlClient,
    theme: Theme,
    label_members: dict[str, set[str]] | None = None,
) -> list[Place]:
    """Lieux candidats pour un thème.

    Les classes sont interrogées par lots : une requête sur toutes les classes
    d'un coup dépasse régulièrement le timeout de WDQS.
    """
    by_qid: dict[str, Place] = {}

    # Thème alimenté par des listes officielles : on part des membres des labels
    # plutôt que d'une classe Wikidata.
    if theme.from_labels:
        members: set[str] = set()
        for label_id in theme.from_labels:
            members |= (label_members or {}).get(label_id, set())
        if not members:
            LOG.warning("thème %s : aucun membre de label disponible", theme.id)
        for batch in wd.chunked(sorted(members), 150):
            for row in client.query(wd.items_query(batch)):
                place = _row_to_place(row, theme)
                if place is not None:
                    by_qid[place.wikidata_id] = place

    # Une classe à la fois, et par pages : les classes volumineuses (châteaux,
    # abbayes, cathédrales) dépassaient le délai de WDQS en une seule requête.
    for class_qid in theme.wikidata_classes:
        LOG.info("thème %s : classe %s", theme.id, class_qid)
        for row in _paged(client, lambda limit, offset, q=class_qid: wd.theme_query(
            [q], theme.fetch_min_sitelinks, limit=limit, offset=offset
        )):
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


PAGE_SIZE = 800


def _paged(client: wd.SparqlClient, build_query, page_size: int = PAGE_SIZE):
    """Parcourt une requête page par page jusqu'à épuisement."""
    offset = 0
    while True:
        rows = client.query(build_query(page_size, offset))
        yield from rows
        if len(rows) < page_size:
            return
        offset += page_size


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
        admin_qid=wd.qid_from_uri(row.get("admin")),
        validation_radius_m=theme.radius_m,
    )


def _as_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


def resolve_admin(client: wd.SparqlClient, places: list[Place]) -> None:
    """Complète département et région à partir de la commune de rattachement.

    Seconde passe volontaire : bornée par les communes réellement rencontrées,
    elle coûte quelques requêtes, là où le même chemin transitif intégré à la
    requête de thème faisait échouer les classes volumineuses.
    """
    admin_qids = sorted({p.admin_qid for p in places if p.admin_qid})
    if not admin_qids:
        return

    codes: dict[str, tuple[str | None, str | None]] = {}
    for batch in wd.chunked(admin_qids, 200):
        try:
            rows = client.query(wd.admin_codes_query(batch))
        except Exception as exc:
            LOG.error("résolution administrative : lot échoué (%s)", exc)
            continue
        for row in rows:
            qid = wd.qid_from_uri(row.get("admin"))
            if qid:
                codes[qid] = (row.get("deptCode"), row.get("regionCode"))

    resolved = 0
    for place in places:
        if not place.admin_qid:
            continue
        dept_raw, region_raw = codes.get(place.admin_qid, (None, None))
        dept = normalize_dept_code(dept_raw)
        place.departement_code = dept
        # Le code de région se déduit du département : plus fiable que la
        # remontée Wikidata, qui rate les communes mal rattachées.
        region = region_of(dept) if dept else None
        place.region_code = region.code if region else region_raw
        if dept:
            resolved += 1

    LOG.info(
        "rattachement administratif : %s/%s lieux localisés (%s communes)",
        resolved,
        len(places),
        len(admin_qids),
    )


def fetch_label_members(client: wd.SparqlClient, label: Label, manual_dir: Path) -> set[str]:
    """Q-ids des lieux portant un label."""
    if label.is_manual:
        return _read_manual_label(label, manual_dir)

    if not label.qid:
        # Label en attente de résolution : mieux vaut l'ignorer bruyamment que
        # produire un catalogue amputé sans le dire.
        LOG.warning(
            "label %s : identifiant non résolu (terme « %s ») — ignoré. "
            "Lance `suggest-qids` pour le résoudre.",
            label.id,
            label.search,
        )
        return set()

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


def run_fetch(
    client: wd.SparqlClient,
    config: Config,
    out_dir: Path,
    manual_dir: Path,
    only: list[str] | None = None,
) -> list[Place]:
    """Collecte les candidats. `only` limite aux thèmes nommés.

    Une collecte complète dure une demi-heure ; quand un thème échoue, on doit
    pouvoir le reprendre seul plutôt que tout refaire. Les thèmes non demandés
    sont donc conservés depuis la collecte précédente.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_path = out_dir / "places_raw.json"

    themes = [t for t in config.themes if not only or t.id in only]
    if only:
        unknown = set(only) - {t.id for t in config.themes}
        if unknown:
            raise KeyError(f"thème(s) inconnu(s) : {', '.join(sorted(unknown))}")

    label_members: dict[str, set[str]] = {}
    for label in config.labels:
        try:
            label_members[label.id] = fetch_label_members(client, label, manual_dir)
        except Exception as exc:  # un label en échec ne doit pas tuer la collecte
            LOG.error("label %s : collecte échouée (%s)", label.id, exc)
            label_members[label.id] = set()

    places: list[Place] = []
    failed: list[str] = []
    for theme in themes:
        try:
            places.extend(fetch_theme(client, theme, label_members))
        except Exception as exc:
            LOG.error("thème %s : collecte échouée (%s)", theme.id, exc)
            failed.append(theme.id)

    resolve_admin(client, places)
    apply_labels(places, label_members)

    # Reprise partielle : on réinjecte les thèmes qu'on n'a pas recollectés.
    if only and raw_path.exists():
        kept = [
            Place(**{k: v for k, v in item.items() if k != "slug"})
            for item in json.loads(raw_path.read_text(encoding="utf-8"))
            if item.get("theme_id") not in {t.id for t in themes}
        ]
        LOG.info("%s lieux conservés des thèmes non recollectés", len(kept))
        places = kept + places

    raw_path.write_text(
        json.dumps([p.to_dict() for p in places], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    LOG.info("%s lieux écrits dans %s", len(places), raw_path)

    if failed:
        # Le message doit être actionnable : une demi-heure de collecte ne se
        # relance pas en entier pour deux thèmes.
        LOG.error(
            "%s thème(s) en échec : %s — reprends-les seuls avec "
            "`python -m roam_pipeline fetch --only %s`",
            len(failed),
            ", ".join(failed),
            " ".join(failed),
        )
    return places
