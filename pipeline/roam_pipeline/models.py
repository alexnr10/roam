"""Structures de données du pipeline."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field, asdict
from typing import Any


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii").lower()
    ascii_only = re.sub(r"[^a-z0-9]+", "-", ascii_only).strip("-")
    return re.sub(r"-{2,}", "-", ascii_only)


@dataclass
class Place:
    wikidata_id: str
    name: str
    theme_id: str
    lat: float
    lon: float

    sitelinks: int = 0
    has_frwiki: bool = False
    wikipedia_url: str | None = None
    # Taille de l'article francophone, en octets. Complète le décompte de langues
    # là où celui-ci ne discrimine rien — typiquement les sites naturels.
    article_bytes: int = 0
    # Deux premières phrases de l'article francophone (CC BY-SA), affichées
    # comme description dans l'application.
    summary: str | None = None
    image_url: str | None = None
    commons_category: str | None = None
    elevation_m: int | None = None
    # Date de démolition ou de disparition (P576). Sa seule présence ne suffit
    # pas à écarter : beaucoup de ruines se visitent. C'est un signal de revue.
    dissolved: str | None = None

    # Ouverture au public, d'après OpenStreetMap. `None` signifie inconnu, ce
    # qui n'est pas la même chose que fermé — l'absence de balise ne prouve rien.
    visitable: bool | None = None
    opening_hours: str | None = None
    website: str | None = None
    osm_id: str | None = None

    departement_code: str | None = None
    region_code: str | None = None
    # Commune de rattachement, en code INSEE. C'est la maille la plus fine de
    # la carte de conquête — celle qui se colore en une seule visite, et donc
    # celle qui donne le sentiment d'avancer.
    commune_code: str | None = None
    commune_name: str | None = None
    # Commune de rattachement (Q-id), résolue en codes INSEE par une seconde passe.
    admin_qid: str | None = None

    labels: list[str] = field(default_factory=list)
    validation_radius_m: int = 150
    score: float = 0.0
    # Correction manuelle issue de la feuille de revue. Doit peser plus lourd
    # qu'un bonus de label, sans quoi une décision humaine ne pourrait pas
    # rattraper un lieu que Wikidata documente mal.
    curator_adjustment: float = 0.0
    # Ajouté à la main par le curateur : échappe au plancher de notoriété et
    # l'emporte sur le rattachement automatique à un thème.
    pinned: bool = False
    # D'où vient ce lieu. « wikidata » : trouvé par sa classe, comme la
    # majorité. « osm » : trouvé parce qu'OpenStreetMap atteste qu'il accueille
    # du public, alors que Wikidata ne le classait nulle part. Cette origine ne
    # change rien au score — elle dit au relecteur pourquoi la ligne est là.
    source: str = "wikidata"
    inclusion_criteria: list[str] = field(default_factory=list)

    @property
    def slug(self) -> str:
        return slugify(self.name)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["slug"] = self.slug
        return payload


@dataclass
class CollectionPlace:
    place_id: str          # wikidata_id
    tier: int
    rank: int


@dataclass
class Collection:
    slug: str
    name: str
    kind: str              # 'theme' | 'geo' | 'label'
    theme_id: str | None = None
    label_id: str | None = None
    geo_level: str | None = None
    geo_code: str | None = None
    places: list[CollectionPlace] = field(default_factory=list)

    @property
    def tier_counts(self) -> list[int]:
        counts = [0, 0, 0]
        for cp in self.places:
            counts[cp.tier - 1] += 1
        return counts

    def to_dict(self) -> dict[str, Any]:
        return {
            "slug": self.slug,
            "name": self.name,
            "kind": self.kind,
            "theme_id": self.theme_id,
            "label_id": self.label_id,
            "geo_level": self.geo_level,
            "geo_code": self.geo_code,
            "place_count": len(self.places),
            "tier_counts": self.tier_counts,
            "places": [asdict(cp) for cp in self.places],
        }
