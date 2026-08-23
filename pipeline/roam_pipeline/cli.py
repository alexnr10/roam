"""Interface en ligne de commande du pipeline de curation."""

from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
from collections import Counter, defaultdict
from pathlib import Path

from . import wikidata as wd
from .collections import build_all
from .config import CONFIG_DIR, Config, load_config
from .export import (
    read_review_csv,
    write_json,
    write_review_csv,
    write_app_catalog,
    write_review_html,
    write_seed_sql,
)
from .fetch import (
    enrich_article_sizes,
    enrich_departements,
    enrich_flags,
    enrich_summaries,
    run_fetch,
)
from .models import Collection, CollectionPlace, Place
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

    pending = _pending_terms(config)
    if pending:
        print("\nEn attente de résolution :")
        for owner, term in pending:
            print(f"  ? {term:<38} ({owner})")

    print(f"\n{len(qids)} Q-ids vérifiés, {problems} introuvable(s), "
          f"{len(pending)} terme(s) à résoudre.")
    if problems or pending:
        print("Lance `python -m roam_pipeline suggest-qids` pour trouver les bons Q-ids.")
    return 1 if problems else 0


def _pending_terms(config: Config) -> list[tuple[str, str]]:
    """Termes déclarés dans la configuration mais pas encore résolus en Q-id."""
    pending: list[tuple[str, str]] = []
    for theme in config.themes:
        for term in theme.search:
            pending.append((f"thème {theme.id}", term))
    for label in config.labels:
        if not label.is_manual and not label.qid and label.search:
            pending.append((f"label {label.id}", label.search))
    return pending


def cmd_suggest_qids(args: argparse.Namespace, config: Config) -> int:
    """Propose des Q-ids pour chaque terme en attente.

    Écrire un Q-id de mémoire ne marche pas : une erreur ne lève aucune
    exception, elle fait rater un thème en silence. On part donc toujours du
    libellé, et on choisit parmi ce que Wikidata renvoie réellement.
    """
    terms = [("recherche", term) for term in args.terms] or _pending_terms(config)
    if not terms:
        print("Aucun terme en attente : la configuration est complète.")
        return 0

    client = wd.SparqlClient()
    for owner, term in terms:
        print(f"\n« {term} »  →  {owner}")
        try:
            hits = client.search(term, limit=args.limit)
        except Exception as exc:
            print(f"    recherche impossible : {exc}")
            continue
        if not hits:
            print("    aucun résultat")
            continue
        for hit in hits:
            description = (hit["description"] or "")[:62]
            print(f"    {hit['id']:<11} {hit['label']:<34} {description}")

    print(
        "\nColle cette sortie dans la conversation : le choix entre deux entités "
        "proches (« château » et « château fort », par exemple) est une décision "
        "éditoriale, pas une correspondance automatique."
    )
    return 0


def cmd_fetch(args: argparse.Namespace, config: Config) -> int:
    client = wd.SparqlClient(min_interval_s=args.min_interval)
    places = run_fetch(client, config, args.out, args.manual, only=args.only or None)
    print(f"{len(places)} lieux candidats collectés → {args.out / 'places_raw.json'}")
    return 0


def cmd_enrich(args: argparse.Namespace, config: Config) -> int:
    """Ajoute la taille de l'article francophone aux candidats déjà collectés.

    Travaille sur `places_raw.json` : ajouter ce signal ne demande pas de
    repasser une demi-heure sur Wikidata.
    """
    raw_path = args.out / "places_raw.json"
    if not raw_path.exists():
        print(f"{raw_path} absent — lance d'abord `fetch`.", file=sys.stderr)
        return 1

    places = _load_places(raw_path)
    found = enrich_article_sizes(places)
    enrich_flags(wd.SparqlClient(), places)
    enrich_departements(places)
    if not args.skip_summaries:
        enrich_summaries(places)
    raw_path.write_text(
        json.dumps([p.to_dict() for p in places], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"{found} tailles d'articles ajoutées → {raw_path}")
    print("Relance `build` pour en tenir compte dans le classement.")
    return 0


def cmd_discover(args: argparse.Namespace, config: Config) -> int:
    """Confronte le catalogue aux sites de visite d'OpenStreetMap.

    Répond aux deux questions que Wikidata ne sait pas trancher : ce lieu
    se visite-t-il, et que manque-t-il au catalogue.
    """
    from .discover import apply_visit_info, find_candidates, guess_theme, is_confident
    from .overpass import OverpassClient, cells

    raw_path = args.out / "places_raw.json"
    if not raw_path.exists():
        print(f"{raw_path} absent — lance d'abord `fetch`.", file=sys.stderr)
        return 1

    grid = list(cells())
    print(f"Interrogation d'OpenStreetMap : {len(grid)} cellules, compte ~{len(grid) // 4} min.")
    client = OverpassClient()
    osm = []
    for index, cell in enumerate(grid, start=1):
        found = client.fetch_cell(cell)
        osm.extend(found)
        LOG.info("cellule %s/%s : %s sites (%s au total)", index, len(grid), len(found), len(osm))

    if not osm:
        print("Aucun site récupéré — service indisponible ?", file=sys.stderr)
        return 1

    places = _load_places(raw_path)
    apply_visit_info(places, osm)
    raw_path.write_text(
        json.dumps([p.to_dict() for p in places], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    candidates = find_candidates(places, osm)
    confident = [site for site in candidates if is_confident(site)]
    retained = candidates if args.all else confident
    out_path = args.out / "candidates.csv"
    with out_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        # Les trois premières colonnes se recopient telles quelles dans
        # data/manual/places.csv ; les suivantes servent à décider.
        writer.writerow(
            ["wikidata_id", "theme_id", "note", "nom", "osm_id",
             "horaires", "tarif", "site_web", "lat", "lon"]
        )
        for site in retained[: args.limit]:
            writer.writerow([
                site.wikidata_id or "",
                guess_theme(site.tags) or "",
                site.name,
                site.name,
                site.osm_id,
                site.opening_hours or "",
                site.fee or "",
                site.website or "",
                f"{site.lat:.6f}",
                f"{site.lon:.6f}",
            ])

    ready = sum(1 for s in retained[: args.limit] if s.wikidata_id)
    print(f"\n{len(osm)} sites lus sur OpenStreetMap.")
    print(f"{len(candidates)} absents du catalogue, dont {len(confident)} avec un signe "
          f"d'accueil du public ET un lien encyclopédique.")
    print(f"{min(len(retained), args.limit)} écrits dans {out_path}, "
          f"dont {ready} directement recopiables dans data/manual/places.csv.")
    if not args.all and len(candidates) > len(confident):
        print(f"Ajoute --all pour voir les {len(candidates) - len(confident)} autres.")
    print("Relance `build` pour tenir compte de l'ouverture au public.")
    return 0


def cmd_build(args: argparse.Namespace, config: Config) -> int:
    raw_path = args.out / "places_raw.json"
    if not raw_path.exists():
        print(f"{raw_path} absent — lance d'abord `fetch`.", file=sys.stderr)
        return 1

    scored = score_all(_load_places(raw_path), config)
    retained, collections = build_all(scored, config)

    write_json(retained, collections, args.out)
    write_review_csv(retained, collections, args.out / "review.csv", config)
    write_review_html(retained, collections, config, args.out / "review.html")
    write_seed_sql(retained, collections, config, args.out / "seed.sql")
    # La distribution porte sur les candidats BRUTS : calculée sur les lieux
    # déjà filtrés, elle répéterait le même nombre sous le plancher courant et
    # ne permettrait pas de le régler.
    _print_stats(retained, collections, raw=scored)
    return 0


def cmd_apply_review(args: argparse.Namespace, config: Config) -> int:
    """Applique les décisions éditoriales et reconstruit les collections."""
    decisions = read_review_csv(args.review)
    if not decisions:
        print("Aucune décision renseignée dans la feuille de revue.", file=sys.stderr)
        return 1

    from .collections import apply_notoriety_floor

    # `scored` garde TOUS les candidats : c'est lui qui alimente la distribution,
    # qui ne sert à régler le plancher que si elle porte sur l'avant-filtre.
    scored = score_all(_load_places(args.out / "places_raw.json"), config)
    places = apply_notoriety_floor(scored, config)
    kept: list[Place] = []
    counts: Counter[str] = Counter()

    for place in places:
        decision, note = decisions.get(place.wikidata_id, ("", ""))
        counts[decision or "pending"] += 1
        if decision == "drop":
            continue
        if decision == "promote":
            place.curator_adjustment = args.adjust
        elif decision == "demote":
            place.curator_adjustment = -args.adjust
        if decision in ("", "pending") and args.strict:
            # En mode strict, seul ce qui a été explicitement relu est conservé.
            continue
        kept.append(place)

    # Rescoré après ajustement : la correction du relecteur fait partie du score,
    # elle n'est pas plaquée par-dessus.
    score_all(kept, config)
    retained, collections = build_all(kept, config)
    write_json(retained, collections, args.out)
    write_review_csv(retained, collections, args.out / "review.csv", config)
    write_review_html(retained, collections, config, args.out / "review.html")
    write_seed_sql(retained, collections, config, args.out / "seed.sql")

    print("Décisions :", ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    _print_stats(retained, collections, raw=scored)
    return 0


APP_CATALOG = BASE_DIR.parent / "mobile" / "src" / "data" / "catalog.json"


def cmd_export_app(args: argparse.Namespace, config: Config) -> int:
    """Remplace le catalogue de l'application par celui qui vient d'être construit."""
    places_path = args.out / "places.json"
    collections_path = args.out / "collections.json"
    if not places_path.exists():
        print(f"{places_path} absent — lance d'abord `build`.", file=sys.stderr)
        return 1

    places = _load_places(places_path)
    raw_collections = json.loads(collections_path.read_text(encoding="utf-8"))
    collections = [
        Collection(
            slug=c["slug"],
            name=c["name"],
            kind=c["kind"],
            theme_id=c.get("theme_id"),
            label_id=c.get("label_id"),
            geo_level=c.get("geo_level"),
            geo_code=c.get("geo_code"),
            places=[
                CollectionPlace(placeId["place_id"], placeId["tier"], placeId["rank"])
                for placeId in c["places"]
            ],
        )
        for c in raw_collections
    ]

    write_app_catalog(places, collections, config, args.to)
    print(f"Catalogue écrit dans {args.to}")
    print("Relance l'application : elle le lira au prochain démarrage.")
    return 0


def cmd_review(args: argparse.Namespace, config: Config) -> int:
    """Sert la page de revue en local et l'ouvre.

    Passer par un serveur plutôt que par un double-clic n'est pas un détail :
    ouverte en `file://`, la page ne peut pas mémoriser les décisions, et un
    travail de plusieurs soirées se perdrait à la première fermeture d'onglet.
    """
    import functools
    import http.server
    import threading
    import webbrowser

    page = args.out / "review.html"
    if not page.exists():
        print(f"{page} absent — lance d'abord `build`.", file=sys.stderr)
        return 1

    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler, directory=str(args.out)
    )
    server = http.server.ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    url = f"http://127.0.0.1:{args.port}/review.html"

    print(f"Revue ouverte sur {url}")
    print("Les décisions sont mémorisées dans le navigateur.")
    print("Ctrl+C pour arrêter, après avoir téléchargé le fichier de décisions.")
    threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nArrêté.")
    finally:
        server.server_close()
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


def _print_stats(places, collections, raw=None) -> None:
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

    ouverts = sum(1 for p in places if getattr(p, "visitable", None))
    rapproches = sum(1 for p in places if getattr(p, "osm_id", None))
    if rapproches:
        print(
            f"  Ouverture au public  : {ouverts} ouverts, "
            f"{rapproches - ouverts} sans signe, "
            f"{len(places) - rapproches} inconnus"
        )

    _print_sitelink_distribution(raw if raw is not None else places, config_floors())
    print()


def config_floors() -> dict[str, int]:
    """Plancher éditorial courant de chaque thème, pour repérer la colonne active."""
    from .config import load_config

    try:
        return {theme.id: theme.min_sitelinks for theme in load_config().themes}
    except Exception:
        return {}


SITELINK_STEPS = (2, 4, 6, 8, 10, 15, 20, 30)


def _print_sitelink_distribution(places, floors: dict[str, int] | None = None) -> None:
    """Combien de lieux resteraient par thème selon le plancher de notoriété.

    C'est le tableau qui permet de régler `min_sitelinks` sur des chiffres réels
    plutôt qu'à l'estime : un thème qui garde 700 lieux à 4 langues et 90 à 10
    n'a pas le même problème qu'un thème qui passe de 40 à 35.
    """
    by_theme: dict[str, list[int]] = defaultdict(list)
    for place in places:
        theme_id = place.theme_id if hasattr(place, "theme_id") else place["theme_id"]
        sitelinks = place.sitelinks if hasattr(place, "sitelinks") else place["sitelinks"]
        by_theme[theme_id].append(int(sitelinks or 0))

    if not by_theme:
        return

    floors = floors or {}
    header = "  ".join(f"≥{step:<4}" for step in SITELINK_STEPS)
    print("\n  Candidats bruts restants selon le plancher de notoriété :")
    print(f"      {'thème':<16} {header}  (× = plancher actuel)")
    for theme_id in sorted(by_theme, key=lambda t: -len(by_theme[t])):
        counts = by_theme[theme_id]
        floor = floors.get(theme_id)
        cells = []
        for step in SITELINK_STEPS:
            n = sum(1 for c in counts if c >= step)
            # Marque la colonne qui correspond au réglage en vigueur.
            active = floor is not None and step <= floor < (
                SITELINK_STEPS[SITELINK_STEPS.index(step) + 1]
                if step != SITELINK_STEPS[-1]
                else 10**9
            )
            cells.append(f"{n}{'×' if active else ' '}".ljust(7))
        print(f"      {theme_id:<16} {''.join(cells)}")


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

    suggest = sub.add_parser(
        "suggest-qids", help="propose des Q-ids pour les termes en attente (réseau requis)"
    )
    suggest.add_argument("terms", nargs="*", help="termes à chercher (défaut : ceux de la config)")
    suggest.add_argument("--limit", type=int, default=6, help="candidats par terme")

    fetch = sub.add_parser("fetch", help="collecte les lieux candidats depuis Wikidata")
    fetch.add_argument(
        "--min-interval", type=float, default=1.5, help="délai minimum entre deux requêtes (s)"
    )
    fetch.add_argument(
        "--only",
        nargs="+",
        metavar="THÈME",
        help="ne recollecter que ces thèmes ; les autres sont conservés",
    )

    enrich = sub.add_parser(
        "enrich",
        help="complète tailles d'articles, descriptions, signaux et départements",
    )
    enrich.add_argument(
        "--skip-summaries",
        action="store_true",
        help="ne pas récupérer les descriptions (la passe la plus longue)",
    )

    discover = sub.add_parser(
        "discover",
        help="confronte le catalogue aux sites de visite d'OpenStreetMap (réseau requis)",
    )
    discover.add_argument(
        "--limit", type=int, default=1500, help="nombre maximum de candidats écrits"
    )
    discover.add_argument(
        "--all",
        action="store_true",
        help="inclure les candidats moins sûrs (sans lien encyclopédique)",
    )

    sub.add_parser("build", help="score, construit les collections et exporte")

    review = sub.add_parser("apply-review", help="applique les décisions de la feuille de revue")
    review.add_argument("--review", type=Path, help="chemin de review.csv")
    review.add_argument(
        "--adjust",
        type=float,
        default=60.0,
        # Doit dépasser le plus gros bonus de label (UNESCO, 40 points) : sans
        # cela, une décision humaine ne pourrait pas rattraper un lieu que
        # Wikidata documente mal.
        help="ajustement de score pour promote/demote",
    )
    review.add_argument(
        "--strict",
        action="store_true",
        help="ne garder que les lieux explicitement relus",
    )

    sub.add_parser("stats", help="statistiques du catalogue construit")

    app = sub.add_parser("export-app", help="écrit le catalogue dans l'application")
    app.add_argument("--to", type=Path, default=APP_CATALOG, help="fichier de destination")

    serve = sub.add_parser("review", help="ouvre la page de revue dans le navigateur")
    serve.add_argument("--port", type=int, default=8765)
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
        "suggest-qids": cmd_suggest_qids,
        "fetch": cmd_fetch,
        "enrich": cmd_enrich,
        "discover": cmd_discover,
        "build": cmd_build,
        "apply-review": cmd_apply_review,
        "stats": cmd_stats,
        "review": cmd_review,
        "export-app": cmd_export_app,
    }
    return handlers[args.command](args, config)
