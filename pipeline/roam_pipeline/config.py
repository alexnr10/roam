"""Chargement et validation de la configuration du pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


@dataclass(frozen=True)
class Theme:
    id: str
    name: str
    name_singular: str
    icon: str
    radius_m: int
    min_sitelinks: int
    cap: int
    wikidata_classes: list[str]


@dataclass(frozen=True)
class Label:
    id: str
    name: str
    authority: str
    score_bonus: float
    makes_collection: bool
    query_kind: str
    qid: str | None

    @property
    def is_manual(self) -> bool:
        return self.query_kind == "manual"


@dataclass(frozen=True)
class Scoring:
    sitelinks_weight: float
    has_image_bonus: float
    has_frwiki_bonus: float
    label_stacking: str


@dataclass(frozen=True)
class Tiers:
    tier1_size: int
    tier2_size: int
    tier1_min_score: float
    tier2_min_score: float


@dataclass(frozen=True)
class CollectionRules:
    min_places: int
    max_places: int
    geo_levels: list[str]
    cross_theme_levels: list[str]


@dataclass(frozen=True)
class Config:
    themes: list[Theme]
    labels: list[Label]
    scoring: Scoring
    tiers: Tiers
    collections: CollectionRules

    def theme(self, theme_id: str) -> Theme:
        for t in self.themes:
            if t.id == theme_id:
                return t
        raise KeyError(f"thème inconnu : {theme_id}")

    def label(self, label_id: str) -> Label:
        for lbl in self.labels:
            if lbl.id == label_id:
                return lbl
        raise KeyError(f"label inconnu : {label_id}")


def _read_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def load_config(config_dir: Path | None = None) -> Config:
    d = config_dir or CONFIG_DIR

    themes = [
        Theme(
            id=t["id"],
            name=t["name"],
            name_singular=t["name_singular"],
            icon=t.get("icon", ""),
            radius_m=int(t["radius_m"]),
            min_sitelinks=int(t["min_sitelinks"]),
            cap=int(t["cap"]),
            wikidata_classes=list(t["wikidata_classes"]),
        )
        for t in _read_yaml(d / "themes.yaml")["themes"]
    ]

    labels = []
    for lbl in _read_yaml(d / "labels.yaml")["labels"]:
        q = lbl.get("wikidata_query") or {"kind": "manual"}
        labels.append(
            Label(
                id=lbl["id"],
                name=lbl["name"],
                authority=lbl.get("authority", ""),
                score_bonus=float(lbl.get("score_bonus", 0)),
                makes_collection=bool(lbl.get("makes_collection", False)),
                query_kind=q["kind"],
                qid=q.get("qid"),
            )
        )

    raw = _read_yaml(d / "scoring.yaml")
    scoring = Scoring(**raw["scoring"])
    tiers = Tiers(**raw["tiers"])
    rules = CollectionRules(
        min_places=int(raw["collections"]["min_places"]),
        max_places=int(raw["collections"]["max_places"]),
        geo_levels=list(raw["geo"]["levels"]),
        cross_theme_levels=list(raw["geo"]["cross_theme_levels"]),
    )

    _validate(themes, labels)
    return Config(themes=themes, labels=labels, scoring=scoring, tiers=tiers, collections=rules)


def _validate(themes: list[Theme], labels: list[Label]) -> None:
    seen: set[str] = set()
    for t in themes:
        if t.id in seen:
            raise ValueError(f"identifiant de thème dupliqué : {t.id}")
        seen.add(t.id)
        for qid in t.wikidata_classes:
            if not qid.startswith("Q") or not qid[1:].isdigit():
                raise ValueError(f"Q-id invalide dans le thème {t.id} : {qid}")

    seen.clear()
    for lbl in labels:
        if lbl.id in seen:
            raise ValueError(f"identifiant de label dupliqué : {lbl.id}")
        seen.add(lbl.id)
        if not lbl.is_manual and not lbl.qid:
            raise ValueError(f"le label {lbl.id} n'est pas 'manual' mais n'a pas de qid")
