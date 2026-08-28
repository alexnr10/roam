"""Interface en ligne de commande du pipeline de curation."""

from __future__ import annotations

import argparse
import csv
import json
import logging
import math
import sys
import unicodedata
from collections import Counter, defaultdict
from typing import Any
from pathlib import Path

from . import wikidata as wd
from .collections import build_all
from .config import CONFIG_DIR, Config, load_config
from .export import (
    review_state,
    review_tiers,
    read_review_csv,
    write_json,
    write_review_csv,
    write_app_catalog,
    write_review_html,
    write_seed_sql,
)
from .fetch import (
    REMEDIES,
    _paged,
    diagnose_missing,
    enrich_exclusions,
    enrich_visitors,
    enrich_article_sizes,
    enrich_communes,
    enrich_departements,
    enrich_flags,
    enrich_summaries,
    fetch_listed_places,
    read_csv_rows,
    read_place_list,
    resolve_admin,
    run_fetch,
)
from .models import Collection, CollectionPlace, Place
from .outlines import ATTRIBUTION as OUTLINE_ATTRIBUTION, DEFAULT_TOLERANCE_KM2
from .outlines import export as export_outlines
from .review import (
    DECISIONS, apply_decisions, apply_names, diff_tiers, read_decisions, read_names,
    read_snapshot, vanished, write_decisions, write_names, write_snapshot,
)
from .score import score_all

LOG = logging.getLogger("roam")

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_OUT = BASE_DIR / "data" / "out"
DEFAULT_MANUAL = BASE_DIR / "data" / "manual"


def _fold(text: str) -> str:
    """Minuscules sans accents, pour chercher « herouville » et trouver « Hérouville »."""
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return plain.lower()


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
        for broad in theme.broad_classes:
            qids.setdefault(broad.qid, []).append(
                f"thème {theme.id}, classe générique ≥ {broad.fetch_min_sitelinks}"
            )
            for qid in broad.exceptions:
                qids.setdefault(qid, []).append(f"thème {theme.id}, exception")
    for label in config.labels:
        if label.qid:
            qids.setdefault(label.qid, []).append(f"label {label.id}")
    for qid in config.exclusions.qids:
        qids.setdefault(qid, []).append("exclusion")
    if config.visitors.property_id:
        qids.setdefault(config.visitors.property_id, []).append("fréquentation")

    client = wd.SparqlClient()
    resolved: dict[str, tuple[str, str]] = {}
    for batch in wd.chunked(sorted(qids), 40):
        for row in client.query(wd.entity_labels_query(batch)):
            qid = wd.qid_from_uri(row.get("item"))
            if qid:
                resolved[qid] = (row.get("itemLabel", ""), row.get("itemDescription", ""))

    problems = 0
    for qid in sorted(qids, key=lambda q: (q[0], int(q[1:]))):
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
        for owner, term, kind in pending:
            marque = "propriété" if kind == "property" else "entité"
            print(f"  ? {term:<38} ({owner}, {marque})")

    print(f"\n{len(qids)} Q-ids vérifiés, {problems} introuvable(s), "
          f"{len(pending)} terme(s) à résoudre.")
    if problems or pending:
        print("Lance `python -m roam_pipeline suggest-qids` pour trouver les bons Q-ids.")
    return 1 if problems else 0


def _pending_terms(config: Config) -> list[tuple[str, str, str]]:
    """Termes déclarés dans la configuration mais pas encore résolus.

    Le troisième champ dit ce qu'on cherche — une entité ou une propriété. Une
    propriété cherchée parmi les entités ne rend rien, en silence.
    """
    pending: list[tuple[str, str, str]] = []
    for theme in config.themes:
        for term in theme.search:
            pending.append((f"thème {theme.id}", term, "item"))
        for broad in theme.broad_classes:
            for term in broad.except_search:
                pending.append((f"thème {theme.id}, exception de {broad.qid}", term, "item"))
    for label in config.labels:
        if not label.is_manual and not label.qid and label.search:
            pending.append((f"label {label.id}", label.search, "item"))
    for term in config.exclusions.search:
        pending.append(("exclusion", term, "item"))
    if config.visitors.search and not config.visitors.property_id:
        pending.append(("fréquentation", config.visitors.search, "property"))
    return pending


def cmd_suggest_qids(args: argparse.Namespace, config: Config) -> int:
    """Propose des Q-ids pour chaque terme en attente.

    Écrire un Q-id de mémoire ne marche pas : une erreur ne lève aucune
    exception, elle fait rater un thème en silence. On part donc toujours du
    libellé, et on choisit parmi ce que Wikidata renvoie réellement.
    """
    kind = "property" if args.property else "item"
    terms = [("recherche", term, kind) for term in args.terms] or _pending_terms(config)
    if not terms:
        print("Aucun terme en attente : la configuration est complète.")
        return 0

    client = wd.SparqlClient()
    for owner, term, term_kind in terms:
        print(f"\n« {term} »  →  {owner}")
        try:
            hits = client.search(term, limit=args.limit, kind=term_kind)
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
    client = wd.SparqlClient()
    enrich_flags(client, places)
    # Les classes disqualifiantes se marquent ici et s'appliquent à la
    # construction : ajouter une classe à la liste ne demande donc pas de
    # recollecter, juste de rejouer `enrich` puis `build`.
    enrich_exclusions(client, places, config.exclusions.qids)
    enrich_visitors(client, places, config.visitors.property_id)
    enrich_departements(places)
    # Après le département : la commune fait autorité sur lui, et la corrige au
    # passage quand Wikidata l'avait mal rattaché.
    enrich_communes(places)
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
    from .discover import (
        apply_visit_info, find_candidates, guess_theme, is_confident, keep_in_france,
    )
    from .geocode import departements_for
    from .overpass import PROBE_CELL, OverpassClient, cells

    raw_path = args.out / "places_raw.json"
    if not raw_path.exists():
        print(f"{raw_path} absent — lance d'abord `fetch`.", file=sys.stderr)
        return 1

    client = OverpassClient()
    # Un aller-retour de contrôle avant d'en lancer quarante : la requête
    # délimite la France par une zone, et une zone qui ne se résout pas ne
    # provoque aucune erreur — elle renvoie simplement zéro objet, partout.
    if not client.fetch_cell(PROBE_CELL):
        print("Le contrôle sur le centre de Paris ne renvoie rien : la zone France "
              "n'a pas été résolue par Overpass. Collecte interrompue.", file=sys.stderr)
        return 1

    grid = list(cells())
    print(f"Interrogation d'OpenStreetMap : {len(grid)} cellules, compte ~{len(grid) // 4} min.")
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
    # Deuxième garde-fou, indépendant de la requête Overpass : le rectangle de
    # collecte déborde sur les pays voisins, et une zone mal résolue par un
    # miroir Overpass repeuplerait la feuille de musées bâlois ou milanais.
    candidates = keep_in_france(candidates, departements_for)
    confident = [site for site in candidates if is_confident(site)]
    retained = candidates if args.all else confident
    out_path = args.out / "candidates.csv"
    with out_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        # Les trois premières colonnes se recopient telles quelles dans
        # data/manual/places.csv ; les suivantes servent à décider.
        writer.writerow(
            ["wikidata_id", "theme_id", "note", "nom", "departement", "osm_id",
             "horaires", "tarif", "site_web", "lat", "lon"]
        )
        for site in retained[: args.limit]:
            writer.writerow([
                site.wikidata_id or "",
                guess_theme(site.tags) or "",
                site.name,
                site.name,
                site.departement or "",
                site.osm_id,
                site.opening_hours or "",
                site.fee or "",
                site.website or "",
                f"{site.lat:.6f}",
                f"{site.lon:.6f}",
            ])

    ready = sum(1 for s in retained[: args.limit] if s.wikidata_id)
    print(f"\n{len(osm)} sites lus sur OpenStreetMap.")
    print(f"{len(candidates)} en France et absents du catalogue, dont {len(confident)} avec un signe "
          f"d'accueil du public ET un lien encyclopédique.")
    print(f"{min(len(retained), args.limit)} écrits dans {out_path}, "
          f"dont {ready} directement recopiables dans data/manual/places.csv.")
    if not args.all and len(candidates) > len(confident):
        print(f"Ajoute --all pour voir les {len(candidates) - len(confident)} autres.")
    print("Relance `build` pour tenir compte de l'ouverture au public.")
    return 0


CANDIDATE_LIST_HEADER = """# Candidats adoptés depuis OpenStreetMap.
#
# Trouvés parce qu'un lieu porte des horaires ou un tarif — un fait de terrain
# — là où Wikidata ne le classait dans aucune des classes interrogées. Ils
# n'ont aucun privilège : ils sont scorés, soumis au plancher de notoriété et
# dédoublonnés comme les autres. Ce fichier existe pour que `fetch` les
# retrouve, et pour qu'une ligne retirée à la main le reste.
#
wikidata_id,theme_id,note
"""


def _write_candidate_list(path: Path, wanted: dict[str, str], names: dict[str, str]) -> None:
    """Réécrit `data/manual/candidates.csv`, un lieu par ligne, trié.

    Le nom n'est là que pour la lecture humaine : c'est le Q-id qui fait foi.
    Sans lui, retirer une ligne à la main demanderait d'aller vérifier sur
    Wikidata ce que « Q3578611 » désigne.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        fh.write(CANDIDATE_LIST_HEADER)
        writer = csv.writer(fh)
        for qid in sorted(wanted):
            writer.writerow([qid, wanted[qid], names.get(qid, "")])


def _apply_osm_signals(places: list[Place], candidates_path: Path) -> None:
    """Reporte sur les lieux adoptés ce qu'OpenStreetMap sait d'eux.

    Sans cela, un candidat arriverait dans la revue sans horaires et sans la
    mention « ouvert au public » — alors que c'est précisément l'accueil du
    public qui l'a fait sortir du lot. L'information est déjà dans la feuille
    de candidats : la reperdre en cours de route serait absurde.
    """
    by_qid = {
        (row.get("wikidata_id") or "").strip(): row
        for row in read_csv_rows(candidates_path)
        if (row.get("wikidata_id") or "").strip()
    }
    for place in places:
        row = by_qid.get(place.wikidata_id)
        if row is None:
            continue
        place.osm_id = (row.get("osm_id") or "").strip() or None
        place.opening_hours = (row.get("horaires") or "").strip() or None
        place.website = (row.get("site_web") or "").strip() or None
        # `discover` n'écrit que des sites gérés — horaires, tarif ou site web.
        # L'accueil du public est donc attesté par construction.
        place.visitable = True


def cmd_adopt(args: argparse.Namespace, config: Config) -> int:
    """Fait entrer les candidats d'OpenStreetMap dans le catalogue.

    `discover` produit une feuille de neuf cents lignes. Juger neuf cents noms
    dans un tableur n'est pas un travail éditorial : il manque la photo, le
    score, les langues de l'article, les voisins du même thème. Ces candidats
    doivent donc rejoindre le catalogue pour être jugés là où tout le reste
    l'est déjà — dans la page de revue.

    Les faire entrer n'est pas les accepter. Ils ne sont pas épinglés : le
    plancher de notoriété en écartera une bonne part sans qu'on ait à les lire,
    et ceux qui restent porteront la mention de leur origine.
    """
    candidates_path = args.candidates or (args.out / "candidates.csv")
    if not candidates_path.exists():
        print(f"{candidates_path} absent — lance d'abord `discover`.", file=sys.stderr)
        return 1

    raw_path = args.out / "places_raw.json"
    if not raw_path.exists():
        print(f"{raw_path} absent — lance d'abord `fetch`.", file=sys.stderr)
        return 1

    proposed = read_place_list(config, candidates_path)
    if not proposed:
        print("Aucun candidat exploitable : il faut un wikidata_id ET un theme_id.",
              file=sys.stderr)
        return 1

    list_path = args.manual / "candidates.csv"
    already_listed = read_place_list(config, list_path)
    # La liste est cumulative et l'ancienne décision prime : une ligne retirée
    # ou dont le thème a été corrigé à la main ne doit pas être réécrite au
    # prochain passage.
    merged = dict(proposed)
    merged.update(already_listed)

    places = _load_places(raw_path)
    names = {place.wikidata_id: place.name for place in places}
    to_fetch = {qid: theme for qid, theme in merged.items() if qid not in names}

    print(f"{len(proposed)} candidats proposés, {len(merged)} au total dans {list_path.name}.")
    print(f"{len(merged) - len(to_fetch)} déjà au catalogue, {len(to_fetch)} à collecter.")
    if not to_fetch:
        _write_candidate_list(list_path, merged, names)
        print("Rien de nouveau. Relance `build` si besoin.")
        return 0

    client = wd.SparqlClient()
    adopted = fetch_listed_places(client, config, to_fetch, pinned=False, source="osm")
    if not adopted:
        print("Aucun candidat récupéré sur Wikidata.", file=sys.stderr)
        return 1

    # Les mêmes signaux que pour le reste du catalogue, sur les seuls nouveaux :
    # sans eux, ils arriveraient dans la revue sans photo, sans description et
    # sans département, donc injugeables.
    _apply_osm_signals(adopted, candidates_path)
    resolve_admin(client, adopted)
    enrich_flags(client, adopted)
    enrich_departements(adopted)
    enrich_article_sizes(adopted)
    if not args.skip_summaries:
        enrich_summaries(adopted)

    names.update({place.wikidata_id: place.name for place in adopted})
    _write_candidate_list(list_path, merged, names)

    places += adopted
    raw_path.write_text(
        json.dumps([p.to_dict() for p in places], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n{len(adopted)} lieux ajoutés à {raw_path.name} ({len(places)} en tout).")
    print("Ils ne sont pas épinglés : le plancher de notoriété s'y applique.")
    print("Lance `build` puis `review` — ils y porteront la mention « OpenStreetMap ».")
    return 0


def _build_and_write(args: argparse.Namespace, config: Config) -> int:
    """Score, applique les décisions du curateur, construit et exporte.

    Les décisions sont relues à CHAQUE construction. Elles vivaient jusqu'ici
    dans la seule mémoire de `apply-review` : un `build` suffisait à les
    perdre, et un lieu écarté revenait comme si de rien n'était.
    """
    raw_path = args.out / "places_raw.json"
    if not raw_path.exists():
        print(f"{raw_path} absent — lance d'abord `fetch`.", file=sys.stderr)
        return 1

    # `scored` garde TOUS les candidats : c'est lui qui alimente la distribution,
    # qui ne sert à régler le plancher que si elle porte sur l'avant-filtre.
    scored = score_all(_load_places(raw_path), config)
    # Avant tout le reste : le nom choisi par le curateur doit valoir partout,
    # jusque dans la feuille de revue où il relira la ligne.
    renamed = apply_names(scored, read_names(args.manual / "names.csv"))
    decisions = read_decisions(args.manual / "decisions.csv")
    kept, counts = apply_decisions(scored, decisions, args.adjust, strict=args.strict)
    # Rescoré après ajustement : la correction du relecteur fait partie du score,
    # elle n'est pas plaquée par-dessus.
    score_all(kept, config)

    retained, collections = build_all(kept, config)

    # Ce qui a bougé depuis la dernière revue. Le niveau d'un lieu n'est pas une
    # propriété du lieu : c'est son rang dans sa collection. Ajouter un signal
    # au score, ou seulement collecter dix lieux de plus, peut faire descendre
    # un lieu déjà validé — et rien ne le disait.
    snapshot_path = args.manual / "tiers.csv"
    before = read_snapshot(snapshot_path)
    current = review_state(retained, collections)
    changes = diff_tiers(before, current)
    gone = vanished(before, current)

    write_json(retained, collections, args.out)
    write_review_csv(retained, collections, args.out / "review.csv", config, changes)
    write_review_html(retained, collections, config, args.out / "review.html", changes)
    write_seed_sql(retained, collections, config, args.out / "seed.sql")

    _report_tier_changes(changes, gone, before, retained)

    if renamed:
        print(f"Renommages appliqués : {renamed}")

    if decisions:
        print("Décisions reprises :",
              ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    _print_stats(retained, collections, raw=scored, config=config)
    return 0


def _report_tier_changes(changes, gone, before, retained) -> None:
    """Dit ce qui a bougé, sans noyer ce qui compte.

    Un lieu qui MONTE n'a pas besoin d'être relu : il gagne en priorité, la
    décision prise reste valable. Un lieu qui DESCEND, si — c'est là qu'un
    incontournable validé se retrouve au fond de sa collection sans que
    personne ne l'ait décidé. Et un lieu qui CHANGE DE THÈME plus encore : il
    a changé de collection, de voisins et de sens, et la décision prise sur
    lui l'a été dans un autre contexte.
    """
    if not before:
        print("Aucune photographie des niveaux : elle sera prise au prochain "
              "`apply-review`, et les changements seront signalés ensuite.")
        return

    counts = Counter(changes.values())
    if not counts and not gone:
        print("Niveaux inchangés depuis la dernière revue.")
        return

    print("Depuis ta dernière revue : "
          + ", ".join(f"{n} {verdict}" for verdict, n in sorted(counts.items()))
          + (f", {len(gone)} sortis du catalogue" if gone else ""))

    names = {p.wikidata_id: p.name for p in retained}
    for verdict, titre in (("theme", "changé de thème"), ("descend", "descendus")):
        touches = [qid for qid, v in changes.items() if v == verdict]
        if touches:
            shown = sorted(names.get(q, q) for q in touches)[:10]
            print(f"  {titre:<16}: " + ", ".join(shown)
                  + (f" (+{len(touches) - 10})" if len(touches) > 10 else ""))
    if gone:
        print("  sortis    : " + ", ".join(gone[:10])
              + (f" (+{len(gone) - 10})" if len(gone) > 10 else ""))
    print("  `review` → filtre « ce qui a changé de niveau » pour les relire.")


def cmd_explain(args: argparse.Namespace, config: Config) -> int:
    """Pourquoi ce lieu est-il dans le catalogue, ou pourquoi n'y est-il pas ?

    La question revient à chaque revue — « je ne vois pas Giverny », « le
    château d'Hérouville est encore là » — et y répondre demandait jusqu'ici de
    relire le pipeline. Or chaque étape est un filtre nommé : il suffit de
    suivre un lieu à travers elles et de dire laquelle l'arrête.
    """
    from .collections import (
        apply_access_filter, apply_alpine_filter, apply_class_exclusion,
        apply_geographic_scope, apply_notoriety_floor, dedupe, dedupe_across_themes,
    )
    from .score import rescued

    raw_path = args.out / "places_raw.json"
    if not raw_path.exists():
        print(f"{raw_path} absent — lance d'abord `fetch`.", file=sys.stderr)
        return 1

    needle = _fold(args.name)
    everything = score_all(_load_places(raw_path), config)
    apply_names(everything, read_names(args.manual / "names.csv"))
    found = [p for p in everything if needle in _fold(p.name)]

    if not found:
        print(f"Aucun lieu dont le nom contient « {args.name} » n'a été collecté.\n")
        print("`explain` ne connaît que ce qui a été collecté : il ne peut pas dire")
        print("POURQUOI ce lieu n'est jamais entré. C'est le rôle de `probe`, qui")
        print("interroge Wikidata sans aucun filtre et nomme ce qui manque :")
        print(f"\n    python -m roam_pipeline probe \"{args.name}\"\n")
        return 0

    decisions = read_decisions(args.manual / "decisions.csv")
    # Chaque étape est rejouée sur le catalogue entier : suivre un lieu isolé
    # ne dirait rien du dédoublonnage, qui est une comparaison entre lieux.
    # Rejouer signifie aussi réémettre tous les journaux de construction, deux
    # fois — ils noieraient la réponse à une question qui tient en dix lignes.
    pipeline_log = logging.getLogger("roam_pipeline")
    previous_level = pipeline_log.level
    pipeline_log.setLevel(logging.ERROR)
    try:
        kept, _counts = apply_decisions(everything, decisions, args.adjust, strict=args.strict)
        score_all(kept, config)
        stages = [("décision du curateur", kept)]
        stages.append(("périmètre français", apply_geographic_scope(stages[-1][1], config)))
        stages.append(("thème unique", dedupe_across_themes(stages[-1][1], config)))
        stages.append(("classe écartée", apply_class_exclusion(stages[-1][1], config)))
        stages.append(("accès refusé", apply_access_filter(stages[-1][1], config)))
        stages.append(("accès alpin non prouvé", apply_alpine_filter(stages[-1][1], config)))
        stages.append(("plancher de notoriété", apply_notoriety_floor(stages[-1][1], config)))
        stages.append(("doublon de proximité", dedupe(stages[-1][1])))
        _retained, collections = build_all(kept, config)
    finally:
        pipeline_log.setLevel(previous_level)
    membership = defaultdict(list)
    for collection in collections:
        for cp in collection.places:
            membership[cp.place_id].append((collection.name, cp.tier))

    for place in sorted(found, key=lambda p: -p.score)[: args.limit]:
        floor = config.theme(place.theme_id).min_sitelinks
        decision = decisions.get(place.wikidata_id, ("aucune", ""))[0]
        print(f"\n{place.name}  ({place.wikidata_id})")
        print(f"  thème {place.theme_id} · {place.sitelinks} langues · score {place.score:.1f}")
        print(f"  origine {place.source}"
              + (f" · département {place.departement_code}" if place.departement_code else ""))
        print("  ouverture au public : "
              + {True: "confirmée", False: "refusée"}.get(place.visitable, "non renseignée")
              + (f" ({place.opening_hours})" if place.opening_hours else ""))
        print(f"  plancher du thème : {floor} langues"
              + (" — repêché malgré lui" if rescued(place, config) else ""))
        print(f"  décision enregistrée : {decision}")
        if place.excluded_class:
            print(f"  classe disqualifiante : {place.excluded_class}")
        if place.visitors_per_year:
            print(f"  fréquentation : {place.visitors_per_year:,} visiteurs par an"
                  .replace(",", " "))

        blocked = None
        for label, survivors in stages:
            if not any(p is place for p in survivors):
                blocked = label
                break
        if blocked:
            print(f"  → ÉCARTÉ à l'étape « {blocked} »")
            continue

        found_in = membership.get(place.wikidata_id, [])
        if not found_in:
            print("  → retenu par tous les filtres, mais dans AUCUNE collection")
            continue
        print(f"  → dans le catalogue, {len(found_in)} collections :")
        for name, tier in sorted(found_in, key=lambda x: x[1])[:6]:
            print(f"       niveau {tier} · {name}")

    if len(found) > args.limit:
        print(f"\n({len(found) - args.limit} autres correspondances non affichées)")
    return 0


def cmd_build(args: argparse.Namespace, config: Config) -> int:
    return _build_and_write(args, config)


def cmd_apply_review(args: argparse.Namespace, config: Config) -> int:
    """Enregistre les décisions d'une revue, puis reconstruit."""
    fresh = read_review_csv(args.review)
    unknown = {d for d, _ in fresh.values()} - set(DECISIONS)
    if unknown:
        print(f"Décisions inconnues, ignorées : {', '.join(sorted(unknown))}", file=sys.stderr)
        fresh = {q: v for q, v in fresh.items() if v[0] in DECISIONS}
    if not fresh:
        print("Aucune décision renseignée dans la feuille de revue.", file=sys.stderr)
        return 1

    path = args.manual / "decisions.csv"
    decisions = read_decisions(path)
    before = len(decisions)
    changed = sum(1 for qid, d in fresh.items() if decisions.get(qid, ("", ""))[0] != d[0])
    # La revue la plus récente l'emporte : revenir sur un verdict doit se faire
    # en relisant le lieu, pas en éditant un fichier.
    decisions.update(fresh)

    names = {p.wikidata_id: p.name for p in _load_places(args.out / "places_raw.json")}
    write_decisions(path, decisions, names)
    print(f"{len(fresh)} décisions lues, {changed} nouvelles ou modifiées "
          f"({before} → {len(decisions)} au total dans {path.name}).")

    status = _build_and_write(args, config)

    # La photographie se prend APRÈS la construction, et seulement ici : c'est
    # le moment où le curateur a vu l'état des niveaux et l'a accepté. La
    # prendre à chaque `build` effacerait le changement avant qu'il ne le lise.
    collections_path = args.out / "collections.json"
    if status == 0 and collections_path.exists():
        rebuilt = [
            Collection(
                slug=c["slug"], name=c["name"], kind=c["kind"],
                theme_id=c.get("theme_id"), label_id=c.get("label_id"),
                geo_level=c.get("geo_level"), geo_code=c.get("geo_code"),
                places=[CollectionPlace(m["place_id"], m["tier"], m["rank"])
                        for m in c["places"]],
            )
            for c in json.loads(collections_path.read_text(encoding="utf-8"))
        ]
        finales = _load_places(args.out / "places.json")
        write_snapshot(
            args.manual / "tiers.csv",
            review_state(finales, rebuilt),
            {p.wikidata_id: p.name for p in finales},
        )
        print("Décisions et niveaux enregistrés dans data/manual/ — "
              "pense à les committer, c'est ta seule copie.")
    return status


def _class_owners(config: Config) -> dict[str, tuple[str, int]]:
    """`{Q-id de classe: (thème, plancher de collecte DE CETTE CLASSE)}`.

    Le plancher appartient à la classe, pas au thème : `maisons` collecte ses
    maisons-musées à partir de deux langues, mais la classe générique
    « maison » à partir de huit. Confondre les deux fait dire à `probe` que
    rien ne s'oppose à un lieu que la requête écarte — c'est exactement ce qui
    est arrivé à la maison du docteur Gachet.

    Quand deux classes du même thème mènent au même lieu, la moins exigeante
    l'emporte : il suffit d'une route pour être collecté.
    """
    owners: dict[str, tuple[str, int]] = {}
    for theme in config.themes:
        for qid, floor in theme.collected_classes:
            known = owners.get(qid)
            if known is None or floor < known[1]:
                owners[qid] = (theme.id, floor)
    return owners


def cmd_probe(args: argparse.Namespace, config: Config) -> int:
    """Pourquoi ce lieu n'a-t-il JAMAIS été collecté ?

    `explain` répond pour ce que le pipeline connaît. Il est muet sur ce qui
    n'est jamais entré — or c'est le défaut le plus grave possible : un lieu
    emblématique absent ne se signale nulle part, et rien dans le catalogue ne
    dit qu'il manque.

    Cette commande interroge donc Wikidata SANS AUCUN FILTRE et rapporte ce qui
    manque : pas de pays, pas de coordonnées, une classe qu'aucun thème ne
    collecte, une notoriété sous le plancher de collecte.
    """
    client = wd.SparqlClient()

    qids = [t.strip() for t in args.terms if t.strip().startswith("Q") and t.strip()[1:].isdigit()]
    words = [t for t in args.terms if t.strip() not in qids]
    for term in words:
        print(f"Recherche « {term} »…")
        try:
            hits = client.search(term, limit=args.limit)
        except Exception as exc:
            print(f"    recherche impossible : {exc}", file=sys.stderr)
            continue
        for hit in hits:
            print(f"    {hit['id']:<11} {hit['label']:<36} {(hit['description'] or '')[:56]}")
            qids.append(hit["id"])
    if not qids:
        print("Aucune entité à sonder.", file=sys.stderr)
        return 1

    qids = list(dict.fromkeys(qids))
    rows = client.query(wd.probe_query(qids))

    # Une entité peut avoir plusieurs classes : une ligne par classe.
    facts: dict[str, dict[str, Any]] = {}
    for row in rows:
        qid = wd.qid_from_uri(row.get("item"))
        if not qid:
            continue
        entry = facts.setdefault(qid, {"classes": {}})
        entry.setdefault("label", row.get("itemLabel") or "")
        entry.setdefault("description", row.get("itemDescription") or "")
        entry.setdefault("country", row.get("countryLabel") or "")
        # Le Q-id plutôt que le libellé : c'est lui que `theme_query` compare,
        # et un libellé retombé en anglais ferait mentir le verdict.
        entry.setdefault("country_qid", wd.qid_from_uri(row.get("country")) or "")
        entry.setdefault("coord", row.get("coord") or "")
        entry.setdefault("sitelinks", int(row.get("sitelinks") or 0))
        entry.setdefault("frwiki", row.get("frwiki") or "")
        entry.setdefault("admin", row.get("adminLabel") or "")
        class_qid = wd.qid_from_uri(row.get("class"))
        if class_qid:
            entry["classes"][class_qid] = row.get("classLabel") or class_qid

    # De quelles classes CONFIGURÉES l'entité descend-elle ? La question n'est
    # pas « quelle est sa classe » mais « un thème la reconnaît-il », et la
    # réponse passe par la hiérarchie des sous-classes.
    owners = _class_owners(config)
    inherited: dict[str, list[tuple[str, str]]] = defaultdict(list)
    if owners:
        for row in client.query(wd.class_ancestry_query(qids, sorted(owners))):
            qid = wd.qid_from_uri(row.get("item"))
            ancestor = wd.qid_from_uri(row.get("class"))
            if qid and ancestor in owners:
                inherited[qid].append((ancestor, row.get("classLabel") or ancestor))

    collected = _known_qids(args.out / "places_raw.json")
    proposed = _known_qids(args.out / "candidates.csv")

    for qid in qids:
        entry = facts.get(qid)
        print()
        if not entry:
            print(f"{qid} : introuvable sur Wikidata.")
            continue

        print(f"{entry['label']}  ({qid})")
        if entry["description"]:
            print(f"  {entry['description']}")
        print(f"  pays : {entry['country'] or '— AUCUN —'}"
              + (f" · commune : {entry['admin']}" if entry["admin"] else ""))
        print(f"  coordonnées : {entry['coord'] or '— AUCUNE —'}")
        print(f"  langues : {entry['sitelinks']}"
              f" · article francophone : {'oui' if entry['frwiki'] else 'non'}")
        classes = ", ".join(f"{name} ({q})" for q, name in sorted(entry["classes"].items()))
        print(f"  classes déclarées : {classes or '— aucune —'}")

        # Une route = une classe qui mène à un thème, avec SON plancher.
        routes = sorted(
            {
                (owners[ancestor][0], label, owners[ancestor][1])
                for ancestor, label in inherited.get(qid, [])
            },
            key=lambda route: route[2],
        )
        if routes:
            print("  routes de collecte :")
            for theme_id, label, floor in routes:
                verdict = "✓" if entry["sitelinks"] >= floor else "✗"
                print(f"      {verdict} {theme_id:<12} via « {label} » — exige "
                      f"{floor} langues")
        else:
            print("  thème(s) qui la reconnaissent : AUCUN")

        print(f"  déjà collectée : {'oui' if qid in collected else 'NON'}"
              f" · proposée par OpenStreetMap : {'oui' if qid in proposed else 'non'}")

        for line in _probe_verdict(entry, routes, config, qid in collected):
            print(f"  {line}")

    return 0


def _known_qids(path: Path) -> set[str]:
    """Q-ids présents dans un fichier de sortie, quel que soit son format."""
    if not path.exists():
        return set()
    if path.suffix == ".json":
        return {row.get("wikidata_id", "") for row in json.loads(path.read_text(encoding="utf-8"))}
    return {
        (row.get("wikidata_id") or "").strip()
        for row in csv.DictReader(
            line
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        )
    }


def _probe_verdict(
    entry: dict[str, Any],
    routes: list[tuple[str, str, int]],
    config: Config,
    collected: bool,
) -> list[str]:
    """Ce qui empêche la collecte, et par quoi y remédier.

    Chaque condition correspond à une clause de `theme_query`. Une clause non
    remplie n'y produit aucune erreur : elle retire simplement l'entité du
    résultat, sans laisser de trace. C'est cette absence de trace qu'on répare
    ici.
    """
    manual = "  Remède : l'inscrire dans `data/manual/places.csv` — les lieux "
    out: list[str] = []

    if entry.get("country_qid") != wd.Q_FRANCE:
        out.append("⚠ pas de propriété « pays » = France : INVISIBLE à toutes les "
                   "requêtes de thème, qui l'exigent pour borner la collecte.")
        out.append(manual + "manuels échappent à toute la chaîne de collecte.")
        return out

    if not entry["coord"]:
        out.append("⚠ aucune coordonnée : un lieu sans point ne peut ni se placer "
                   "sur la carte ni se valider au GPS.")
        out.append(manual + "manuels portent alors leurs coordonnées à la main.")
        return out

    if not routes:
        out.append("⚠ aucune classe reconnue par un thème : la collecte ne peut pas "
                   "la voir. Ajouter l'une de ses classes à un thème de "
                   "`themes.yaml` la ramènerait — avec tout ce qui partage cette "
                   "classe, ce qui se vérifie avant.")
        out.append(manual + "manuels imposent leur thème.")
        return out

    # Il suffit d'une route pour être collecté : on regarde la moins exigeante.
    ouvertes = [route for route in routes if entry["sitelinks"] >= route[2]]
    if not ouvertes:
        theme_id, label, floor = routes[0]
        out.append(f"⚠ {entry['sitelinks']} langues, sous le plancher de COLLECTE "
                   f"de la classe « {label} » ({floor}) : la requête l'écarte avant "
                   f"même le catalogue.")
        out.append(f"  Le plancher appartient à la CLASSE, pas au thème — "
                   f"{theme_id} collecte ses classes propres plus bas. Remèdes : "
                   f"abaisser ce plancher dans `themes.yaml`, ou " + manual.strip() +
                   "manuels échappent à toute la chaîne de collecte.")
        return out

    themes = sorted({theme_id for theme_id, _label, _floor in ouvertes})
    if not collected:
        out.append("Rien ne s'y oppose côté Wikidata : elle devrait être collectée. "
                   "Relance `fetch --only " + ",".join(themes) + "`.")
        return out

    editorial = ", ".join(f"{t} ≥ {config.theme(t).min_sitelinks}" for t in themes)
    out.append(f"Collectée. Le sort se joue donc à la construction — plancher "
               f"éditorial {editorial} : `explain` le dira.")
    return out


def cmd_check_lists(args: argparse.Namespace, config: Config) -> int:
    """Que sont devenus les Q-ids des listes tenues à la main ?

    Les ajouts du curateur et les candidats adoptés sont désignés un par un.
    Quand l'un d'eux n'arrive pas dans `places_raw.json`, `fetch` le signale au
    passage — mais il faut une demi-heure de collecte pour revoir ce message.
    Ici, une seule requête bornée suffit, et elle se rejoue autant qu'on veut.
    """
    raw_path = args.out / "places_raw.json"
    if not raw_path.exists():
        print(f"{raw_path} absent — lance d'abord `fetch`.", file=sys.stderr)
        return 1

    collected = _known_qids(raw_path)
    listed: dict[str, str] = {}
    for name in ("places.csv", "candidates.csv"):
        path = args.manual / name
        for qid in read_place_list(config, path):
            listed.setdefault(qid, name)
    if not listed:
        print("Aucune liste manuelle à vérifier.")
        return 0

    missing = {qid for qid in listed if qid not in collected}
    print(f"{len(listed)} Q-ids listés, {len(listed) - len(missing)} collectés, "
          f"{len(missing)} sans résultat.")
    if not missing:
        return 0

    client = wd.SparqlClient()
    rows: list[dict[str, str]] = []
    for batch in wd.chunked(sorted(missing), 150):
        rows.extend(client.query(wd.probe_query(batch)))

    for cause, items in diagnose_missing(rows, missing).items():
        print(f"\n{len(items)} — {REMEDIES.get(cause, cause)}")
        for item in items:
            print(f"    {item}")
    return 0


def census(rows, counts: dict[str, int], known: set[str], owned: set[str]) -> list[dict]:
    """Regroupe par classe les lieux notoires que le catalogue n'a pas.

    Le tri se fait sur les lieux INCONNUS et non sur le total : une classe déjà
    largement collectée n'est pas un trou, même si elle est immense. Ce qu'on
    cherche, ce sont les portes fermées.
    """
    par_classe: dict[str, dict] = {}
    vus: dict[str, set[str]] = defaultdict(set)

    for row in rows:
        qid = wd.qid_from_uri(row.get("item"))
        class_qid = wd.qid_from_uri(row.get("class"))
        if not qid or not class_qid or qid in vus[class_qid]:
            continue
        vus[class_qid].add(qid)
        entry = par_classe.setdefault(
            class_qid,
            {"qid": class_qid, "label": "", "total": counts.get(class_qid, 0),
             "manquants": 0, "exemples": []},
        )
        if qid not in known:
            entry["manquants"] += 1
            if len(entry["exemples"]) < 5:
                entry["exemples"].append(row.get("itemLabel") or qid)

    for entry in par_classe.values():
        entry["collectee"] = entry["qid"] in owned
    return sorted(par_classe.values(), key=lambda e: -e["manquants"])


#: Planchers explorés par `gaps --class` : ceux qu'on écrirait vraiment.
THRESHOLDS = [2, 3, 4, 6, 8, 10, 12, 15, 20]


def cmd_gaps(args: argparse.Namespace, config: Config) -> int:
    """Quelles classes de lieux nous échappent ?

    La collecte part des classes qu'on connaît : elle est par construction
    incapable de dire ce qu'elle ignore. Une liste d'incontournables écrite de
    mémoire ne le peut pas non plus — elle oublie précisément ce qu'on oublie.

    On part donc de l'inverse : tout ce que Wikidata situe en France et
    documente dans plusieurs langues, moins ce que le catalogue possède déjà.

    En DEUX temps, et c'est ce qui rend la chose tenable. Un décompte agrégé
    chez WDQS d'abord, puis les membres des seules classes intéressantes,
    bornés par `VALUES`. La version qui paginait tous les lieux de France
    mourait en 504 : chaque page retriait des dizaines de milliers de lignes.
    """
    raw_path = args.out / "places_raw.json"
    if not raw_path.exists():
        print(f"{raw_path} absent — lance d'abord `fetch`.", file=sys.stderr)
        return 1

    known = _known_qids(raw_path)
    owned = set(_class_owners(config))
    client = wd.SparqlClient()

    if args.klass:
        return _print_thresholds(client, args.klass, known, config)

    print(f"Décompte des lieux français à {args.min_sitelinks} langues ou plus…")
    counts: dict[str, int] = {}
    for row in client.query(wd.class_census_query(args.min_sitelinks)):
        class_qid = wd.qid_from_uri(row.get("class"))
        if class_qid:
            counts[class_qid] = int(row.get("n") or 0)
    if not counts:
        print("Aucun résultat — le plancher est peut-être trop haut.")
        return 0

    # On n'interroge les membres que des classes assez fournies pour valoir un
    # thème : le reste est du bruit, et chaque classe coûte une requête.
    candidates = [
        qid for qid, n in sorted(counts.items(), key=lambda kv: -kv[1])
        if n >= args.min_places
    ][: args.limit * 2]
    print(f"{len(counts)} classes, {len(candidates)} assez fournies — "
          f"examen de leurs membres…")

    # Par petits lots : les classes massives (église, musée, montagne) font
    # dépasser le délai de WDQS dès qu'on en groupe dix. Un lot perdu, ce sont
    # dix angles morts qui restent aveugles — et le recensement ne sert plus à
    # rien s'il tait ce qu'il n'a pas pu regarder.
    rows: list[dict] = []
    manques: list[str] = []
    for batch in wd.chunked(candidates, 4):
        try:
            rows.extend(client.query(wd.class_members_query(batch, args.min_sitelinks)))
        except Exception as exc:
            LOG.warning("classes non examinées (%s) : %s", exc, ", ".join(batch))
            manques.extend(batch)

    classes = [c for c in census(rows, counts, known, owned) if c["manquants"]]
    labels = _entity_labels(client, [c["qid"] for c in classes[: args.limit]])
    for entry in classes:
        entry["label"] = labels.get(entry["qid"], entry["qid"])

    print(f"\n{len(known)} lieux au catalogue · "
          f"{sum(c['manquants'] for c in classes)} lieux notoires non collectés.\n")
    print(f"  {'classe':<38} {'absents':>8} {'sur':>6}   exemples")
    for entry in classes[: args.limit]:
        marque = "·" if entry["collectee"] else "✗"
        label = f"{marque} {entry['label']} ({entry['qid']})"
        print(f"  {label[:38]:<38} {entry['manquants']:>8} {entry['total']:>6}   "
              + ", ".join(entry["exemples"][:3])[:60])

    if manques:
        # Le dire fort : une liste incomplète qui se présente comme complète
        # est pire que pas de liste du tout.
        print(f"\n⚠ {len(manques)} classes N'ONT PAS PU être examinées — le "
              f"recensement ci-dessus est INCOMPLET.")
        print("  Relance avec un plancher plus haut (`--min-sitelinks 15`) ou "
              "moins de classes (`--min-places 20`).")
        print("  " + ", ".join(manques[:20]) + (f" (+{len(manques) - 20})"
              if len(manques) > 20 else ""))

    print("\n« ✗ » : aucun thème ne collecte cette classe — c'est un angle mort.")
    print("« · » : classe collectée ; ses absents sont sous un plancher, pas hors")
    print("du radar. `gaps --class Q3947` dit ce que changerait chaque plancher.")
    return 0


def _entity_labels(client, qids: list[str]) -> dict[str, str]:
    labels: dict[str, str] = {}
    for batch in wd.chunked(qids, 40):
        for row in client.query(wd.entity_labels_query(batch)):
            qid = wd.qid_from_uri(row.get("item"))
            if qid:
                labels[qid] = row.get("itemLabel") or qid
    return labels


def _print_thresholds(client, class_qid: str, known: set[str], config: Config) -> int:
    """Ce que changerait chaque plancher, pour une classe donnée.

    Baisser un plancher se décide sur un nombre, pas sur une impression — et
    le nombre ne devrait pas coûter une demi-heure de collecte à obtenir.
    """
    label = _entity_labels(client, [class_qid]).get(class_qid, class_qid)
    rows = client.query(wd.class_thresholds_query(class_qid, THRESHOLDS))
    if not rows:
        print(f"{class_qid} : aucun lieu français situé de cette classe.")
        return 0

    row = rows[0]
    current = dict(_class_owners(config)).get(class_qid)
    print(f"\n{label} ({class_qid}) — lieux français situés, par plancher de collecte\n")
    print("      " + "".join(f"{'≥' + str(t):>8}" for t in THRESHOLDS))
    print("      " + "".join(f"{row.get('n' + str(t), '0'):>8}" for t in THRESHOLDS))
    if current:
        theme_id, floor = current
        print(f"\n  Collectée par « {theme_id} » à partir de {floor} langues.")
        for lower, higher in zip(THRESHOLDS, THRESHOLDS[1:]):
            if lower < floor <= higher:
                gagne = int(row.get(f"n{lower}", 0)) - int(row.get(f"n{higher}", 0))
                print(f"  Descendre à {lower} en ramènerait environ {gagne} de plus.")
                break
    else:
        print("\n  Aucun thème ne collecte cette classe.")
    print("  Le plancher se règle dans `themes.yaml`, puis `fetch --only <thème>`.")
    return 0


def cmd_rename(args: argparse.Namespace, config: Config) -> int:
    """Choisit le nom d'affichage d'un lieu, durablement.

    Wikidata donne un libellé, pas un titre. Il est parfois exact mais
    illisible, parfois encombré d'une précision de base de données. Le curateur
    tranche, et sa décision survit à toutes les reconstructions.
    """
    path = args.manual / "names.csv"
    names = read_names(path)

    if args.wikidata_id is None:
        if not names:
            print("Aucun renommage. Usage : rename Q3330248 « Nom choisi »")
            return 0
        for qid in sorted(names):
            print(f"  {qid:<12} {names[qid]}")
        print(f"\n{len(names)} renommage(s) dans {path}")
        return 0

    qid = args.wikidata_id.strip()
    if not qid.startswith("Q") or not qid[1:].isdigit():
        print(f"« {qid} » n'est pas un identifiant Wikidata.", file=sys.stderr)
        return 1

    if args.clear:
        if names.pop(qid, None) is None:
            print(f"{qid} n'avait pas de nom choisi.")
            return 0
        write_names(path, names)
        print(f"{qid} reprend son libellé Wikidata.")
        return 0

    if not args.name:
        print("Il manque le nom. Usage : rename Q3330248 « Nom choisi »", file=sys.stderr)
        return 1

    names[qid] = args.name
    write_names(path, names)
    print(f"{qid} s'affichera « {read_names(path)[qid]} ».")
    print("Relance `build` : le nom vaudra partout, y compris dans la revue.")
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


APP_OUTLINES = BASE_DIR.parent / "mobile" / "src" / "data" / "outlines.json"


def cmd_export_outlines(args: argparse.Namespace, config: Config) -> int:
    """Fabrique les contours administratifs de la carte de conquête.

    À lancer une fois pour toutes : les frontières administratives ne bougent
    qu'à la faveur d'une loi, et le fichier produit est versionné avec
    l'application. Rien à relancer après un `build`.
    """
    tolerances = dict(DEFAULT_TOLERANCE_KM2)
    if args.tolerance is not None:
        tolerances = {level: args.tolerance for level in tolerances}

    counts = export_outlines(args.to, tolerances, source_dir=args.from_dir)
    size = args.to.stat().st_size / 1024
    print(f"Contours écrits dans {args.to} ({size:.0f} Ko)")
    for level, count in counts.items():
        print(f"  {level:<12} {count:>3} territoires")
    print(OUTLINE_ATTRIBUTION)
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


def _print_stats(places, collections, raw=None, config: Config | None = None) -> None:
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

    if config is not None:
        # Roam promet des PAYSAGES autant que du patrimoine. Wikidata documente
        # bien mieux le bâti que le naturel, et plusieurs mécanismes du pipeline
        # penchent du même côté sans le dire : sans ce compte, la dérive vers le
        # culturel resterait invisible jusqu'à ce qu'un utilisateur la remarque.
        kinds = {theme.id: theme.kind for theme in config.themes}
        counts = Counter(
            kinds.get(p.theme_id if hasattr(p, "theme_id") else p["theme_id"], "culture")
            for p in places
        )
        total = sum(counts.values())
        if total:
            print("  Nature / culture     : " + " · ".join(
                f"{label} {counts.get(key, 0)} ({counts.get(key, 0) / total:.0%})"
                for key, label in (("nature", "nature"), ("culture", "culture"))
            ))

    ouverts = sum(1 for p in places if getattr(p, "visitable", None) is True)
    fermes = sum(1 for p in places if getattr(p, "visitable", None) is False)
    rapproches = sum(1 for p in places if getattr(p, "osm_id", None))
    if rapproches:
        # « Non renseigné » n'est pas « fermé » : OpenStreetMap ne porte des
        # horaires que sur une minorité d'objets, y compris visitables.
        print(
            f"  Ouverture au public  : {ouverts} confirmés ouverts, "
            f"{fermes} accès refusé, "
            f"{len(places) - ouverts - fermes} non renseignés"
        )

    if config is not None:
        _print_visitor_coverage(places, config)

    source = raw if raw is not None else places
    _print_sitelink_distribution(source, config_floors())
    if config is not None and hasattr(source[0] if source else None, "theme_id"):
        _print_rescue_distribution(source, config)
    print()


def _print_visitor_coverage(places, config: Config) -> None:
    """Couverture et barème de la fréquentation.

    Le poids ne se choisit pas dans l'abstrait. Ce tableau dit deux choses : sur
    combien de lieux le signal joue réellement, et combien de points il vaut à
    chaque ordre de grandeur — à comparer aux 55 points que valent onze langues.
    Trop haut, la fréquentation écrase tout ; trop bas, elle ne corrige rien.
    """
    rule = config.visitors
    known = [p for p in places if getattr(p, "visitors_per_year", None)]
    if not rule.property_id:
        if rule.search:
            print("  Fréquentation        : propriété non résolue — "
                  "`suggest-qids --property` puis `enrich`")
        return
    if not known:
        print("  Fréquentation        : aucun chiffre — as-tu relancé `enrich` ?")
        return

    print(f"  Fréquentation        : {len(known)} lieux sur {len(places)} "
          f"({len(known) / max(len(places), 1):.0%}), poids {rule.weight}")

    by_theme: dict[str, list[int]] = defaultdict(list)
    for place in known:
        by_theme[place.theme_id].append(place.visitors_per_year)
    print(f"      {'thème':<16} {'avec chiffre':>12} {'médiane':>10} {'maximum':>12}")
    for theme_id, counts in sorted(by_theme.items(), key=lambda kv: -len(kv[1])):
        ordered = sorted(counts)
        median = ordered[len(ordered) // 2]
        print(f"      {theme_id:<16} {len(counts):>12} {median:>10,} {max(counts):>12,}"
              .replace(",", " "))

    bareme = " · ".join(
        f"{count:,}".replace(",", " ") + f" → +{rule.weight * math.log1p(count / rule.scale):.0f}"
        for count in (10_000, 100_000, 1_000_000, 10_000_000)
    )
    print(f"      barème : {bareme}")
    print("      (onze langues valent 55 points de notoriété — c'est l'échelle "
          "à laquelle comparer)")


def config_floors() -> dict[str, int]:
    """Plancher éditorial courant de chaque thème, pour repérer la colonne active."""
    from .config import load_config

    try:
        return {theme.id: theme.min_sitelinks for theme in load_config().themes}
    except Exception:
        return {}


SITELINK_STEPS = (2, 4, 6, 8, 10, 15, 20, 30)
RESCUE_STEPS = (70, 80, 85, 90, 100, 120)


def _print_rescue_distribution(places, config: Config) -> None:
    """Combien de lieux le repêchage ferait entrer, selon le seuil de score.

    Ce tableau manquait, et son absence a coûté un catalogue : un seuil choisi
    sur un seul exemple — le musée de Giverny, à 88 points — s'est révélé
    repêcher 2 757 lieux. Un réglage se choisit sur une distribution, jamais
    sur un cas.

    Ne comptent que les lieux sous le plancher de leur thème ET dont l'accueil
    du public est attesté : ce sont les seuls que le repêchage peut concerner.
    """
    eligible: dict[str, list[float]] = defaultdict(list)
    for place in places:
        if place.visitable is not True or place.pinned:
            continue
        try:
            floor = config.theme(place.theme_id).min_sitelinks
        except KeyError:
            continue
        if place.sitelinks < floor:
            eligible[place.theme_id].append(place.score)

    if not eligible:
        return

    current = config.scoring.rescue_score
    header = "  ".join(f"≥{step:<4}" for step in RESCUE_STEPS)
    print("\n  Lieux repêchés selon le seuil de score (accueil du public attesté) :")
    print(f"      {'thème':<16} {header}   (× = seuil actuel)")
    for theme_id, scores in sorted(eligible.items(), key=lambda kv: -len(kv[1])):
        cells = []
        for step in RESCUE_STEPS:
            count = sum(1 for score in scores if score >= step)
            mark = "×" if step == current else " "
            cells.append(f"{count}{mark}".ljust(7))
        print(f"      {theme_id:<16} {''.join(cells)}")
    total = sum(
        sum(1 for score in scores if score >= current) for scores in eligible.values()
    )
    print(f"      seuil actuel ({current:g}) : {total} lieux repêchés sur "
          f"{sum(len(v) for v in eligible.values())} éligibles.")


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
    suggest.add_argument(
        "--property",
        action="store_true",
        help="chercher des propriétés (P-ids) et non des entités",
    )

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

    adopt = sub.add_parser(
        "adopt",
        help="fait entrer les candidats d'OpenStreetMap dans le catalogue (réseau requis)",
    )
    adopt.add_argument(
        "--candidates", type=Path, help="feuille de candidats (défaut : data/out/candidates.csv)"
    )
    adopt.add_argument(
        "--skip-summaries",
        action="store_true",
        help="ne pas récupérer les descriptions (la passe la plus longue)",
    )

    def add_decision_args(target: argparse.ArgumentParser) -> None:
        """Options communes aux deux commandes qui construisent le catalogue.

        `build` applique les décisions déjà enregistrées, `apply-review` en
        ajoute d'abord de nouvelles : les deux ont besoin des mêmes réglages.
        """
        target.add_argument(
            "--adjust",
            type=float,
            default=60.0,
            # Doit dépasser le plus gros bonus de label (UNESCO, 40 points) :
            # sans cela, une décision humaine ne pourrait pas rattraper un lieu
            # que Wikidata documente mal.
            help="ajustement de score pour promote/demote",
        )
        target.add_argument(
            "--strict",
            action="store_true",
            help="ne garder que les lieux explicitement relus",
        )

    build = sub.add_parser("build", help="score, construit les collections et exporte")
    add_decision_args(build)

    explain = sub.add_parser(
        "explain", help="dit pourquoi un lieu est dans le catalogue, ou pourquoi il n'y est pas"
    )
    explain.add_argument("name", help="tout ou partie du nom du lieu")
    explain.add_argument("--limit", type=int, default=5, help="correspondances affichées")
    add_decision_args(explain)

    review = sub.add_parser("apply-review", help="enregistre les décisions d'une revue")
    review.add_argument("--review", type=Path, help="chemin de review.csv")
    add_decision_args(review)

    gaps = sub.add_parser(
        "gaps",
        help="quelles classes de lieux nous échappent ? (réseau requis, long)",
    )
    gaps.add_argument(
        "--min-sitelinks", type=int, default=12,
        help="notoriété minimale des lieux recensés (défaut 12 ; plus bas = plus long)",
    )
    gaps.add_argument("--limit", type=int, default=30, help="classes affichées")
    gaps.add_argument(
        "--class", dest="klass", metavar="QID",
        help="au lieu du recensement : ce que changerait chaque plancher pour CETTE classe",
    )
    gaps.add_argument(
        "--min-places", type=int, default=5,
        help="ignorer les classes sous ce nombre de lieux",
    )

    sub.add_parser(
        "check-lists",
        help="diagnostique les Q-ids listés à la main qui n'arrivent pas (réseau requis)",
    )

    probe = sub.add_parser(
        "probe",
        help="pourquoi un lieu n'a-t-il jamais été collecté ? (réseau requis)",
    )
    probe.add_argument("terms", nargs="+", help="Q-ids, ou termes à chercher")
    probe.add_argument("--limit", type=int, default=4, help="candidats par terme")

    rename = sub.add_parser(
        "rename", help="choisit le nom d'affichage d'un lieu (durable)"
    )
    rename.add_argument("wikidata_id", nargs="?", help="Q-id du lieu ; omis, liste les renommages")
    rename.add_argument("name", nargs="?", help="nom à afficher")
    rename.add_argument(
        "--clear", action="store_true", help="revenir au libellé de Wikidata"
    )

    sub.add_parser("stats", help="statistiques du catalogue construit")

    app = sub.add_parser("export-app", help="écrit le catalogue dans l'application")
    app.add_argument("--to", type=Path, default=APP_CATALOG, help="fichier de destination")

    contours = sub.add_parser(
        "export-outlines",
        help="fabrique les contours des régions et départements (réseau requis)",
    )
    contours.add_argument("--to", type=Path, default=APP_OUTLINES, help="fichier de destination")
    contours.add_argument(
        "--tolerance",
        type=float,
        help="aire minimale d'un sommet, en km² (défaut : par échelle)",
    )
    contours.add_argument(
        "--from-dir",
        type=Path,
        dest="from_dir",
        help="dossier de GeoJSON déjà téléchargés (region.geojson, departement.geojson)",
    )

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
        "adopt": cmd_adopt,
        "build": cmd_build,
        "explain": cmd_explain,
        "apply-review": cmd_apply_review,
        "stats": cmd_stats,
        "review": cmd_review,
        "check-lists": cmd_check_lists,
        "gaps": cmd_gaps,
        "probe": cmd_probe,
        "rename": cmd_rename,
        "export-app": cmd_export_app,
        "export-outlines": cmd_export_outlines,
    }
    return handlers[args.command](args, config)
