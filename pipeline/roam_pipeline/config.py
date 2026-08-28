"""Chargement et validation de la configuration du pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


@dataclass(frozen=True)
class BroadClass:
    """Classe trop générique pour le plancher du thème, admise plus haut.

    La fondation Claude-Monet n'est, chez Wikidata, qu'une « maison » (Q3947).
    Collecter cette classe au plancher du thème ramènerait toutes les maisons
    de France ; ne pas la collecter du tout laisse dehors la maison de Monet.

    Le plancher est la sortie : une classe générique n'est admise qu'au-dessus
    d'une notoriété qui, à elle seule, prouve qu'on ne parle plus d'un pavillon.
    C'est le seul filtre dont on dispose quand la classe ne dit rien.
    """

    qid: str
    fetch_min_sitelinks: int
    #: Classes qui FERMENT cette route sans écarter le lieu du catalogue : il
    #: reste disponible pour un thème déclaré plus loin.
    exceptions: list[str] = field(default_factory=list)
    #: Termes d'exception encore à résoudre par `suggest-qids`.
    except_search: list[str] = field(default_factory=list)


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
    # « nature » ou « culture ». Roam promet des PAYSAGES autant que du
    # patrimoine ; sans cette étiquette, l'équilibre entre les deux ne se
    # mesure pas, et une dérive vers le bâti passe inaperçue.
    kind: str = "culture"
    # Thème alimenté par des listes officielles plutôt que par une classe
    # Wikidata : les labels sont déjà une curation humaine, finie et fiable.
    from_labels: list[str] = field(default_factory=list)
    # Termes à résoudre avec `suggest-qids` — présents tant qu'un identifiant
    # reste à confirmer.
    search: list[str] = field(default_factory=list)
    # Classes génériques, collectées à un plancher qui leur est propre.
    broad_classes: list[BroadClass] = field(default_factory=list)

    @property
    def collected_classes(self) -> list[tuple[str, int]]:
        """`(classe, plancher de collecte)` — tout ce que le thème interroge."""
        return [(qid, floor) for qid, floor, _ in self.collection_routes]

    @property
    def collection_routes(self) -> list[tuple[str, int, list[str]]]:
        """`(classe, plancher, classes qui ferment la route)`.

        Les trois éléments d'une requête de collecte. Les classes propres du
        thème n'ont pas d'exception : elles sont déjà spécifiques.
        """
        return [
            (qid, self.fetch_min_sitelinks, []) for qid in self.wikidata_classes
        ] + [
            (broad.qid, broad.fetch_min_sitelinks, list(broad.exceptions))
            for broad in self.broad_classes
        ]


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
    # Score à partir duquel un lieu dont l'accueil du public est ATTESTÉ est
    # repêché malgré un plancher qu'il ne franchit pas. Les deux conditions
    # comptent : un plancher qui mesure la documentation ne peut pas être
    # franchi par plus de documentation. 0 désactive le repêchage.
    rescue_score: float = 0.0


@dataclass(frozen=True)
class Visitors:
    """Fréquentation annuelle : le seul signal qui mesure l'affluence.

    `property_id` reste `None` tant que l'identifiant n'a pas été résolu par
    `suggest-qids --property`. Dans ce cas le signal est simplement inactif —
    aucun lieu n'en profite, aucun n'en pâtit.

    Le champ ne s'appelle pas `property` : dans un corps de classe, ce nom
    masque la fonction intégrée du même nom et casse le décorateur ci-dessous.
    """

    property_id: str | None = None
    search: str | None = None
    weight: float = 0.0
    scale: int = 10_000

    @property
    def active(self) -> bool:
        return bool(self.property_id and self.weight)


@dataclass(frozen=True)
class Tiers:
    tier1_size: int
    tier2_size: int
    tier1_min_score: float
    tier2_min_score: float


@dataclass(frozen=True)
class Exclusions:
    """Classes Wikidata qui disqualifient un lieu, quel que soit son thème.

    Un parc d'attractions n'entre pas au catalogue parce qu'il possède un
    aquarium classé « musée » quelque part dans sa hiérarchie de classes. La
    liste est GLOBALE et non par thème : le problème n'est pas qu'un delphinarium
    soit mal rangé, c'est qu'il n'a rien à faire dans Roam.
    """

    qids: list[str] = field(default_factory=list)
    # Termes à résoudre avec `suggest-qids`, comme pour les thèmes.
    search: list[str] = field(default_factory=list)


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
    exclusions: Exclusions = field(default_factory=Exclusions)
    visitors: Visitors = field(default_factory=Visitors)

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
            kind=t.get("kind", "culture"),
            # `str()` n'est pas cosmétique : YAML lit « 3947 » comme un entier,
            # et la validation ci-dessous — celle qui dit clairement ce qui ne
            # va pas — mourait avant d'avoir pu parler.
            wikidata_classes=[str(q) for q in (t.get("wikidata_classes") or [])],
            from_labels=list(t.get("from_labels") or []),
            search=list(t.get("search") or []),
            broad_classes=[
                BroadClass(
                    qid=str(b["qid"]),
                    fetch_min_sitelinks=int(b["fetch_min_sitelinks"]),
                    exceptions=[str(q) for q in (b.get("except") or [])],
                    except_search=list(b.get("except_search") or []),
                )
                for b in (t.get("broad_classes") or [])
            ],
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

    seen_visitors = raw.get("visitors") or {}
    visitors = Visitors(
        property_id=(str(seen_visitors["property"]) if seen_visitors.get("property") else None),
        search=seen_visitors.get("search"),
        weight=float(seen_visitors.get("weight", 0.0)),
        scale=int(seen_visitors.get("scale", 10_000)),
    )

    raw_themes = _read_yaml(d / "themes.yaml")
    excluded = raw_themes.get("exclude_classes") or {}
    exclusions = Exclusions(
        qids=[str(q) for q in (excluded.get("qids") or [])],
        search=list(excluded.get("search") or []),
    )

    _validate(themes, labels, exclusions, visitors)
    return Config(
        themes=themes,
        labels=labels,
        scoring=scoring,
        tiers=tiers,
        collections=rules,
        alerts=alerts,
        exclusions=exclusions,
        visitors=visitors,
    )


def _validate(themes: list[Theme], labels: list[Label],
              exclusions: Exclusions | None = None,
              visitors: Visitors | None = None) -> None:
    label_ids = {lbl.id for lbl in labels}
    seen: set[str] = set()
    for t in themes:
        if t.id in seen:
            raise ValueError(f"identifiant de thème dupliqué : {t.id}")
        seen.add(t.id)
        # Un thème sans source est admis s'il porte des termes de recherche : il
        # est en attente de résolution par `suggest-qids`, et la collecte
        # l'ignorera bruyamment plutôt que de le taire.
        if not t.collected_classes and not t.from_labels and not t.search:
            raise ValueError(f"le thème {t.id} n'a ni classe Wikidata ni label source")
        for label_id in t.from_labels:
            if label_id not in label_ids:
                raise ValueError(f"le thème {t.id} référence un label inconnu : {label_id}")
        for qid, _floor in t.collected_classes:
            if not qid.startswith("Q") or not qid[1:].isdigit():
                raise ValueError(f"Q-id invalide dans le thème {t.id} : {qid}")
        for broad in t.broad_classes:
            for qid in broad.exceptions:
                if not qid.startswith("Q") or not qid[1:].isdigit():
                    raise ValueError(
                        f"Q-id d'exception invalide dans le thème {t.id} : {qid}"
                    )
            # Une classe générique au plancher du thème n'est plus générique :
            # elle ramènerait tout, et le garde-fou serait décoratif.
            if broad.fetch_min_sitelinks <= t.fetch_min_sitelinks:
                raise ValueError(
                    f"le thème {t.id} déclare la classe générique {broad.qid} à un plancher "
                    f"({broad.fetch_min_sitelinks}) qui n'est pas plus haut que le sien "
                    f"({t.fetch_min_sitelinks}) : elle ramènerait tout"
                )

    seen.clear()
    for lbl in labels:
        if lbl.id in seen:
            raise ValueError(f"identifiant de label dupliqué : {lbl.id}")
        seen.add(lbl.id)
        # Un label sans qid est admis s'il porte un terme de recherche : il est
        # en attente de résolution par `suggest-qids`, et sera simplement ignoré
        # par la collecte avec un avertissement.
    for theme in themes:
        if theme.kind not in ("nature", "culture"):
            raise ValueError(
                f"le thème {theme.id} a un `kind` inconnu : « {theme.kind} » "
                "(attendu « nature » ou « culture »)"
            )

    for lbl in labels:
        if not lbl.is_manual and not lbl.qid and not lbl.search:
            raise ValueError(
                f"le label {lbl.id} n'est pas 'manual' et n'a ni qid ni terme de recherche"
            )

    for qid in (str(q) for q in (exclusions.qids if exclusions else [])):
        if not qid.startswith("Q") or not qid[1:].isdigit():
            raise ValueError(f"Q-id invalide dans `exclude_classes` : {qid}")

    if visitors and visitors.property_id:
        prop = visitors.property_id
        if not prop.startswith("P") or not prop[1:].isdigit():
            raise ValueError(f"identifiant de propriété invalide pour `visitors` : {prop}")
        if visitors.scale < 1:
            raise ValueError("`visitors.scale` doit être positif")

    # Une classe ne peut pas être à la fois ce qu'on cherche et ce qu'on refuse :
    # le thème serait vidé sans que rien ne le dise.
    banned = set(exclusions.qids if exclusions else [])
    for theme in themes:
        clash = banned.intersection(qid for qid, _ in theme.collected_classes)
        if clash:
            raise ValueError(
                f"le thème {theme.id} collecte une classe que `exclude_classes` refuse : "
                f"{', '.join(sorted(clash))}"
            )
