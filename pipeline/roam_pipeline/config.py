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
    # Plancher ÉDITORIAL, appliqué à la construction : se règle sans recollecter.
    min_sitelinks: int
    # Plancher de COLLECTE, appliqué dans la requête SPARQL. Il ne sert qu'à
    # garder les requêtes tenables ; le laisser bas permet de régler le plancher
    # éditorial librement, sans repasser une demi-heure sur Wikidata.
    fetch_min_sitelinks: int
    cap: int
    wikidata_classes: list[str]
    # Thème alimenté par des listes officielles plutôt que par une classe
    # Wikidata : les labels sont déjà une curation humaine, finie et fiable.
    from_labels: list[str] = field(default_factory=list)
    # Termes à résoudre avec `suggest-qids` — présents tant qu'un identifiant
    # reste à confirmer.
    search: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Label:
    id: str
    name: str
    authority: str
    score_bonus: float
    makes_collection: bool
    query_kind: str
    qid: str | None
    search: str | None = None

    @property
    def is_manual(self) -> bool:
        return self.query_kind == "manual"


@dataclass(frozen=True)
class Scoring:
    sitelinks_weight: float
    has_image_bonus: float
    has_frwiki_bonus: float
    article_weight: float
    label_stacking: str
    # Ouverture au public, d'après OpenStreetMap. Trois états et non deux :
    # « non renseigné » ne vaut ni bonus ni malus, sinon les deux tiers du
    # catalogue seraient pénalisés par une lacune de balisage.
    visitable_bonus: float = 0.0
    not_visitable_malus: float = 0.0
    # Remise sur le plancher de notoriété pour un lieu dont l'accueil du public
    # est attesté ET qui a un article francophone. Une PROPORTION du plancher du
    # thème, et non un nombre fixe : retirer trois langues à un plancher de
    # douze est une remise, à un plancher de cinq c'est une amnistie.
    visitable_floor_ratio: float = 1.0


@dataclass(frozen=True)
class Tiers:
    tier1_size: int
    tier2_size: int
    tier1_min_score: float
    tier2_min_score: float


@dataclass(frozen=True)
class Alerts:
    alpine_elevation_m: int


@dataclass(frozen=True)
class CollectionRules:
    min_places: int
    max_places: int
    geo_levels: list[str]
    cross_theme_levels: list[str]
    require_departement: bool


@dataclass(frozen=True)
class Config:
    themes: list[Theme]
    labels: list[Label]
    scoring: Scoring
    tiers: Tiers
    collections: CollectionRules
    alerts: Alerts

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
            fetch_min_sitelinks=int(t.get("fetch_min_sitelinks", 3)),
            cap=int(t["cap"]),
            wikidata_classes=list(t.get("wikidata_classes") or []),
            from_labels=list(t.get("from_labels") or []),
            search=list(t.get("search") or []),
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
                search=q.get("search"),
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
        require_departement=bool(raw["geo"].get("require_departement", True)),
    )

    alerts = Alerts(**raw.get("alerts", {"alpine_elevation_m": 2500}))

    _validate(themes, labels)
    return Config(
        themes=themes,
        labels=labels,
        scoring=scoring,
        tiers=tiers,
        collections=rules,
        alerts=alerts,
    )


def _validate(themes: list[Theme], labels: list[Label]) -> None:
    label_ids = {lbl.id for lbl in labels}
    seen: set[str] = set()
    for t in themes:
        if t.id in seen:
            raise ValueError(f"identifiant de thème dupliqué : {t.id}")
        seen.add(t.id)
        # Un thème sans source est admis s'il porte des termes de recherche : il
        # est en attente de résolution par `suggest-qids`, et la collecte
        # l'ignorera bruyamment plutôt que de le taire.
        if not t.wikidata_classes and not t.from_labels and not t.search:
            raise ValueError(f"le thème {t.id} n'a ni classe Wikidata ni label source")
        for label_id in t.from_labels:
            if label_id not in label_ids:
                raise ValueError(f"le thème {t.id} référence un label inconnu : {label_id}")
        for qid in t.wikidata_classes:
            if not qid.startswith("Q") or not qid[1:].isdigit():
                raise ValueError(f"Q-id invalide dans le thème {t.id} : {qid}")

    seen.clear()
    for lbl in labels:
        if lbl.id in seen:
            raise ValueError(f"identifiant de label dupliqué : {lbl.id}")
        seen.add(lbl.id)
        # Un label sans qid est admis s'il porte un terme de recherche : il est
        # en attente de résolution par `suggest-qids`, et sera simplement ignoré
        # par la collecte avec un avertissement.
        if not lbl.is_manual and not lbl.qid and not lbl.search:
            raise ValueError(
                f"le label {lbl.id} n'est pas 'manual' et n'a ni qid ni terme de recherche"
            )
