"""Structures de données du pipeline."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field, asdict, fields
from typing import Any


def display_name(value: str) -> str:
    """Le nom tel qu'il doit s'afficher.

    Les libellés français de Wikidata ne sont pas capitalisés de façon fiable :
    « Dune du Pilat » y côtoie « château d'Hérouville » et « musée des
    impressionnismes Giverny ». C'est cohérent du point de vue de Wikidata, qui
    traite le libellé comme un syntagme et non comme un titre — mais dans une
    liste de lieux, une minuscule initiale se lit comme une faute.

    On ne touche QUE la première lettre. Capitaliser davantage détruirait les
    noms propres internes (« Saint-Cirq-Lapopie », « d'Hérouville ») et les
    sigles, et il n'existe aucune règle mécanique pour distinguer « Pont du
    Gard » de « pont de Normandie ».
    """
    cleaned = " ".join(value.split())
    if cleaned and cleaned[0].islower():
        return cleaned[0].upper() + cleaned[1:]
    return cleaned


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
    # Correction manuelle issue de la revue : −1 pour un `promote`, +1 pour un
    # `demote`. Un DÉCALAGE DE NIVEAU, pas de points.
    #
    # La première version ajoutait ou retirait soixante points. Un décalage de
    # score ne peut pas exprimer une intention de rang : deux lieux au même
    # score ne sont pas dans le même voisinage, et la même correction en
    # déplaçait un de deux niveaux, un autre d'aucun. Mesuré sur le catalogue
    # réel, seuls 25 `demote` sur 73 descendaient d'un cran ; 27 en perdaient
    # deux et 15 disparaissaient purement et simplement du catalogue — alors
    # qu'écarter un lieu, c'est `drop`, et que ce sont deux gestes distincts.
    tier_shift: int = 0
    # La promotion vaut-elle DEUX gestes ?
    #
    # Un `promote` sur un lieu hors collection nationale le fait ENTRER, et
    # rien de plus : « la promotion paie l'entrée, pas le rang ». C'est la
    # règle, et elle protège d'un vrai accident — le pont du Port-à-l'Anglais,
    # quarante et unième des quarante-deux ponts, arrivait au niveau 1.
    #
    # Mais elle laissait le curateur sans mot pour dire « fais-le entrer ET
    # monte-le », qui est une intention légitime et simplement DIFFÉRENTE. Le
    # verdict `promote2` la porte, et lui seul : sur un lieu déjà dans sa
    # collection, il ne peut rien faire de plus qu'un `promote`, puisque
    # aucune entrée n'est à payer. L'accident reste donc hors d'atteinte.
    promotion_double: bool = False
    # Conservé parce que son département était vide, non parce qu'il franchit le
    # plancher de son thème. La revue doit le dire : c'est le pari le plus
    # fragile du catalogue, et le relecteur doit pouvoir le juger comme tel.
    geo_rescued: bool = False
    # Ajouté à la main par le curateur : échappe au plancher de notoriété et
    # l'emporte sur le rattachement automatique à un thème.
    pinned: bool = False
    # Validé en revue, par opposition à épinglé à la main dans `places.csv`.
    #
    # Les deux posent `pinned`, et il le faut : un lieu que le curateur a vu et
    # gardé ne doit pas disparaître parce qu'un plancher a bougé. Mais ils ne
    # valent pas la même chose face à un PLAFOND. « Keep » veut dire « celui-ci
    # ne me choque pas » ; il y en a mille cinq cent cinquante-cinq, et les
    # traiter comme des dispenses remplissait le plafond des cathédrales avant
    # qu'une seule région n'ait eu sa part.
    kept_in_review: bool = False
    # Épinglé DANS places.csv, par opposition à épinglé par un verdict `keep`.
    #
    # Les deux posent `pinned`, et les plafonds ne réservent leur place qu'aux
    # premiers — un `keep` veut dire « celui-ci ne me choque pas », il y en a
    # mille cinq cent cinquante-cinq, et les traiter en dispenses remplissait
    # les plafonds avant qu'aucune région n'ait eu sa part.
    #
    # Les distinguer par « pinned mais pas kept_in_review » PARAISSAIT suffire.
    # Ça ne l'était pas : un lieu de places.csv que le curateur valide en revue
    # porte les deux drapeaux, perd sa réservation, et tombe sous le plafond de
    # son thème. Le Familistère de Guise a disparu du catalogue exactement
    # ainsi — épinglé à la main, puis gardé en revue, donc écarté.
    #
    # Le drapeau est posé par `apply_decisions`, qui photographie l'état
    # d'AVANT que la revue ne parle : à ce moment, `pinned` ne peut venir que
    # de places.csv.
    pinned_by_hand: bool = False
    # D'où vient ce lieu. « wikidata » : trouvé par sa classe, comme la
    # majorité. « osm » : trouvé parce qu'OpenStreetMap atteste qu'il accueille
    # du public, alors que Wikidata ne le classait nulle part. Cette origine ne
    # change rien au score — elle dit au relecteur pourquoi la ligne est là.
    source: str = "wikidata"
    inclusion_criteria: list[str] = field(default_factory=list)
    # Classe Wikidata disqualifiante, quand il y en a une : un parc
    # d'attractions entré par la porte des musées, par exemple. Le libellé de
    # la classe, pas son Q-id — pour que le journal se lise.
    excluded_class: str | None = None
    # Fréquentation annuelle, d'après Wikidata. `None` signifie « non
    # renseignée », ce qui ne vaut RIEN — ni bonus ni malus. Wikidata ne la
    # documente que pour une minorité de sites.
    visitors_per_year: int | None = None
    # Consultations mensuelles typiques de l'article francophone (médiane des
    # douze derniers mois). `None` signifie « pas de données » et ne vaut RIEN.
    #
    # Le décompte de langues mesure ce que le MONDE écrit d'un lieu ; celui-ci,
    # ce que le public FRANCOPHONE va y chercher. Le Champ-de-Mars est dans
    # cinquante-six langues parce que la tour Eiffel s'y trouve, et les jardins
    # de la Fontaine dans six — ce que personne n'irait appeler un classement.
    pageviews_per_month: int | None = None
    # Le crédit de la photo : qui l'a prise, et sous quelle licence. Une image
    # de Commons n'est pas libre de droits — la plupart des licences exigent de
    # citer l'auteur, et le catalogue en publie deux mille. `None` signifie
    # « Commons ne le documente pas » : la fiche se rabat alors sur le nom du
    # dépôt, qui est le minimum honnête.
    image_author: str | None = None
    image_licence: str | None = None
    # Le fichier auquel ce crédit appartient. Un crédit n'est pas une propriété
    # du LIEU mais de la PHOTO : changer la photo d'un lieu — `photos.csv` le
    # permet — sans oublier son crédit afficherait le nom d'un photographe sous
    # l'image de quelqu'un d'autre. On garde donc le titre du fichier crédité,
    # et l'export ne cite l'auteur que si les deux concordent.
    image_credit_for: str | None = None
    # Entré par une classe GÉNÉRIQUE (`broad_classes`) et non par une classe
    # propre au thème. Une porte large ne vaut pas une porte précise : le
    # dédoublonnage inter-thèmes s'en sert pour trancher.
    via_broad_class: bool = False

    def __post_init__(self) -> None:
        # Le nom est normalisé à la construction, d'où qu'il vienne : Wikidata,
        # OpenStreetMap ou une liste manuelle. Le faire au seul point de
        # collecte laissait passer les autres sources.
        self.name = display_name(self.name)

    @property
    def slug(self) -> str:
        return slugify(self.name)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["slug"] = self.slug
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Place":
        """Reconstruit un lieu en IGNORANT les champs qu'on ne connaît plus.

        Une collecte versionnée survit à ses lecteurs : les fichiers du dépôt
        portent les champs du jour où ils ont été écrits. Retirer un champ du
        modèle rendrait alors tout le catalogue illisible d'un coup, pour une
        donnée dont plus personne ne veut.
        """
        connus = {champ.name for champ in fields(cls)}
        return cls(**{clef: valeur for clef, valeur in payload.items() if clef in connus})


@dataclass
class CollectionPlace:
    place_id: str          # wikidata_id
    tier: int
    rank: int
    # Entré parce que le curateur l'a remonté, alors que le plafond de la
    # collection l'avait coupé. La collection dépasse alors son plafond, et
    # c'est assumé : le plafond est une heuristique, la décision un jugement.
    forced: bool = False
    # Le niveau qu'il aurait eu SANS la décision du curateur. Le niveau seul
    # ne dit pas d'où l'on part : un lieu remonté depuis le niveau 2 et un
    # lieu qui valait déjà le niveau 1 s'affichent à l'identique, et la revue
    # ne peut pas relire ses propres décisions.
    natural_tier: int = 0


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
