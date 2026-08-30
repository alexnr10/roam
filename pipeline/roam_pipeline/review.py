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
import re
import unicodedata
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


# ---------------------------------------------------------------------------
# Rattachement au thème
# ---------------------------------------------------------------------------

THEMES_HEADER = """# Thème choisi par le curateur, quand le rattachement automatique se trompe.
#
# Le pipeline range un lieu d'après ses classes Wikidata. C'est juste la plupart
# du temps et faux parfois : le musée Christian-Dior est classé « jardin » parce
# que sa villa en a un remarquable, et se retrouvait donc parmi les jardins.
# Aucune règle générale ne rattrape cela — Wikidata dit vrai, c'est la
# hiérarchie des classes qui ne dit pas ce qu'on vient voir.
#
# Une ligne ici l'emporte sur tout : le lieu quitte ses autres rattachements et
# n'appartient plus qu'au thème indiqué.
#
# Ce n'est PAS un verdict d'inclusion. Un lieu redirigé doit encore franchir le
# plancher de notoriété de son nouveau thème ; `build` le dit s'il n'y arrive
# pas.
#
# Pour trouver un identifiant : python -m roam_pipeline explain "musée Dior"
#
wikidata_id,theme_id,note
"""


def read_themes(path: Path) -> dict[str, tuple[str, str]]:
    """`{qid: (thème choisi, note)}`. Fichier absent = aucun redressement."""
    themes: dict[str, tuple[str, str]] = {}
    if not path.exists():
        return themes

    lines = [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    for row in csv.DictReader(lines):
        qid = (row.get("wikidata_id") or "").strip()
        theme = (row.get("theme_id") or "").strip()
        if qid and theme:
            themes[qid] = (theme, (row.get("note") or "").strip())
    return themes


def write_themes(path: Path, themes: dict[str, tuple[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        fh.write(THEMES_HEADER)
        writer = csv.writer(fh)
        for qid in sorted(themes):
            theme, note = themes[qid]
            writer.writerow([qid, theme, note])
    LOG.info("thèmes : %s redressements conservés dans %s", len(themes), path)


def apply_themes(
    places: list[Place], themes: dict[str, tuple[str, str]], known: set[str]
) -> tuple[list[Place], list[str]]:
    """Rattache un lieu au thème choisi par le curateur.

    Renvoie le catalogue redressé et les Q-id qu'il n'a pas pu redresser.

    Un lieu peut être collecté sous plusieurs thèmes : le Louvre est un palais
    et un musée. Redresser ne consiste donc pas à changer une étiquette mais à
    **supprimer les autres rattachements** — sinon la règle du plus spécifique
    continuerait de trancher toute seule et la décision humaine n'aurait aucun
    effet.
    """
    if not themes:
        return places, []

    redressed: dict[str, Place] = {}
    reste: list[Place] = []
    inconnus = sorted(qid for qid, (theme, _) in themes.items() if theme not in known)

    for place in places:
        cible = themes.get(place.wikidata_id)
        if cible is None or cible[0] not in known:
            reste.append(place)
            continue
        # Le premier rencontré fait foi : les doublons inter-thèmes ne diffèrent
        # que par le rattachement, qu'on est précisément en train de remplacer.
        if place.wikidata_id in redressed:
            continue
        place.theme_id = cible[0]
        # Une décision humaine est le rattachement le plus spécifique qui soit :
        # elle ne doit pas céder devant une entrée « par classe précise ».
        place.via_broad_class = False
        redressed[place.wikidata_id] = place

    return reste + list(redressed.values()), inconnus


def name_hints(config) -> dict[str, str]:
    """`{mot: thème}` — les mots qui, en tête d'un nom, ne désignent qu'un thème.

    Un mot revendiqué par deux thèmes ne prouve rien et n'est pas retenu.
    """
    owners: dict[str, set[str]] = {}
    for theme in config.themes:
        mots = theme.name_hints or [theme.name_singular]
        for mot in mots:
            owners.setdefault(_fold(mot), set()).add(theme.id)
    return {mot: next(iter(ids)) for mot, ids in owners.items() if len(ids) == 1}


# Articles et qualificatifs : « Le Mont-Saint-Michel » commence par « le », et
# c'est le mot suivant qui porte le type du lieu.
_ARTICLES = {"le", "la", "les", "l", "du", "de", "des", "d", "un", "une", "grand",
             "grande", "petit", "petite", "vieux", "vieille", "ancien", "ancienne"}


def _fold(value: str) -> str:
    """Minuscules sans accents : « Île » et « ile » doivent se rencontrer."""
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower()


def theme_from_name(name: str, hints: dict[str, str]) -> str | None:
    """Le thème que le NOM du lieu annonce, s'il en annonce un.

    Le nom français d'un lieu commence par son type — « Musée Christian-Dior »,
    « Abbaye Saint-Victor », « Pont de Normandie ». C'est le seul signal que
    Wikidata ne donne pas : quand la classe décrit une PARTIE du lieu (le jardin
    remarquable de la villa), le nom, lui, dit ce qu'on vient voir.

    Un indice, pas un verdict : il sert à attirer l'œil du relecteur, jamais à
    ranger tout seul. « Maison Carrée » est un temple romain.
    """
    for mot in re.split(r"[^\w]+", _fold(name)):
        if not mot or mot in _ARTICLES:
            continue
        return hints.get(mot)
    return None


def theme_claims(places: list[Place]) -> dict[str, list[str]]:
    """`{qid: thèmes qui ont réclamé ce lieu}`, avant tout arbitrage.

    À calculer sur le catalogue BRUT : après `dedupe_across_themes`, le lieu n'a
    plus qu'un thème et la contestation a disparu sans laisser de trace. Or
    c'est exactement là qu'un relecteur doit regarder — le Louvre réclamé par
    « musées » et « châteaux », c'est un arbitrage, pas un fait.
    """
    claims: dict[str, set[str]] = {}
    for place in places:
        claims.setdefault(place.wikidata_id, set()).add(place.theme_id)
    return {qid: sorted(themes) for qid, themes in claims.items() if len(themes) > 1}


# ---------------------------------------------------------------------------
# Photographie des niveaux
# ---------------------------------------------------------------------------

SNAPSHOT_HEADER = """# Niveau de chaque lieu tel que le curateur l'a vu à sa dernière revue.
#
# Le niveau d'un lieu n'est pas une propriété du lieu : c'est son rang dans sa
# collection. Ajouter un signal au score, ou seulement collecter dix lieux de
# plus, peut donc faire descendre un lieu qu'on avait validé — sans que rien ne
# le dise.
#
# Ce fichier est la photographie du dernier état VU. `build` compare et signale
# les écarts ; `apply-review` la met à jour, parce que c'est le moment où le
# curateur a regardé.
#
wikidata_id,tier,theme,name
"""


def read_snapshot(path: Path) -> dict[str, tuple[int, str]]:
    """`{qid: (niveau, thème)}` du dernier état relu.

    Le thème compte autant que le niveau : un lieu qui change de thème change
    de collection, de voisins et de sens. Le Petit Palais classé en « maison
    d'artiste » puis rendu aux musées est un événement éditorial, pas un
    ajustement de rang.
    """
    snapshot: dict[str, tuple[int, str]] = {}
    if not path.exists():
        return snapshot
    lines = [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    for row in csv.DictReader(lines):
        qid = (row.get("wikidata_id") or "").strip()
        try:
            tier = int((row.get("tier") or "").strip())
        except ValueError:
            continue
        if qid:
            snapshot[qid] = (tier, (row.get("theme") or "").strip())
    return snapshot


def write_snapshot(
    path: Path, state: dict[str, tuple[int, str]], names: dict[str, str]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        fh.write(SNAPSHOT_HEADER)
        writer = csv.writer(fh)
        for qid in sorted(state):
            tier, theme = state[qid]
            writer.writerow([qid, tier, theme, names.get(qid, "")])
    LOG.info("niveaux : %s lieux photographiés dans %s", len(state), path)


def diff_tiers(
    previous: dict[str, tuple[int, str]], current: dict[str, tuple[int, str]]
) -> dict[str, str]:
    """Ce qui a bougé depuis la dernière revue, par lieu.

    Quatre verdicts. `theme` d'abord, parce qu'il prime : changer de thème,
    c'est changer de collection, de voisins et de sens — un lieu validé comme
    maison d'artiste et rendu aux musées doit être revu comme musée, quel que
    soit le rang qu'il y prend. Puis `monte`, `descend`, `nouveau`.

    Un lieu sorti du catalogue n'y figure pas : il n'est plus là pour être
    relu, et `build` le compte à part.

    Sans photographie précédente, on ne renvoie RIEN — tout signaler comme
    nouveau au premier passage noierait le signal le jour où il compte.
    """
    if not previous:
        return {}
    changes: dict[str, str] = {}
    for qid, (tier, theme) in current.items():
        before = previous.get(qid)
        if before is None:
            changes[qid] = "nouveau"
            continue
        tier_avant, theme_avant = before
        if theme_avant and theme != theme_avant:
            changes[qid] = "theme"
        elif tier < tier_avant:
            changes[qid] = "monte"
        elif tier > tier_avant:
            changes[qid] = "descend"
    return changes


def vanished(previous: dict, current: dict) -> list[str]:
    """Lieux relus qui ne sont plus au catalogue."""
    return sorted(set(previous) - set(current))
