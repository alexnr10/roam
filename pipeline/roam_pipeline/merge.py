"""Réconcilier deux revues faites chacune de son côté.

Les fichiers de `data/manual/` sont réécrits en entier par le pipeline, triés
par identifiant. Deux soirées de relecture menées sur deux machines produisent
donc deux versions du même fichier, et git ne sait pas les départager : il pose
des marqueurs de conflit au milieu d'un travail que personne n'a perdu.

Or ces fichiers ne sont pas du texte : ce sont des tables dont la clé est le
Q-id. La fusion juste est évidente — l'union des deux côtés. Le seul cas qui
demande un humain est le lieu tranché DIFFÉREMMENT des deux côtés, et il est
rare ; on garde alors la version locale et on la nomme, plutôt que d'inventer
une règle qui déciderait à la place du curateur.
"""

from __future__ import annotations

import csv
import io
import logging
from dataclasses import dataclass, field
from pathlib import Path

LOG = logging.getLogger(__name__)

OURS = "<<<<<<<"
BASE = "|||||||"
THEIRS = "======="
END = ">>>>>>>"


def has_conflict(text: str) -> bool:
    return any(line.startswith(OURS) for line in text.splitlines())


def split_conflict(text: str) -> tuple[str, str]:
    """Sépare un fichier conflictuel en ses deux versions complètes.

    Un fichier peut porter plusieurs blocs de conflit ; les parties communes
    appartiennent aux deux versions.
    """
    ours: list[str] = []
    theirs: list[str] = []
    side = "les deux"
    for line in text.splitlines():
        if line.startswith(OURS):
            side = "nous"
        elif line.startswith(BASE):
            side = "ancêtre"          # section produite par `diff3`, à ignorer
        elif line.startswith(THEIRS):
            side = "eux"
        elif line.startswith(END):
            side = "les deux"
        elif side == "les deux":
            ours.append(line)
            theirs.append(line)
        elif side == "nous":
            ours.append(line)
        elif side == "eux":
            theirs.append(line)
    return "\n".join(ours), "\n".join(theirs)


def _parse(text: str) -> tuple[list[str], list[str], list[dict]]:
    """`(lignes de commentaire, colonnes, lignes)`."""
    comments = [l for l in text.splitlines() if l.lstrip().startswith("#")]
    body = [l for l in text.splitlines() if l.strip() and not l.lstrip().startswith("#")]
    reader = csv.DictReader(body)
    return comments, list(reader.fieldnames or []), [row for row in reader]


@dataclass
class MergeReport:
    path: Path
    kept: int = 0
    added: int = 0
    disagreements: list[tuple[str, str, str]] = field(default_factory=list)


def merge_text(ours: str, theirs: str, key: str = "wikidata_id") -> tuple[str, MergeReport]:
    """Union des deux tables. La version LOCALE l'emporte sur un désaccord."""
    c_ours, cols_ours, rows_ours = _parse(ours)
    c_theirs, cols_theirs, rows_theirs = _parse(theirs)
    comments = c_ours or c_theirs
    columns = cols_ours or cols_theirs
    if key not in columns:
        raise ValueError(f"colonne « {key} » absente : {columns}")

    report = MergeReport(path=Path("."))
    fusion: dict[str, dict] = {}
    for row in rows_theirs:
        if row.get(key):
            fusion[row[key]] = row
    mine = {row[key]: row for row in rows_ours if row.get(key)}
    report.added = len([q for q in fusion if q not in mine])

    for qid, row in mine.items():
        other = fusion.get(qid)
        if other is not None and other != row:
            # Ce qui distingue vraiment les deux verdicts, sans le bruit des
            # colonnes de confort (le nom, la note).
            champ = next((c for c in columns if c != key and other.get(c) != row.get(c)), "")
            if champ:
                report.disagreements.append((qid, row.get(champ, ""), other.get(champ, "")))
        fusion[qid] = row
    report.kept = len(fusion)

    out = io.StringIO()
    if comments:
        out.write("\n".join(comments) + "\n")
    writer = csv.DictWriter(out, fieldnames=columns)
    writer.writeheader()
    for qid in sorted(fusion):
        writer.writerow({c: fusion[qid].get(c, "") for c in columns})
    return out.getvalue(), report


def merge_file(path: Path, key: str = "wikidata_id") -> MergeReport | None:
    """Résout un fichier conflictuel sur place. `None` s'il n'y a rien à faire."""
    text = path.read_text(encoding="utf-8")
    if not has_conflict(text):
        return None
    ours, theirs = split_conflict(text)
    merged, report = merge_text(ours, theirs, key)
    report.path = path
    path.write_text(merged, encoding="utf-8")
    return report


def conflicted(directory: Path) -> list[Path]:
    """Les fichiers CSV du dossier que git a laissés en conflit."""
    if not directory.is_dir():
        return []
    return sorted(
        path
        for path in directory.glob("*.csv")
        if has_conflict(path.read_text(encoding="utf-8", errors="replace"))
    )
