"""Interface en ligne de commande du pipeline de curation."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import Counter
from pathlib import Path

from . import wikidata as wd
from .collections import build_all
from .config import CONFIG_DIR, Config, load_config
from .export import read_review_csv, write_json, write_review_csv, write_seed_sql
from .fetch import run_fetch
from .models import Place
from .score import score_all

LOG = logging.getLogger("roam")

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_OUT = BASE_DIR / "data" / "out"
DEFAULT_MANUAL = BASE_DIR / "data" / "manual"


def _load_places(path: Path) -> list[Place]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    places = []
    for item in raw:
        item.pop("slug", None)
        places.append(Place(**item))
    return places


def cmd_verify_qids(args: argparse.Namespace, config: Config) -> int:
    """Affiche le libellé réel de chaque Q-id de la configuration.

    À lancer avant toute première collecte : un Q-id erroné ne provoque pas
    d'erreur, il renvoie simplement zéro résultat — c'est le bug le plus
    silencieux et le plus coûteux du pipeline.
    """
    qids: dict[str, list[str]] = {}
    for theme in config.themes:
        for qid in theme.wikidata_classes:
            qids.setdefault(qid, []).append(f"thème {theme.id}")
    for label in config.labels:
        if label.qid:
            qids.setdefault(label.qid, []).append(f"label {label.id}")

    client = wd.SparqlClient()
    resolved: dict[str, tuple[str, str]] = {}
    for batch in wd.chunked(sorted(qids), 40):
        for row in client.query(wd.entity_labels_query(batch)):
            qid = wd.qid_from_uri(row.get("item"))
            if qid:
                resolved[qid] = (row.get("itemLabel", ""), row.get("itemDescription", ""))

    problems = 0
    for qid in sorted(qids, key=lambda q: int(q[1:])):
        label, description = resolved.get(qid, ("", ""))
        used_by = ", ".join(qids[qid])
        if not label or label == qid:
            problems += 1
            print(f"  ✗ {qid:<12} INTROUVABLE            ({used_by})")
        else:
            print(f"  · {qid:<12} {label:<38} {description[:60]:<60} ({used_by})")

    print(f"\n{len(qids)} Q-ids, {problems} introuvable(s).")
    if problems:
        print("Corrige-les dans pipeline/config/ avant de lancer la collecte.")
    return 1 if problems else 0


def cmd_fetch(args: argparse.Namespace, config: Config) -> int:
    client = wd.SparqlClient(min_interval_s=args.min_interval)
    places = run_fetch(client, config, args.out, args.manual)
    print(f"{len(places)} lieux candidats collectés → {args.out / 'places_raw.json'}")
    return 0


def cmd_build(args: argparse.Namespace, config: Config) -> int:
    raw_path = args.out / "places_raw.json"
    if not raw_path.exists():
        print(f"{raw_path} absent — lance d'abord `fetch`.", file=sys.stderr)
        return 1

    places = score_all(_load_places(raw_path), config)
    retained, collections = build_all(places, config)

    write_json(retained, collections, args.out)
    write_review_csv(retained, collections, args.out / "review.csv")
    write_seed_sql(retained, collections, config, args.out / "seed.sql")
    _print_stats(retained, collections)
    return 0


def cmd_apply_review(args: argparse.Namespace, config: Config) -> int:
    """Applique les décisions éditoriales et reconstruit les collections."""
    decisions = read_review_csv(args.review)
    if not decisions:
        print("Aucune décision renseignée dans la feuille de revue.", file=sys.stderr)
        return 1

    places = score_all(_load_places(args.out / "places_raw.json"), config)
    kept: list[Place] = []
    counts: Counter[str] = Counter()

    for place in places:
        decision, note = decisions.get(place.wikidata_id, ("", ""))
        counts[decision or "pending"] += 1
        if decision == "drop":
            continue
        if decision == "promote":
            place.score += args.adjust
        elif decision == "demote":
            place.score -= args.adjust
        if decision in ("", "pending") and args.strict:
            # En mode strict, seul ce qui a été explicitement relu est conservé.
            continue
        kept.append(place)

    retained, collections = build_all(kept, config)
    write_json(retained, collections, args.out)
    write_seed_sql(retained, collections, config, args.out / "seed.sql")

    print("Décisions :", ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    _print_stats(retained, collections)
    return 0


def cmd_stats(args: argparse.Namespace, config: Config) -> int:
    places_path = args.out / "places.json"
    if not places_path.exists():
        print(f"{places_path} absent — lance d'abord `build`.", file=sys.stderr)
        return 1
    places = _load_places(places_path)
    collections = json.loads((args.out / "collections.json").read_text(encoding="utf-8"))
    _print_stats(places, collections)
    return 0


def _print_stats(places, collections) -> None:
    def count(collection) -> int:
        return collection["place_count"] if isinstance(collection, dict) else len(collection.places)

    def kind(collection) -> str:
        return collection["kind"] if isinstance(collection, dict) else collection.kind

    by_kind = Counter(kind(c) for c in collections)
    sizes = sorted(count(c) for c in collections)

    print(f"\n  Lieux retenus        : {len(places)}")
    print(f"  Collections          : {len(collections)}")
    for k, n in sorted(by_kind.items()):
        print(f"      {k:<16} : {n}")
    if sizes:
        median = sizes[len(sizes) // 2]
        print(f"  Taille de collection : min {sizes[0]}, médiane {median}, max {sizes[-1]}")

    themes = Counter(
        p.theme_id if hasattr(p, "theme_id") else p["theme_id"] for p in places
    )
    print("  Lieux par thème      :")
    for theme_id, n in themes.most_common():
        print(f"      {theme_id:<16} : {n}")
    print()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="roam_pipeline",
        description="Pipeline de curation du catalogue Roam. Propose et classe ; ne publie pas.",
    )
    parser.add_argument("--config", type=Path, default=CONFIG_DIR, help="dossier de configuration")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="dossier de sortie")
    parser.add_argument("--manual", type=Path, default=DEFAULT_MANUAL, help="listes manuelles")
    parser.add_argument("-v", "--verbose", action="store_true")

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("verify-qids", help="vérifie les Q-ids de la configuration (réseau requis)")

    fetch = sub.add_parser("fetch", help="collecte les lieux candidats depuis Wikidata")
    fetch.add_argument(
        "--min-interval", type=float, default=1.5, help="délai minimum entre deux requêtes (s)"
    )

    sub.add_parser("build", help="score, construit les collections et exporte")

    review = sub.add_parser("apply-review", help="applique les décisions de la feuille de revue")
    review.add_argument("--review", type=Path, help="chemin de review.csv")
    review.add_argument(
        "--adjust", type=float, default=15.0, help="ajustement de score pour promote/demote"
    )
    review.add_argument(
        "--strict",
        action="store_true",
        help="ne garder que les lieux explicitement relus",
    )

    sub.add_parser("stats", help="statistiques du catalogue construit")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)-7s %(message)s",
    )
    if getattr(args, "review", None) is None and args.command == "apply-review":
        args.review = args.out / "review.csv"

    config = load_config(args.config)
    handlers = {
        "verify-qids": cmd_verify_qids,
        "fetch": cmd_fetch,
        "build": cmd_build,
        "apply-review": cmd_apply_review,
        "stats": cmd_stats,
    }
    return handlers[args.command](args, config)
