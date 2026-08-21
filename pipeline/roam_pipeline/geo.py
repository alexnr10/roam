"""Référentiel géographique français (départements, régions).

Le champ `de_form` porte la forme complète du complément de nom
(« du Cantal », « de la Manche », « des Landes », « de l'Ain »). Le français ne
permet pas de la dériver d'une règle simple, donc elle est stockée telle quelle :
c'est ce qui donne « Châteaux du Cantal » et non « Châteaux de Cantal ».
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "reference"


@dataclass(frozen=True)
class Area:
    code: str
    name: str
    de_form: str
    level: str
    parent_code: str | None = None

    @property
    def id(self) -> str:
        return f"{self.level}:{self.code}"


@lru_cache(maxsize=1)
def regions() -> dict[str, Area]:
    out: dict[str, Area] = {}
    with (DATA_DIR / "regions.csv").open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            out[row["code"]] = Area(
                code=row["code"], name=row["name"], de_form=row["de_form"], level="region"
            )
    return out


@lru_cache(maxsize=1)
def departements() -> dict[str, Area]:
    out: dict[str, Area] = {}
    with (DATA_DIR / "departements.csv").open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            out[row["code"]] = Area(
                code=row["code"],
                name=row["name"],
                de_form=row["de_form"],
                level="departement",
                parent_code=row["region_code"],
            )
    return out


FRANCE = Area(code="FR", name="France", de_form="de France", level="country")


def area(level: str, code: str) -> Area | None:
    if level == "country":
        return FRANCE
    if level == "region":
        return regions().get(code)
    if level == "departement":
        return departements().get(code)
    return None


def region_of(departement_code: str) -> Area | None:
    dept = departements().get(departement_code)
    if dept is None or dept.parent_code is None:
        return None
    return regions().get(dept.parent_code)


def normalize_dept_code(raw: str | None) -> str | None:
    """Normalise un code INSEE de département venant de Wikidata ('1' → '01')."""
    if not raw:
        return None
    code = raw.strip().upper()
    if code in departements():
        return code
    if code.isdigit():
        padded = code.zfill(2)
        if padded in departements():
            return padded
        if code in departements():
            return code
    return None
