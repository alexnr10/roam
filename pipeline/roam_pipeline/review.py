"""Décisions éditoriales, et leur conservation.

Le pipeline propose, l'humain décide — mais une décision qui ne survit pas au
prochain `build` n'est pas une décision, c'est un affichage. Les verdicts du
curateur vivent donc dans `data/manual/decisions.csv`, à côté de ses autres
listes, et non dans les fichiers de sortie que chaque commande réécrit.

Le fichier est cumulatif : relire cent lieux de plus n'efface pas les mille
précédents.

Un second fichier, `names.csv`, porte les noms d'affichage choisis. Les deux
sont séparés à dessein : renommer et écarter sont deux gestes différents, et un
lieu peut être renommé ET gardé, renommé ET écarté. Fondus en un seul fichier,
la colonne `decision` deviendrait ambiguë.
"""

from __future__ import annotations

import csv
import logging
from collections import Counter
from pathlib import Path

from .models import Place, display_name

LOG = logging.getLogger(__name__)

DECISIONS = ("keep", "drop", "promote", "demote")

HEADER = """# Décisions éditoriales, cumulées au fil des revues.
#
# keep    : validé, et conservé même si un plancher venait à monter.
# drop    : écarté du catalogue.
# promote : remonté dans le classement.
# demote  : descendu dans le classement.
#
# Ce fichier est la mémoire de la curation. Le supprimer perd tout le travail
# de relecture ; en corriger une ligne suffit à revenir sur un verdict.
#
wikidata_id,decision,name,note
"""


def read_decisions(path: Path) -> dict[str, tuple[str, str]]:
    """`{qid: (décision, note)}`. Fichier absent = aucune décision."""
    decisions: dict[str, tuple[str, str]] = {}
    if not path.exists():
        return decisions

    lines = [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    for row in csv.DictReader(lines):
        qid = (row.get("wikidata_id") or "").strip()
        decision = (row.get("decision") or "").strip().lower()
        if not qid or decision not in DECISIONS:
            continue
        decisions[qid] = (decision, (row.get("note") or "").strip())
    return decisions


def write_decisions(path: Path, decisions: dict[str, tuple[str, str]],
                    names: dict[str, str]) -> None:
    """Réécrit le fichier, trié par identifiant.

    Le nom accompagne chaque ligne pour qu'elle reste relisible : revenir sur
    un verdict ne doit pas demander d'aller chercher ce que « Q3578611 »
    désigne.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        fh.write(HEADER)
        writer = csv.writer(fh)
        for qid in sorted(decisions):
            decision, note = decisions[qid]
            writer.writerow([qid, decision, names.get(qid, ""), note])
    LOG.info("décisions : %s verdicts conservés dans %s", len(decisions), path)


def apply_decisions(
    places: list[Place], decisions: dict[str, tuple[str, str]], adjust: float,
    strict: bool = False,
) -> tuple[list[Place], Counter[str]]:
    """Applique les verdicts. Renvoie les lieux conservés et le décompte.

    `drop` retire. `promote` et `demote` ne retirent rien : ils corrigent le
    score, parce qu'un relecteur qui trouve un lieu mal classé n'a pas dit
    qu'il ne valait rien. `keep` épingle — un lieu explicitement validé ne doit
    pas disparaître parce qu'un plancher a bougé depuis.
    """
    kept: list[Place] = []
    counts: Counter[str] = Counter()
    counted: set[str] = set()

    for place in places:
        decision, _note = decisions.get(place.wikidata_id, ("", ""))
        # Compté une fois par LIEU, pas par ligne : un même lieu peut figurer
        # sous deux thèmes avant le dédoublonnage, et le décompte affiché
        # dépassait alors le nombre de décisions prises.
        if place.wikidata_id not in counted:
            counted.add(place.wikidata_id)
            counts[decision or "pending"] += 1
        if decision == "drop":
            continue
        if decision == "promote":
            place.curator_adjustment = adjust
        elif decision == "demote":
            place.curator_adjustment = -adjust
        elif decision == "keep":
            place.pinned = True
        elif strict:
            # En mode strict, seul ce qui a été explicitement relu est conservé.
            continue
        kept.append(place)

    return kept, counts


# ---------------------------------------------------------------------------
# Renommages
# ---------------------------------------------------------------------------

NAMES_HEADER = """# Noms d'affichage choisis par le curateur.
#
# Wikidata donne un libellé, pas un titre. Il est parfois exact mais illisible
# (« musée des impressionnismes Giverny »), parfois encombré d'une précision
# qui n'a de sens que dans une base de données. Une ligne ici l'emporte.
#
# Ce n'est PAS un verdict d'inclusion : renommer et écarter sont deux gestes
# différents, et les mélanger rendrait `decisions.csv` ambigu. D'où ce fichier.
#
wikidata_id,name,note
"""


def read_names(path: Path) -> dict[str, str]:
    """`{qid: nom choisi}`. Fichier absent = aucun renommage."""
    names: dict[str, str] = {}
    if not path.exists():
        return names

    lines = [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    for row in csv.DictReader(lines):
        qid = (row.get("wikidata_id") or "").strip()
        name = (row.get("name") or "").strip()
        if qid and name:
            names[qid] = display_name(name)
    return names


def write_names(path: Path, names: dict[str, str], notes: dict[str, str] | None = None) -> None:
    notes = notes or {}
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        fh.write(NAMES_HEADER)
        writer = csv.writer(fh)
        for qid in sorted(names):
            writer.writerow([qid, names[qid], notes.get(qid, "")])
    LOG.info("noms : %s renommages conservés dans %s", len(names), path)


def apply_names(places: list[Place], names: dict[str, str]) -> int:
    """Remplace le libellé de Wikidata par celui du curateur. Renvoie le compte.

    Appliqué à CHAQUE construction, comme les décisions : un renommage qui ne
    survit pas au prochain `build` n'est pas une décision, c'est un affichage.
    """
    changed = 0
    for place in places:
        chosen = names.get(place.wikidata_id)
        if chosen and chosen != place.name:
            place.name = chosen
            changed += 1
    return changed
