"""Interface en ligne de commande du pipeline de curation."""

from __future__ import annotations

import argparse
import io
from contextlib import contextmanager, redirect_stdout
from dataclasses import replace
import csv
import json
import logging
import math
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any
from pathlib import Path

from . import wikidata as wd
from .collections import DUPLICATE_DISTANCE_M, build_all, fantomes, haversine_m
from .config import CONFIG_DIR, Config, load_config
from .export import (
    review_state,
    review_tiers,
    read_review_csv,
    read_review_themes,
    write_json,
    write_review_csv,
    write_app_catalog,
    write_review_html,
    write_seed_sql,
)
from .raw import EXTRA_SHARD, read_raw, shard_of, shards, write_raw
from .merge import conflicted, merge_file
from .fetch import (
    REMEDIES,
    apply_labels,
    carry_enrichment,
    fetch_label_members,
    read_fetch_state,
    stale_themes,
    _paged,
    diagnose_missing,
    enrich_exclusions,
    enrich_visitors,
    enrich_article_sizes,
    enrich_pageviews,
    enrich_communes,
    enrich_departements,
    enrich_flags,
    enrich_summaries,
    fetch_listed_places,
    read_csv_rows,
    read_place_list,
    align_departements,
    resolve_admin,
    run_fetch,
)
from .models import Collection, CollectionPlace, Place
from .outlines import ATTRIBUTION as OUTLINE_ATTRIBUTION, DEFAULT_TOLERANCE_KM2
from .outlines import export as export_outlines
from .review import (
    CLEAR, DECISIONS, apply_decisions, apply_names, apply_themes, diff_tiers,
    read_decisions, read_names, read_themes, theme_claims, write_themes,
    read_snapshot, vanished, write_decisions, write_names, write_snapshot,
)
from .score import rescued, score_all, warn_missing_pageviews

LOG = logging.getLogger("roam")

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_OUT = BASE_DIR / "data" / "out"
DEFAULT_MANUAL = BASE_DIR / "data" / "manual"
# La collecte, versionnée et découpée par thème. Ce n'est pas une sortie de
# construction : c'est la donnée sur laquelle portent les décisions.
DEFAULT_RAW = BASE_DIR / "data" / "raw"
# Le brouillon de revue, écrit par le serveur à chaque clic et relu par
# `apply-review`. Il vit dans le dossier de sortie, donc hors de git : ce n'est
# pas une mémoire, c'est le trajet entre le navigateur et `decisions.csv`.
AUTOSAVE = "review-decisions.csv"


def _fold(text: str) -> str:
    """Minuscules sans accents, pour chercher « herouville » et trouver « Hérouville »."""
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return plain.lower()


def _load_places(path: Path) -> list[Place]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [Place.from_dict(item) for item in raw]


def _save_raw(args: argparse.Namespace, places: list[Place]) -> None:
    """Écrit la collecte dans le dépôt ET dans la copie de travail.

    Toute commande qui modifie les candidats passe par ici. Écrire seulement
    `places_raw.json` laisserait l'enrichissement — résumés, départements,
    fréquentation — sur une seule machine, et l'autre relirait un catalogue
    appauvri sans qu'aucune erreur ne le dise.
    """
    # La copie de travail n'est PAS versionnée : après un `git pull`, elle est
    # en retard sur le dépôt. Une commande qui la relit et la réécrit efface
    # alors ce que le dépôt venait d'apporter — c'est ainsi qu'un `relabel` a
    # annulé la réparation de huit mille lieux, sans un mot.
    #
    # Le dépôt fait donc foi pour ce qu'`enrich` a posé : ce qui manque au lot
    # qu'on écrit est repris de ce qui est déjà là. Cela n'empêche aucune
    # modification — seules les valeurs ABSENTES sont complétées.
    repris = carry_enrichment(places, args.raw, args.out / "places_raw.json")
    if repris > len(places) // 10:
        LOG.warning(
            "%s lieux sur %s ont retrouvé dans le dépôt un enrichissement que "
            "ta copie de travail avait perdu — elle était en retard. Lance "
            "`sync` après un `git pull` pour éviter ce genre de surprise.",
            repris, len(places),
        )
    # Même endroit, même raison : un lieu dont le département contredit sa
    # commune est rangé dans la mauvaise collection départementale, et rien ne
    # le signale. La commune vient des coordonnées, elle a le dernier mot.
    align_departements(places)
    write_raw(args.raw, places, replacing={shard_of(place) for place in places})
    (args.out / "places_raw.json").write_text(
        json.dumps([p.to_dict() for p in places], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def cmd_label_probe(args: argparse.Namespace, config: Config) -> int:
    """Par quelle propriété Wikidata ce label rattache-t-il ses membres ?

    `labels.yaml` propose plusieurs façons de poser la question — désignation
    patrimoniale (P1435), appartenance à une organisation (P463), instance
    d'une classe, et depuis peu l'exploitant (P137) ou le propriétaire (P127),
    car toute liste utile n'est pas un label : le Centre des monuments
    nationaux est l'établissement public qui GÈRE une centaine de monuments
    d'État. Rien ne dit laquelle convient à une entité donnée. Se
    tromper ne lève aucune erreur : la requête rend zéro membre, le label
    n'apporte rien, et il faut une demi-heure de collecte pour s'en apercevoir.

    Cinq requêtes bornées répondent avant qu'on écrive la moindre ligne de
    configuration. Un seul compte non nul désigne la bonne propriété ; aucun
    signifie que Wikidata ne porte pas cette liste, et qu'elle devra être
    saisie à la main (`kind: manual`).
    """
    qid = (args.wikidata_id or "").strip()
    if not qid.startswith("Q") or not qid[1:].isdigit():
        print(f"« {qid} » n'est pas un identifiant Wikidata.", file=sys.stderr)
        return 1

    client = wd.SparqlClient()
    for ligne in client.query(wd.entity_labels_query([qid])):
        libelle = ligne.get("itemLabel") or qid
        description = ligne.get("itemDescription") or ""
        print(f"{qid} — {libelle}" + (f" ({description})" if description else ""))

    print("\nMembres français, par façon d'interroger :\n")
    trouve = False
    for kind, explication in (
        ("heritage", "désignation patrimoniale (P1435) — celle des sites classés"),
        ("member_of", "membre d'une organisation (P463) — celle des Plus Beaux Villages"),
        ("instance", "instance de cette classe (P31/P279*)"),
        ("operator", "géré par (P137) — pour un exploitant, pas un label"),
        ("owner", "propriété de (P127)"),
    ):
        try:
            membres = list(client.query(wd.label_members_query(kind, qid)))
        except Exception as erreur:  # noqa: BLE001 — un miroir en panne n'est pas un verdict
            print(f"    {kind:10s} : requête en échec ({erreur})")
            continue
        marque = "  ← c'est celle-là" if membres else ""
        if membres:
            trouve = True
        print(f"    {kind:10s} : {len(membres):5d} membres   {explication}{marque}")

    if trouve:
        print("\n  Reporte le `kind` retenu dans config/labels.yaml, puis :"
              "\n      python -m roam_pipeline verify-qids"
              "\n      python -m roam_pipeline fetch --only <thème>")
    else:
        print("\n  Wikidata ne rattache aucun lieu français à ce label. La liste"
              "\n  doit être saisie à la main : `kind: manual` dans labels.yaml,"
              "\n  puis data/manual/<identifiant-du-label>.csv.")
    return 0


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
    places = run_fetch(client, config, args.out, args.manual,
                       only=args.only or None, raw_dir=args.raw)
    print(f"{len(places)} lieux candidats collectés → {args.out / 'places_raw.json'}")
    return 0


def cmd_sync(args: argparse.Namespace, config: Config) -> int:
    """Aligne la copie de travail sur la collecte du dépôt, ou l'inverse.

    C'est la commande qui rend les décisions transportables. Sans elle, chaque
    machine reconstruit son catalogue depuis sa propre collecte : deux
    catalogues différents, et des verdicts qui portent sur des lieux que
    l'autre machine n'a jamais vus.

    `--depuis-la-copie` sert une fois, pour verser dans le dépôt une collecte
    déjà faite. Ensuite le sens normal est l'autre : `git pull` puis `sync`
    remplacent une demi-heure de collecte.
    """
    raw_path = args.out / "places_raw.json"

    if args.from_working_copy:
        if not raw_path.exists():
            print(f"{raw_path} absent — rien à verser.", file=sys.stderr)
            return 1
        places = _load_places(raw_path)
        written = write_raw(args.raw, places, replacing={shard_of(p) for p in places})

        # Un thème retiré de la configuration n'est plus recollecté par personne :
        # son fichier resterait dans le dépôt indéfiniment, et ses lieux
        # fausseraient chaque tableau de diagnostic sans jamais sortir dans une
        # collection. `fetch` fait déjà ce ménage ; le versement doit aussi.
        configures = {t.id for t in config.themes} | {EXTRA_SHARD, "sans-theme"}
        oublies = [name for name in shards(args.raw) if name not in configures]
        for name in oublies:
            (args.raw / f"{name}.json").unlink(missing_ok=True)
            written.pop(name, None)
        if oublies:
            print(f"⚠ thèmes disparus de la configuration, non versés : "
                  f"{', '.join(oublies)}")

        print(f"{len(places)} lieux versés dans {args.raw} :")
        for name, count in sorted(written.items()):
            print(f"  {name:<16} {count:>5}")
        print("\nCommitte ce dossier : c'est lui qui rendra le catalogue identique "
              "sur tes deux machines.")
        return 0

    places = read_raw(args.raw)
    if not places:
        print(f"{args.raw} ne contient aucune collecte. Sur la machine qui en a "
              "une : `python -m roam_pipeline sync --depuis-la-copie`, puis "
              "committe le dossier.", file=sys.stderr)
        return 1

    args.out.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(
        json.dumps([p.to_dict() for p in places], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    par_theme = Counter(place.theme_id for place in places)
    print(f"{len(places)} lieux repris du dépôt → {raw_path}")
    absents = [t.id for t in config.themes if not par_theme.get(t.id)]
    if absents:
        print(f"⚠ {len(absents)} thèmes sans aucun candidat dans le dépôt : "
              + ", ".join(absents[:8])
              + (f" (+{len(absents) - 8})" if len(absents) > 8 else ""))
        print("  Personne ne les a encore collectés — `fetch --only "
              + " ".join(absents[:3]) + "` sur la machine de ton choix.")
    print("Enchaîne avec `build` : aucune collecte n'est nécessaire.")
    return 0


def cmd_relabel(args: argparse.Namespace, config: Config) -> int:
    """Rappose les labels sur la collecte, sans la recollecter.

    Les labels sont apposés pendant `fetch`, et sur les seuls thèmes que ce
    `fetch` a recollectés. Ajouter un identifiant à une liste manuelle — les
    vingt-cinq Grands Sites de France que Wikidata ignore — n'avait donc aucun
    effet tant qu'on n'avait pas refait passer leur thème, c'est-à-dire une
    demi-heure pour changer une ligne de CSV.

    Or apposer un label ne demande pas de recollecter des lieux : il suffit de
    redemander la liste de ses membres, ce qui coûte une douzaine de requêtes.
    """
    raw_path = args.out / "places_raw.json"
    if not raw_path.exists():
        print(f"{raw_path} absent — lance d'abord `fetch`.", file=sys.stderr)
        return 1

    places = _load_places(raw_path)
    avant = {place.wikidata_id: set(place.labels) for place in places}

    client = wd.SparqlClient()
    members: dict[str, set[str]] = {}
    for label in config.labels:
        try:
            members[label.id] = fetch_label_members(client, label, args.manual)
        except Exception as erreur:  # noqa: BLE001 — un label en échec n'est pas fatal
            LOG.error("label %s : collecte échouée (%s)", label.id, erreur)
            members[label.id] = set()
    apply_labels(places, members)

    # Un membre que la collecte ne contient pas ne peut pas être étiqueté :
    # `relabel` appose des labels, il ne crée pas de lieux. Cent une communes
    # des Plus Beaux Détours ont ainsi été saisies, relabellisées, et n'ont
    # jamais rien produit — le thème « villages » n'a aucune classe Wikidata,
    # il n'existe que par ses listes, et seul un `fetch` de ce thème va
    # chercher les entités correspondantes.
    presents = {place.wikidata_id for place in places}
    par_theme_a_refaire: dict[str, int] = {}
    for theme in config.themes:
        attendus: set[str] = set()
        for label_id in theme.from_labels:
            attendus |= members.get(label_id, set())
        manquants = attendus - presents
        if manquants:
            par_theme_a_refaire[theme.id] = len(manquants)

    gagnes = [p for p in places if set(p.labels) - avant[p.wikidata_id]]
    perdus = [p for p in places if avant[p.wikidata_id] - set(p.labels)]
    _save_raw(args, places)

    if par_theme_a_refaire:
        detail = ", ".join(f"{t} {n}" for t, n in sorted(par_theme_a_refaire.items()))
        print(f"\n⚠ {sum(par_theme_a_refaire.values())} membres de liste officielle "
              f"ne sont PAS dans la collecte : {detail}.")
        print("  `relabel` appose des labels, il ne crée pas de lieux. Pour les "
              "faire entrer :")
        for theme_id in sorted(par_theme_a_refaire):
            print(f"      python -m roam_pipeline fetch --only {theme_id}")

    print(f"{len(places)} lieux relus : {len(gagnes)} gagnent un label, "
          f"{len(perdus)} en perdent un.")
    for place in gagnes[:20]:
        neufs = ", ".join(sorted(set(place.labels) - avant[place.wikidata_id]))
        print(f"    + {place.wikidata_id:<11} {place.name:<44} {neufs}")
    if len(gagnes) > 20:
        print(f"    (+{len(gagnes) - 20})")
    for place in perdus[:10]:
        partis = ", ".join(sorted(avant[place.wikidata_id] - set(place.labels)))
        print(f"    − {place.wikidata_id:<11} {place.name:<44} {partis}")
    print("\n  Enchaîne avec `build`.")
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
    # Une requête par article : la passe la plus longue, et la seule dont le
    # résultat ne pèse encore rien au score. On ne la lance donc que si on la
    # demande.
    if args.pageviews:
        enrich_pageviews(places)
    _save_raw(args, places)
    print(f"{found} tailles d'articles ajoutées → {raw_path}")
    print("Relance `build` pour en tenir compte dans le classement.")
    return 0


def cmd_discover(args: argparse.Namespace, config: Config) -> int:
    """Confronte le catalogue aux sites de visite d'OpenStreetMap.

    Répond aux deux questions que Wikidata ne sait pas trancher : ce lieu
    se visite-t-il, et que manque-t-il au catalogue.
    """
    from .discover import (
        THEME_BY_TAG, apply_visit_info, find_candidates, guess_theme, is_confident,
        keep_in_france, tag_filters_for,
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

    vises = {t.strip() for t in (args.only or "").split(",") if t.strip()}
    inconnus = vises - {theme.id for theme in config.themes}
    if inconnus:
        print(f"Thème(s) inconnu(s) : {', '.join(sorted(inconnus))}", file=sys.stderr)
        return 1
    tags = tag_filters_for(vises) if vises else None
    if vises:
        # Un thème sans tag dans la table ne produirait rien, et le silence
        # passerait pour un résultat : « aucune cascade trouvée » et « on n'a
        # jamais demandé les cascades » se ressemblent trop.
        couverts = {t for _k, _v, t in THEME_BY_TAG}
        muets = sorted(vises - couverts)
        if muets:
            print(f"⚠ aucun tag OpenStreetMap ne correspond à {', '.join(muets)} — "
                  "ce(s) thème(s) ne seront pas cherchés.", file=sys.stderr)
    if vises and not tags:
        print(f"Aucun tag OpenStreetMap ne correspond à {', '.join(sorted(vises))} — "
              "la table des correspondances est dans discover.THEME_BY_TAG.",
              file=sys.stderr)
        return 1

    grid = list(cells())
    if args.cells:
        grid = grid[: args.cells]
    print(f"Interrogation d'OpenStreetMap : {len(grid)} cellules, compte ~{max(1, len(grid) // 4)} min."
          + (f"\nRestreinte à {', '.join(sorted(vises))}." if vises else ""))
    osm = []
    for index, cell in enumerate(grid, start=1):
        found = client.fetch_cell(cell, tags)
        osm.extend(found)
        LOG.info("cellule %s/%s : %s sites (%s au total)", index, len(grid), len(found), len(osm))

    if not osm:
        print("Aucun site récupéré — service indisponible ?", file=sys.stderr)
        return 1

    places = _load_places(raw_path)
    # Une collecte restreinte ne doit PAS réécrire l'ouverture au public : elle
    # n'a vu qu'une catégorie d'objets, et un lieu du catalogue rapproché d'une
    # cascade voisine perdrait les horaires qu'une collecte complète lui avait
    # trouvés.
    if not vises:
        apply_visit_info(places, osm)
        _save_raw(args, places)

    # Les thèmes sans portes ne peuvent pas produire de site « géré » : là,
    # un lien encyclopédique tient lieu de preuve.
    sans_portes = {theme.id for theme in config.themes if not theme.gated}
    candidates = find_candidates(places, osm, sans_portes)
    # Deuxième garde-fou, indépendant de la requête Overpass : le rectangle de
    # collecte déborde sur les pays voisins, et une zone mal résolue par un
    # miroir Overpass repeuplerait la feuille de musées bâlois ou milanais.
    candidates = keep_in_france(candidates, departements_for)
    if vises:
        candidates = [s for s in candidates if guess_theme(s.tags) in vises]
    confident = [site for site in candidates if is_confident(site, sans_portes)]
    retained = candidates if args.all else confident
    # Une collecte restreinte écrit dans SA feuille. La feuille complète coûte
    # vingt minutes de requêtes Overpass et porte les seuls faits de terrain du
    # catalogue — horaires, tarifs, accès refusé ; l'écraser avec le résultat
    # d'un essai sur un thème la détruirait sans un mot, et `discover --only
    # cascades` l'a bel et bien ramenée à sa seule ligne d'en-tête.
    out_path = args.out / (
        f"candidates-{'-'.join(sorted(vises))}.csv" if vises else "candidates.csv"
    )
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
    if client.abandonnees:
        # Une cellule abandonnée rend zéro site, comme une cellule vide : sans
        # ce compte, une collecte à moitié tombée passe pour un résultat.
        print(f"⚠ {len(client.abandonnees)} cellule(s) sur {len(grid)} abandonnées "
              "faute de réponse d'Overpass — le compte ci-dessous est PARTIEL.")
    # Le critère n'est pas le même partout, et l'annoncer faux vaut moins que
    # ne rien annoncer : sur un thème sans portes, une fiche Wikidata suffit.
    preuve = ("une fiche Wikidata" if vises and vises <= sans_portes
              else "un signe d'accueil du public ET un lien encyclopédique")
    print(f"{len(candidates)} en France et absents du catalogue, "
          f"dont {len(confident)} avec {preuve}.")
    print(f"{min(len(retained), args.limit)} écrits dans {out_path}, "
          f"dont {ready} directement recopiables dans data/manual/places.csv.")
    if not args.all and len(candidates) > len(confident):
        print(f"Ajoute --all pour voir les {len(candidates) - len(confident)} autres.")
    if vises:
        print("Collecte restreinte : l'ouverture au public du catalogue n'a PAS été "
              "mise à jour.")
    else:
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
    # Le filtre des classes AUSSI, et c'est par là que les parcs entraient :
    # `adopt` ramène ce qu'OpenStreetMap propose, où un parc d'attractions est
    # un lieu touristique comme un autre. Sans cette passe, il arrive au
    # catalogue sans que rien ne l'ait regardé.
    enrich_exclusions(client, adopted, config.exclusions.qids)
    enrich_flags(client, adopted)
    enrich_departements(adopted)
    enrich_article_sizes(adopted)
    if not args.skip_summaries:
        enrich_summaries(adopted)

    names.update({place.wikidata_id: place.name for place in adopted})
    _write_candidate_list(list_path, merged, names)

    places += adopted
    _save_raw(args, places)
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
        # Le dépôt porte peut-être déjà la collecte : la reprendre coûte une
        # seconde là où `fetch` coûte une demi-heure.
        if read_raw(args.raw):
            print(f"{raw_path} absent — reprise de la collecte versionnée.")
            cmd_sync(argparse.Namespace(**{**vars(args), "from_working_copy": False}),
                     config)
        else:
            print(f"{raw_path} absent — lance d'abord `fetch`.", file=sys.stderr)
            return 1
    _warn_if_behind_repo(args)

    charges = _load_places(raw_path)
    # Avant de scorer quoi que ce soit : un lieu dont le département contredit
    # sa commune part dans la mauvaise collection départementale, et rien ne le
    # dit. La collecte peut venir de n'importe quel chemin — `sync` écrit
    # `places_raw.json` sans passer par `_save_raw` — donc la vérification se
    # refait ici, où elle décide.
    align_departements(charges)

    # `scored` garde TOUS les candidats : c'est lui qui alimente la distribution,
    # qui ne sert à régler le plancher que si elle porte sur l'avant-filtre.
    warn_missing_pageviews(charges, config)
    scored = score_all(charges, config)
    # Avant tout le reste : le nom choisi par le curateur doit valoir partout,
    # jusque dans la feuille de revue où il relira la ligne.
    renamed = apply_names(scored, read_names(args.manual / "names.csv"))
    # Le rattachement choisi par le curateur, avant tout le reste : il change
    # la collection d'appartenance, donc les voisins, donc le rang.
    themes = read_themes(args.manual / "themes.csv")
    scored, inconnus = apply_themes(scored, themes, {t.id for t in config.themes})
    if inconnus:
        print(f"⚠ themes.csv : thème inconnu pour {', '.join(inconnus)} — ligne "
              "ignorée. Thèmes valides : "
              + ", ".join(t.id for t in config.themes), file=sys.stderr)
    decisions = read_decisions(args.manual / "decisions.csv")
    kept, counts = apply_decisions(scored, decisions, strict=args.strict)
    # Rescoré après les décisions : `drop` retire des lieux, donc la
    # distribution change. Le déplacement de niveau, lui, ne touche pas au
    # score — il s'applique au classement, une fois celui-ci établi.
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
    write_review_html(
        retained, collections, config, args.out / "review.html", changes,
        decided={qid: verdict for qid, (verdict, _note) in decisions.items()},
        # Calculée sur le catalogue AVANT arbitrage : après le dédoublonnage,
        # le lieu n'a plus qu'un thème et la contestation ne se voit plus.
        claims=theme_claims(scored),
        rethemed={qid: theme for qid, (theme, _note) in themes.items()},
    )
    write_seed_sql(retained, collections, config, args.out / "seed.sql")

    _report_tier_changes(changes, gone, before, retained)
    _report_stale_themes(args.out, config, scored)

    if renamed:
        print(f"Renommages appliqués : {renamed}")

    if themes:
        gardes = {place.wikidata_id for place in retained}
        perdus = [qid for qid in themes if qid not in gardes]
        print(f"Thèmes redressés : {len(themes) - len(perdus)}/{len(themes)}")
        if perdus:
            # Le nouveau thème a son propre plancher de notoriété : un lieu
            # peut le rater alors qu'il passait celui de l'ancien. Sans ce
            # message, il disparaîtrait du catalogue en silence.
            print(f"⚠ {len(perdus)} lieux redressés ne sortent dans AUCUNE "
                  f"collection : {', '.join(perdus)}")
            print("    Le plancher de leur nouveau thème les écarte. "
                  "`explain <nom>` dit lequel.")

    if decisions:
        print("Décisions reprises :",
              ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    _print_stats(retained, collections, raw=scored, config=config)
    return 0



def _warn_if_behind_repo(args: argparse.Namespace) -> None:
    """Dit si la copie de travail a pris du retard sur la collecte du dépôt.

    Un `git pull` amène des lieux que cette machine n'a jamais collectés ; sans
    `sync`, `build` continue de travailler sur l'ancienne copie et l'écart
    reste invisible — c'est exactement ainsi qu'un catalogue peut différer
    d'une machine à l'autre sans qu'aucune commande ne proteste.
    """
    repo = {place.wikidata_id for place in read_raw(args.raw)}
    if not repo:
        return
    local = _known_qids(args.out / "places_raw.json")
    manquants = repo - local
    if manquants:
        print(f"⚠ {len(manquants)} lieux présents dans le dépôt manquent à cette "
              "copie de travail. Lance `sync` avant de construire.")

def empty_themes(config: Config, raw) -> list[str]:
    """Thèmes configurés dont le catalogue brut ne contient AUCUN lieu.

    La preuve la plus dure qui soit, et elle ne dépend d'aucun fichier d'état :
    un thème sans un seul candidat n'a pas été collecté ici, point. Sur une
    machine fraîchement clonée, `places_raw.json` n'existe pas — collecter deux
    ou trois thèmes suffit alors à produire un catalogue qui a l'air complet et
    auquel il manque vingt thèmes entiers. C'est ainsi qu'un aperçu publié
    s'est retrouvé sans une seule abbaye.
    """
    presents = {getattr(place, "theme_id", None) for place in raw}
    return [theme.id for theme in config.themes if theme.id not in presents]


def _report_stale_themes(out_dir: Path, config: Config, raw=()) -> None:
    """Un thème absent ou en échec ne doit pas se taire indéfiniment.

    L'échec de collecte était signalé une fois, en fin de journal de `fetch`,
    puis oublié : la reprise partielle reconduisait les anciennes données à
    chaque passage. Le mont Blanc a disparu du catalogue de cette façon, sans
    qu'aucun compteur ne bouge.

    Le fichier d'état ne suffit pas : il ne dit rien des collectes antérieures
    à sa mise en place, et son message rassurant — « le suivi se remplira » —
    couvrait exactement le cas d'un thème jamais collecté sur cette machine.
    Le catalogue brut, lui, ne ment pas.
    """
    vides = empty_themes(config, raw)
    if vides:
        print(f"\n⚠ {len(vides)} thèmes SANS AUCUN LIEU dans les candidats bruts :")
        print("    " + ", ".join(vides))
        print("    Ils n'ont jamais été collectés ici. Le catalogue construit est")
        print("    PARTIEL — ne le publie pas en l'état.")
        print("    Si une autre machine les a collectés : `git pull` puis `sync`.")
        print("    Sinon : `fetch --only " + " ".join(vides) + "`")

    stale = [
        (theme_id, raison)
        for theme_id, raison in stale_themes(read_fetch_state(out_dir), config)
        if theme_id not in set(vides)
    ]
    if not stale:
        return
    inconnus = [t for t, raison in stale if raison.startswith("jamais")]
    casses = [(t, raison) for t, raison in stale if not raison.startswith("jamais")]

    if casses:
        print("\n⚠ Données de thème NON FIABLES :")
        for theme_id, raison in casses:
            print(f"    {theme_id:<16} {raison}")
        print("    Reprends-les : `fetch --only "
              + ",".join(t for t, _ in casses) + "`")
    if inconnus:
        print(f"\n{len(inconnus)} thèmes sans trace de collecte — le suivi ne "
              "date que d'aujourd'hui, il se remplira au prochain `fetch`.")


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


def _mots(nom: str) -> set[str]:
    """Les mots porteurs d'un nom de lieu, articles et ponctuation ôtés."""
    vides = {"de", "des", "du", "la", "le", "les", "l", "d", "et", "aux", "au",
             "sur", "sous", "en", "a", "the", "of"}
    plain = "".join(c if c.isalnum() else " " for c in _fold(nom))
    return {m for m in plain.split() if len(m) > 1 and m not in vides}


def _variantes(nom: str) -> list[str]:
    """Le nom entier, puis ses morceaux.

    Une liste officielle nomme le PÉRIMÈTRE, pas le lieu : « Cap d'Erquy -
    Cap Fréhel » désigne deux caps, « Chaînes des Puys - Puy de Dôme » un
    massif et son sommet, « Falaises d'Étretat, Côte d'Albâtre » une falaise et
    la côte qui la porte. Cherché entier, aucun ne se retrouve ; cherché par
    morceaux, presque tous.

    Le tiret n'est découpé qu'entouré d'espaces : « Concors-Sainte-Victoire »
    est un nom, pas une énumération, et « Sainte-Victoire » n'en est pas un
    morceau séparable.
    """
    morceaux = [nom]
    reste = nom.replace(" – ", " - ").replace(" — ", " - ")
    for separateur in (" - ", ",", " et "):
        reste = reste.replace(separateur, "|")
    if "|" in reste:
        morceaux += [m.strip() for m in reste.split("|") if _mots(m.strip())]
    return morceaux


class _FauxLieu:
    """Juste assez d'un lieu pour l'afficher parmi les propositions."""

    def __init__(self, wikidata_id: str, name: str):
        self.wikidata_id = wikidata_id
        self.name = name


def _resolve_chez_wikidata(
    noms: list[str], class_qid: str
) -> tuple[list[tuple[str, "_FauxLieu"]], dict[str, list[tuple[str, str]]]]:
    """Retrouve des noms chez Wikidata, bornés par une classe.

    Un nom qui rend PLUSIEURS entités n'est pas résolu : « Saint-Martin » est
    une trentaine de communes, et choisir au hasard écrirait un faux
    identifiant dans une liste officielle. Ceux-là repartent en arbitrage.
    """
    client = wd.SparqlClient()
    # La requête interroge plusieurs casses du même nom — Wikidata écrit
    # « forêt de Fontainebleau » sans majuscule. Le résultat revient sous la
    # graphie trouvée : on le replie sur le nom que le curateur a écrit, sans
    # quoi la ligne ne se rattache à aucune entrée de sa liste.
    origine = {
        forme: nom for nom in noms for forme in wd.label_casings(nom)
    }
    par_nom: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for batch in wd.chunked(noms, 150):
        try:
            rows = client.query(wd.label_lookup_query(batch, class_qid))
        except Exception as erreur:  # noqa: BLE001
            print(f"    recherche Wikidata en échec ({erreur})", file=sys.stderr)
            continue
        for row in rows:
            qid = wd.qid_from_uri(row.get("item"))
            nom = origine.get(row.get("nom") or "", row.get("nom"))
            if qid and nom and (qid, row.get("itemLabel") or nom) not in par_nom[nom]:
                par_nom[nom].append((qid, row.get("itemLabel") or nom))

    trouves = [
        (nom, _FauxLieu(*couples[0])) for nom, couples in par_nom.items()
        if len(couples) == 1
    ]
    ambigus = {nom: couples for nom, couples in par_nom.items() if len(couples) > 1}

    # Une douzaine de « Villeneuve » alignées sans rien pour les distinguer ne
    # se tranchent pas. La description de Wikidata nomme presque toujours le
    # département — « commune française du département de l'Aveyron » — et la
    # liste officielle donne le même : le rapprochement devient évident.
    homonymes = [q for couples in ambigus.values() for q, _ in couples]
    if homonymes:
        descriptions = _entity_descriptions(client, homonymes)
        # Et surtout : le lieu est-il seulement COLLECTABLE ? `items_query`
        # exige des coordonnées, le plancher compte les langues. Entre une
        # « ancienne commune » et la « commune nouvelle » qui l'a absorbée, ce
        # sont ces deux chiffres qui tranchent, pas la description.
        utiles = _entity_usefulness(client, homonymes)
        ambigus = {
            nom: [(q, _decrire(lab, descriptions.get(q), utiles.get(q)))
                  for q, lab in couples]
            for nom, couples in ambigus.items()
        }
    return trouves, ambigus


def _decrire(libelle: str, description: str | None, langues: int | None) -> str:
    morceaux = [libelle]
    if description:
        morceaux.append(description)
    morceaux.append(
        "SANS COORDONNÉES, incollectable" if langues is None
        else f"{langues} langue{'s' if langues > 1 else ''}"
    )
    return " — ".join(morceaux)


def _entity_usefulness(client, qids: list[str]) -> dict[str, int]:
    """Langues de chaque entité, pour celles qui portent des coordonnées.

    Absente du résultat = sans coordonnées, donc impossible à collecter : c'est
    le critère le plus tranchant, et il ne demande aucun jugement.
    """
    langues: dict[str, int] = {}
    for batch in wd.chunked(qids, 150):
        try:
            for row in client.query(wd.items_query(batch)):
                qid = wd.qid_from_uri(row.get("item"))
                if qid:
                    langues[qid] = int(row.get("sitelinks") or 0)
        except Exception as erreur:  # noqa: BLE001
            LOG.debug("langues indisponibles (%s)", erreur)
    return langues


def _entity_descriptions(client, qids: list[str]) -> dict[str, str]:
    descriptions: dict[str, str] = {}
    for batch in wd.chunked(qids, 200):
        try:
            for row in client.query(wd.entity_labels_query(batch)):
                qid = wd.qid_from_uri(row.get("item"))
                if qid and row.get("itemDescription"):
                    descriptions[qid] = row["itemDescription"]
        except Exception as erreur:  # noqa: BLE001 — sans description, on affiche moins
            LOG.debug("descriptions indisponibles (%s)", erreur)
    return descriptions


def cmd_resolve_list(args: argparse.Namespace, config: Config) -> int:
    """Retrouve les Q-ids d'une liste de noms dans la collecte.

    Certaines listes officielles existent sur le site du ministère sans exister
    chez Wikidata : les Grands Sites de France y sont dix-neuf, alors que le
    label en compte bien davantage. Il faut donc les saisir à la main — et les
    saisir veut dire trouver un Q-id par nom, ce qui à cinquante lignes n'est
    pas une opération manuelle raisonnable.

    La plupart de ces lieux sont DÉJÀ collectés, sous un autre rattachement :
    l'identifiant se lit dans la collecte plutôt que de s'inventer.

    Le rapprochement par les mots est trompeur, et il faut le dire : « baie de
    Somme » couvre entièrement « chemin de fer de la baie de Somme », « gorges
    du Verdon » couvre « basses gorges du Verdon ». Seul un nom retrouvé MOT
    POUR MOT est écrit sans demander ; tout le reste est proposé, avec ses
    concurrents, et attend un arbitrage.
    """
    raw_path = args.out / "places_raw.json"
    if not raw_path.exists():
        print(f"{raw_path} absent — lance d'abord `fetch`.", file=sys.stderr)
        return 1

    noms = [
        ligne.strip()
        for ligne in (args.file.read_text(encoding="utf-8").splitlines()
                      if args.file else sys.stdin.read().splitlines())
        if ligne.strip() and not ligne.startswith("#")
    ]
    if not noms:
        print("Aucun nom lu.", file=sys.stderr)
        return 1

    places = _load_places(raw_path)
    apply_names(places, read_names(args.manual / "names.csv"))

    surs: list[tuple[str, Place]] = []
    doutes: list[tuple[str, list[tuple[float, int, Place]]]] = []
    perdus: list[str] = []

    # Wikidata D'ABORD quand une classe est donnée. Une classe est une
    # contrainte exacte ; le rapprochement par les mots ne l'est pas, et il se
    # trompe de façon crédible : « Fontevraud-l'Abbaye » désigne une commune,
    # et la collecte n'en connaît que l'abbaye. Écrire ce Q-id-là dans une
    # liste de villages serait une erreur muette.
    ambigus: dict[str, list[tuple[str, str]]] = {}
    if args.classe:
        trouves, ambigus = _resolve_chez_wikidata(noms, args.classe)
        surs.extend(trouves)
        pris = {nom for nom, _ in trouves} | set(ambigus)
        noms = [nom for nom in noms if nom not in pris]
        if trouves:
            print(f"{len(trouves)} nom(s) résolus chez Wikidata "
                  f"(classe {args.classe}) :\n")
            for nom, place in trouves:
                print(f"    {place.wikidata_id:<11} {place.name}")
            print()

    for nom in noms:
        exacts: list[Place] = []
        proches: list[tuple[float, int, Place]] = []
        vus: set[str] = set()
        for variante in _variantes(nom):
            cible = _mots(variante)
            if not cible:
                continue
            classe = []
            for place in places:
                mots = _mots(place.name)
                part = len(cible & mots) / len(cible)
                if part >= args.seuil:
                    classe.append((part, len(mots - cible), place))
            classe.sort(key=lambda c: (-c[0], c[1], c[2].name))
            # Un périmètre peut désigner PLUSIEURS lieux — « Cap d'Erquy - Cap
            # Fréhel » en désigne deux, et le label vaut pour les deux.
            if classe and classe[0][0] >= 1.0 and classe[0][1] == 0:
                if classe[0][2].wikidata_id not in vus:
                    vus.add(classe[0][2].wikidata_id)
                    exacts.append(classe[0][2])
            for candidat in classe[:3]:
                if candidat[2].wikidata_id not in vus:
                    vus.add(candidat[2].wikidata_id)
                    proches.append(candidat)
        if exacts:
            surs.extend((nom, place) for place in exacts)
        elif proches:
            proches.sort(key=lambda c: (-c[0], c[1], c[2].name))
            doutes.append((nom, proches[:3]))
        else:
            perdus.append(nom)

    for nom, candidats in ambigus.items():
        # Plusieurs communes portent ce nom : le choix est éditorial.
        doutes.append((nom, [(1.0, 0, _FauxLieu(q, lab)) for q, lab in candidats]))

    locaux = [couple for couple in surs if not isinstance(couple[1], _FauxLieu)]
    if locaux:
        print(f"{len(locaux)} nom(s) retrouvés mot pour mot dans la collecte :\n")
        for nom, place in locaux:
            print(f"    {place.wikidata_id:<11} {place.name}")

    if doutes:
        print(f"\n{len(doutes)} à trancher — le nom collecté n'est pas le même :\n")
        for nom, candidats in doutes:
            print(f"    « {nom} »")
            for part, extra, place in candidats:
                print(f"        {place.wikidata_id:<11} {place.name:<44} "
                      f"{part:.0%} du nom, {extra} mot(s) en plus")

    if perdus:
        print(f"\n{len(perdus)} sans correspondance :\n")
        for nom in perdus:
            print(f"    {nom}")
        if args.classe:
            print("\n  Ni dans la collecte, ni chez Wikidata sous cette classe.")
        print("\n  Résous-les chez Wikidata :"
              "\n      python -m roam_pipeline suggest-qids "
              + " ".join(f'"{n}"' for n in perdus[:3])
              + (" ..." if len(perdus) > 3 else ""))

    if not args.into:
        print("\n  Ajoute `--into <identifiant-du-label>` pour écrire les lignes sûres.")
        return 0

    chemin = args.manual / f"{args.into}.csv"
    connus = set()
    if chemin.exists():
        connus = {r["wikidata_id"] for r in read_csv_rows(chemin) if r.get("wikidata_id")}
    nouveaux = [(p, n) for n, p in surs if p.wikidata_id not in connus]
    with chemin.open("a" if chemin.exists() else "w", encoding="utf-8",
                     newline="") as sortie:
        if not connus:
            sortie.write("wikidata_id,name\r\n")
        for place, nom in nouveaux:
            sortie.write(f"{place.wikidata_id},{nom}\r\n")
    print(f"\n{len(nouveaux)} ligne(s) ajoutées à {chemin}.")
    print("  Cette liste COMPLÈTE ce que Wikidata rend, elle ne le remplace pas.")
    if doutes:
        print("  Les cas à trancher n'y sont PAS : ajoute-les toi-même une fois choisis.")
    return 0


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

    raw_path = args.out / "places_raw.json"
    if not raw_path.exists():
        print(f"{raw_path} absent — lance d'abord `fetch`.", file=sys.stderr)
        return 1

    needle = _fold(args.name)
    everything = score_all(_load_places(raw_path), config)
    apply_names(everything, read_names(args.manual / "names.csv"))
    # Le redressement de thème aussi : sans lui, `explain` annonce le thème que
    # le pipeline aurait choisi et non celui qui vaut, ce qui est exactement le
    # contraire de son rôle.
    everything, _inconnus = apply_themes(
        everything, read_themes(args.manual / "themes.csv"),
        {theme.id for theme in config.themes},
    )
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
        kept, _counts = apply_decisions(everything, decisions, strict=args.strict)
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

    print("\nThème faux ? `retheme <Q-id> <thème>` le redresse durablement.")
    return 0


def cmd_build(args: argparse.Namespace, config: Config) -> int:
    return _build_and_write(args, config)


def cmd_apply_review(args: argparse.Namespace, config: Config) -> int:
    """Enregistre les décisions d'une revue, puis reconstruit."""
    fresh = read_review_csv(args.review)
    unknown = {d for d, _ in fresh.values()} - set(DECISIONS) - {CLEAR}
    if unknown:
        print(f"Décisions inconnues, ignorées : {', '.join(sorted(unknown))}", file=sys.stderr)
        fresh = {q: v for q, v in fresh.items() if v[0] in DECISIONS or v[0] == CLEAR}

    # `clear` n'est pas un verdict qu'on enregistre : c'est un verdict qu'on
    # efface. Sans lui, revenir sur un `demote` demandait d'ouvrir le CSV à la
    # main — et un curateur qui doit éditer un fichier pour se dédire finit par
    # ne plus se dédire.
    effaces = {qid for qid, (verdict, _n) in fresh.items() if verdict == CLEAR}
    fresh = {qid: v for qid, v in fresh.items() if v[0] != CLEAR}

    # Les redressements de thème voyagent dans la même feuille mais dans leur
    # propre colonne : ranger et écarter sont deux gestes différents.
    valides = {theme.id for theme in config.themes}
    fresh_themes = read_review_themes(args.review)
    inconnus = {t for t in fresh_themes.values()} - valides
    if inconnus:
        print(f"Thèmes inconnus, ignorés : {', '.join(sorted(inconnus))}", file=sys.stderr)
        fresh_themes = {q: t for q, t in fresh_themes.items() if t in valides}

    if not fresh and not fresh_themes and not effaces:
        print("Aucune décision renseignée dans la feuille de revue.", file=sys.stderr)
        return 1

    path = args.manual / "decisions.csv"
    decisions = read_decisions(path)
    before = len(decisions)
    changed = sum(1 for qid, d in fresh.items() if decisions.get(qid, ("", ""))[0] != d[0])
    # La revue la plus récente l'emporte : revenir sur un verdict doit se faire
    # en relisant le lieu, pas en éditant un fichier.
    decisions.update(fresh)
    retires = [qid for qid in effaces if decisions.pop(qid, None) is not None]

    names = {p.wikidata_id: p.name for p in _load_places(args.out / "places_raw.json")}
    write_decisions(path, decisions, names)
    print(f"{len(fresh)} décisions lues, {changed} nouvelles ou modifiées "
          f"({before} → {len(decisions)} au total dans {path.name}).")
    if retires:
        print(f"{len(retires)} décisions RETIRÉES : le lieu retrouve son "
              "classement automatique.")

    bouge = 0
    if fresh_themes:
        themes_path = args.manual / "themes.csv"
        themes = read_themes(themes_path)
        bouge = sum(1 for q, t in fresh_themes.items() if themes.get(q, ("",))[0] != t)
        for qid, theme in fresh_themes.items():
            themes[qid] = (theme, themes.get(qid, ("", ""))[1])
        write_themes(themes_path, themes)
        print(f"{len(fresh_themes)} thèmes redressés, {bouge} nouveaux ou modifiés "
              f"({len(themes)} au total dans {themes_path.name}).")

    apporte = changed + len(retires) + bouge
    if not apporte:
        # Une feuille qui n'apporte rien n'est pas anodine : c'est presque
        # toujours qu'on a rejoué un ANCIEN téléchargement. Chrome numérote les
        # doublons — « review-decisions (1).csv » — et le premier de la liste
        # est le plus vieux. Photographier les niveaux dans ce cas effacerait
        # le repère qui aurait permis de s'en apercevoir.
        print(f"\n⚠ {args.review.name} n'apporte AUCUNE décision nouvelle.",
              file=sys.stderr)
        recents = sorted(args.review.parent.glob("*.csv"),
                         key=lambda f: f.stat().st_mtime, reverse=True)[:4]
        if recents:
            print("  Fichiers du dossier, du plus récent au plus ancien :",
                  file=sys.stderr)
            for f in recents:
                age = datetime.fromtimestamp(f.stat().st_mtime).strftime("%d/%m à %H:%M")
                print(f"      {age}   {f.name}", file=sys.stderr)
        print("  Les niveaux ne sont PAS photographiés : le repère de ta "
              "dernière revue reste\n  en place, et tu peux réessayer avec le "
              "bon fichier.", file=sys.stderr)
        return _build_and_write(args, config)

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
        snapshot_path = args.manual / "tiers.csv"
        # Photographier un catalogue plus maigre que le précédent effacerait la
        # trace des lieux que cette machine n'a pas collectés : au prochain
        # `build` sur la machine complète, des centaines de lieux déjà relus
        # reviendraient marqués « nouveau ». Les décisions, elles, s'ajoutent
        # sans rien détruire — on les écrit dans tous les cas.
        ancien = read_snapshot(snapshot_path)
        manque = len(ancien) - len(finales)
        if ancien and manque > max(20, len(ancien) // 50):
            print(f"⚠ Niveaux NON enregistrés : ce catalogue compte {len(finales)} "
                  f"lieux contre {len(ancien)} dans le dernier instantané. "
                  "Cette machine n'a pas tout collecté ; réécrire les niveaux "
                  "ferait passer les lieux manquants pour disparus.")
            print("  Tes décisions, elles, sont bien enregistrées dans "
                  "decisions.csv — pense à les committer.")
            return status
        write_snapshot(
            snapshot_path,
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
#
# Zéro et un en font partie, et il a fallu en avoir besoin pour s'en apercevoir.
# L'échelle commençait à deux — le plancher de collecte le plus bas déjà écrit —
# si bien qu'à la question « combien de plages Wikidata décrit-il SOUS notre
# plancher ? », la commande répondait par le silence. Or c'est exactement la
# question qui décide s'il vaut la peine de descendre : les plages de la Côte
# d'Azur manquent au catalogue, et rien ne disait si elles manquaient parce que
# le plancher les coupe ou parce que Wikidata les ignore. Un outil de mesure
# qui ne sait pas mesurer en dessous de l'existant ne peut rien conseiller.
THRESHOLDS = [0, 1, 2, 3, 4, 6, 8, 10, 12, 15, 20]


def cmd_retention(args: argparse.Namespace, config: Config) -> int:
    """La collecte a-t-elle manqué un thème, ou est-ce le tri qui l'a vidé ?

    Deux causes très différentes produisent le même symptôme — un thème
    maigre — et elles appellent des remèdes opposés. Le TAUX DE RÉTENTION les
    sépare : ce que le catalogue garde de ce que la collecte a trouvé.

    Un thème qui garde neuf dixièmes de sa collecte n'est pas trié, il est
    affamé : la requête SPARQL ne lui a rien apporté de plus, et c'est en
    amont qu'il faut chercher — une classe Wikidata manquante, un plancher de
    collecte trop haut. Un thème qui en garde un dixième est richement
    pourvu ; ses absents ont été écartés, et `explain` dira par quoi.

    Cette commande ne demande pas le réseau : elle compare la collecte
    versionnée au catalogue construit. Le recensement des classes qui nous
    échappent, lui, est le travail de `gaps`.
    """
    from .raw import read_raw

    brut = read_raw(args.raw)
    if not brut:
        print(f"{args.raw} vide — lance d'abord `fetch` puis `sync`.", file=sys.stderr)
        return 1
    places_path = args.out / "places.json"
    if not places_path.exists():
        print(f"{places_path} absent — lance d'abord `build`.", file=sys.stderr)
        return 1

    collectes = Counter(place.theme_id for place in brut)
    # Le plus bas nombre de langues réellement collecté. S'il dépasse le
    # plancher configuré, la collecte a été faite AVANT que le réglage ne
    # baisse : le thème est amputé de tout ce qui vit entre les deux, et rien
    # ne le disait. Les gorges en perdaient vingt-huit sur soixante-deux.
    plancher_reel: dict[str, int] = {}
    for place in brut:
        courant = plancher_reel.get(place.theme_id)
        if courant is None or place.sitelinks < courant:
            plancher_reel[place.theme_id] = place.sitelinks
    retenus = Counter(
        place["theme_id"] for place in json.loads(places_path.read_text("utf-8"))
    )

    lignes = []
    perimes: list[tuple[str, int, int]] = []
    for theme in config.themes:
        n = collectes.get(theme.id, 0)
        if not n:
            continue
        garde = retenus.get(theme.id, 0)
        lignes.append((garde / n, theme, n, garde))
        bas = plancher_reel.get(theme.id)
        if bas is not None and bas > theme.fetch_min_sitelinks:
            perimes.append((theme.id, theme.fetch_min_sitelinks, bas))

    print(f"{'thème':16s} {'genre':8s} {'collectés':>10s} {'retenus':>8s} "
          f"{'gardés':>8s} {'plancher':>9s} {'classes':>8s}")
    for taux, theme, n, garde in sorted(lignes, key=lambda t: -t[0]):
        affame = (taux >= args.seuil and n < args.rare and not theme.from_labels)
        alerte = "  ← affamé" if affame else (
            "  (listes)" if theme.from_labels else "")
        print(f"{theme.id:16s} {theme.kind:8s} {n:10d} {garde:8d} "
              f"{100 * taux:7.0f} % {theme.fetch_min_sitelinks:9d} "
              f"{len(theme.wikidata_classes):8d}{alerte}")

    # Un thème alimenté par des listes officielles garde forcément presque tout
    # ce qu'on lui apporte : sa source est une curation humaine, finie et déjà
    # triée. Les Plus Beaux Villages gardent 99 % — ce n'est pas une famine,
    # c'est le principe.
    if perimes:
        print(f"\n{len(perimes)} thème(s) dont la COLLECTE est plus haute que le "
              f"réglage actuel — le plancher a baissé depuis, sans recollecte :\n")
        for theme_id, regle, reel in perimes:
            print(f"    {theme_id} : réglé à {regle} langues, collecté à partir "
                  f"de {reel}")
        print("\n    Tout ce qui vit entre les deux manque, et rien ne le disait."
              "\n    python -m roam_pipeline fetch --only "
              + ",".join(t for t, _r, _b in perimes))

    affames = [
        (theme, n) for taux, theme, n, _g in sorted(lignes, key=lambda t: -t[0])
        if taux >= args.seuil and n < args.rare and not theme.from_labels
    ]
    if affames:
        print(f"\n{len(affames)} thème(s) où c'est la COLLECTE qui limite, pas le "
              f"tri — le catalogue garde {args.seuil:.0%} ou plus de ce qu'on lui "
              f"apporte :\n")
        for theme, n in affames:
            classes = ", ".join(theme.wikidata_classes) or "aucune"
            print(f"    {theme.name} — {n} candidats, {len(theme.wikidata_classes)} "
                  f"classe(s) : {classes}")
        print("\n  Le premier suspect est le PLANCHER DE COLLECTE, pas les classes :"
              "\n  la requête suit déjà `P31/P279*`, donc les sous-classes remontent"
              "\n  toutes seules. Ajouter « chute d'eau côtière » à côté de « chute"
              "\n  d'eau » ne rapporterait rien."
              "\n"
              "\n  Déclarer une classe ne se justifie que là où Wikidata ne pose PAS"
              "\n  la sous-classe : « musée d'art » n'est pas déclaré sous « musée »,"
              "\n  et 55 musées sur 62 manquaient, dont le Petit Palais."
              "\n"
              "\n  Mesurer avant de recollecter — cette commande dit ce que chaque"
              "\n  plancher rapporterait, sans rien changer :"
              "\n      python -m roam_pipeline gaps --class <QID>")
    return 0


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


def cmd_pertes(args: argparse.Namespace, config: Config) -> int:
    """Quels redressements de thème ont fait DISPARAÎTRE un lieu ?

    Ranger un lieu ailleurs, c'est le soumettre au plancher de son nouveau
    thème et le mettre en concurrence avec de nouveaux voisins. Les arènes
    d'Arles, passées de `monuments` à `megalithes`, se sont retrouvées à
    vingt-deux mètres de la fiche « Monuments romains et romans d'Arles » —
    une inscription UNESCO, pas une visite — qui score plus haut et les a
    évincées. Vingt langues, un des monuments les plus fréquentés de France,
    disparu du catalogue sans un mot.

    C'est le seul geste de la revue dont l'effet peut être destructeur sans
    être visible : un `drop` retire un lieu et le curateur le sait.

    Deux constructions, avec et sans `themes.csv`, et la comparaison nomme le
    rival qui a gagné la place.
    """
    raw_path = args.out / "places_raw.json"
    if not raw_path.exists():
        print(f"{raw_path} absent — lance d'abord `sync` ou `fetch`.", file=sys.stderr)
        return 1

    themes = read_themes(args.manual / "themes.csv")
    if not themes:
        print("Aucun redressement de thème enregistré.")
        return 0

    decisions = read_decisions(args.manual / "decisions.csv")
    valides = {theme.id for theme in config.themes}

    def construire(avec_themes):
        places = _load_places(raw_path)
        apply_names(places, read_names(args.manual / "names.csv"))
        places, _ = apply_themes(places, themes if avec_themes else {}, valides)
        scored = score_all(places, config)
        kept, _counts = apply_decisions(scored, decisions)
        score_all(kept, config)
        with _silence():
            retenus, _collections = build_all(kept, config)
        return {p.wikidata_id: p for p in retenus}, {p.wikidata_id: p for p in kept}

    apres, candidats = construire(True)
    avant, _ = construire(False)

    perdus = [qid for qid in themes if qid in avant and qid not in apres]
    if not perdus:
        print(f"{len(themes)} redressements, aucun n'écarte de lieu du catalogue.")
        return 0

    print(f"{len(themes)} redressements, dont {len(perdus)} qui ÉCARTENT le lieu "
          f"du catalogue :\n")
    for qid in sorted(perdus, key=lambda q: -avant[q].score):
        perdu = candidats.get(qid) or avant[qid]
        theme_avant = avant[qid].theme_id
        theme_apres = themes[qid][0]
        # Le Q-id, sans quoi les trois remèdes proposés plus bas ne sont pas
        # exécutables : il faut aller le rechercher dans la collecte.
        print(f"  {perdu.name}  ({qid}, {perdu.sitelinks} langues, score "
              f"{perdu.score:.0f})")
        print(f"      {theme_avant} → {theme_apres}")
        # Le rival : le lieu du NOUVEAU thème, à portée de dédoublonnage, qui
        # est resté. C'est presque toujours lui la cause.
        rivaux = [
            place for place in apres.values()
            if place.theme_id == theme_apres
            and haversine_m(perdu.lat, perdu.lon, place.lat, place.lon)
            < DUPLICATE_DISTANCE_M
        ]
        if rivaux:
            for rival in sorted(rivaux, key=lambda p: -p.score):
                distance = haversine_m(perdu.lat, perdu.lon, rival.lat, rival.lon)
                print(f"      évincé par « {rival.name} » ({rival.wikidata_id}) "
                      f"à {distance:.0f} m (score {rival.score:.0f})")
        else:
            plancher = config.theme(theme_apres).min_sitelinks
            if perdu.sitelinks < plancher:
                print(f"      sous le plancher de {theme_apres} "
                      f"({perdu.sitelinks} langues pour {plancher})")
            else:
                print("      cause à chercher : `explain` donnera l'étape")
        print()

    print("Trois issues, au choix :")
    print("    retheme <Q-id> --clear     revenir au rattachement d'avant. C'est")
    print("                               souvent le bon remède : dans un AUTRE")
    print("                               thème que son rival, le lieu survit,")
    print("                               le dédoublonnage ne comparant qu'à")
    print("                               l'intérieur d'un thème.")
    print("    decisions.csv : drop       écarter la fiche du rival, quand c'est")
    print("                               elle qui décrit mal la visite")
    print("    pin <Q-id>                 le lieu passe outre les planchers")
    return 0


def cmd_adjustments(args: argparse.Namespace, config: Config) -> int:
    """Audite les `promote` et `demote` : lesquels ne produisent rien ?

    Un déplacement d'un niveau ne peut rien faire quand il n'y a plus de place
    pour bouger : un `promote` sur un lieu déjà au niveau 1, un `demote` sur un
    niveau 3. La décision reste enregistrée et ne change rien.

    Il faut construire DEUX fois pour le savoir, avec et sans les déplacements.
    Regarder le seul niveau final ne suffit pas : un lieu descendu de 2 à 3 s'y
    lit comme un lieu bloqué, et l'audit annonçait alors soixante-dix-sept
    décisions inutiles là où il y en avait seize.
    """
    raw_path = args.out / "places_raw.json"
    if not raw_path.exists():
        print(f"{raw_path} absent — lance d'abord `sync` ou `fetch`.", file=sys.stderr)
        return 1

    decisions = read_decisions(args.manual / "decisions.csv")
    bouges = {q: d for q, (d, _n) in decisions.items() if d in ("promote", "demote")}
    if not bouges:
        print("Aucun `promote` ni `demote` enregistré.")
        return 0

    def construire(deci):
        places = _load_places(raw_path)
        apply_names(places, read_names(args.manual / "names.csv"))
        places, _ = apply_themes(places, read_themes(args.manual / "themes.csv"),
                                 {theme.id for theme in config.themes})
        scored = score_all(places, config)
        kept, _counts = apply_decisions(scored, deci, strict=args.strict)
        score_all(kept, config)
        with _silence():
            retenus, collections = build_all(kept, config)
        return ({p.wikidata_id: p.name for p in retenus}, review_tiers(collections))

    # Les noms viennent du catalogue BRUT : un lieu qu'un plancher écarte n'est
    # dans aucune des deux constructions, et l'audit affichait alors son Q-id.
    noms = {place.wikidata_id: place.name for place in _load_places(raw_path)}
    apply_names_ok, apres = construire(decisions)
    noms.update(apply_names_ok)
    # Sans les déplacements, mais AVEC les `drop` : sinon la comparaison
    # porterait sur deux catalogues de tailles différentes.
    immobiles = {q: v for q, v in decisions.items() if v[0] in ("drop", "keep")}
    noms_sans, avant = construire(immobiles)
    noms = {**noms, **noms_sans, **apply_names_ok}

    bloques, hors, agissants = [], [], 0
    for qid, verdict in sorted(bouges.items(), key=lambda kv: noms.get(kv[0], kv[0])):
        if qid not in apres:
            hors.append((qid, verdict))
        elif apres[qid] != avant.get(qid):
            agissants += 1
        else:
            bloques.append((qid, verdict, apres[qid]))

    print(f"{len(bouges)} déplacements enregistrés "
          f"({sum(1 for v in bouges.values() if v == 'promote')} promote, "
          f"{sum(1 for v in bouges.values() if v == 'demote')} demote), "
          f"dont {agissants} qui déplacent effectivement un lieu.\n")

    if hors:
        print(f"{len(hors)} portent sur un lieu ABSENT du catalogue :")
        for qid, verdict in hors:
            print(f"    {noms.get(qid, qid)[:48]:<50} {verdict}")
        print("    Un plancher ou un filtre les écarte. La décision ne produit "
              "rien.\n")

    if bloques:
        print(f"{len(bloques)} sont AU BOUT de l'échelle et n'ont pas bougé :")
        for qid, verdict, niveau in bloques:
            print(f"    {noms.get(qid, qid)[:48]:<50} {verdict}, niveau {niveau}")
        print("    Il n'y a pas de niveau 4. Si c'est un rejet, c'est `drop` "
              "qu'il faut écrire.\n")

    if not hors and not bloques:
        print("Tous déplacent effectivement un lieu d'un niveau.")
    return 0


def cmd_weigh(args: argparse.Namespace, config: Config) -> int:
    """Montre ce qu'un poids ferait au catalogue, sans rien adopter.

    Un signal nouveau ne se règle pas au jugé : on le collecte, on le regarde
    peser sur les lieux qu'on connaît, et on choisit le poids en voyant qui
    monte et qui descend. Le poids réel reste celui de `scoring.yaml` tant
    qu'on ne l'y écrit pas.
    """
    raw_path = args.out / "places_raw.json"
    if not raw_path.exists():
        print(f"{raw_path} absent — lance d'abord `sync` ou `fetch`.", file=sys.stderr)
        return 1

    base = _load_places(raw_path)
    renseignes = [p for p in base if p.pageviews_per_month]
    print(f"Consultations connues : {len(renseignes)} lieux sur {len(base)} "
          f"({len(renseignes) / len(base) * 100:.0f} %)")
    # La donnée n'est indispensable que si on lui donne du poids : peser les
    # seules langues doit rester possible sur un catalogue non enrichi.
    if not renseignes and any(args.weights):
        print("\nAucune donnée. Lance d'abord :\n"
              "    python -m roam_pipeline enrich --pageviews", file=sys.stderr)
        return 1

    vues = sorted(p.pageviews_per_month for p in renseignes)
    for nom, rang in (("médiane", 0.5), ("9ᵉ décile", 0.9), ("maximum", 1.0)):
        if vues:
            print(f"  {nom:<12} {vues[min(int(rang * len(vues)), len(vues) - 1)]:>9} vues/mois")

    # Le signal des consultations recoupe largement celui des langues : les
    # ajouter l'un à l'autre renforce ce qu'ils ont en commun — la célébrité —
    # au lieu de corriger ce qui les sépare. D'où `--sitelinks`, qui permet de
    # DÉPLACER du poids de l'un vers l'autre au lieu d'en empiler.
    classements: dict[tuple[float, float], list[tuple[int, str, float, int | None]]] = {}
    globaux: dict[tuple[float, float], tuple[int, int, int, int, int]] = {}
    couples = [(v, s, r) for v in args.weights
               for s in (args.sitelinks or [config.scoring.sitelinks_weight])
               for r in (args.rescue or [config.scoring.rescue_score])]
    for poids, langues, repechage in couples:
        essai = replace(
            config,
            pageviews=replace(config.pageviews, weight=poids),
            scoring=replace(config.scoring, sitelinks_weight=langues,
                            rescue_score=repechage),
        )
        places = _load_places(raw_path)
        apply_names(places, read_names(args.manual / "names.csv"))
        places, _ = apply_themes(places, read_themes(args.manual / "themes.csv"),
                                 {t.id for t in essai.themes})
        scored = score_all(places, essai)
        kept, _counts = apply_decisions(scored, read_decisions(args.manual / "decisions.csv"),
                                        strict=args.strict)
        score_all(kept, essai)
        with _silence():
            retenus, collections = build_all(kept, essai)
        par_id = {p.wikidata_id: p for p in retenus}
        nationale = next(
            (c for c in collections
             if c.kind == "theme" and c.theme_id == args.theme and not c.geo_code),
            None,
        )
        if nationale is None:
            print(f"\nAucune collection nationale pour « {args.theme} ».", file=sys.stderr)
            return 1
        # Baisser le poids des langues ne réordonne pas : ça baisse TOUS les
        # scores, donc déplace chaque seuil absolu de `scoring.yaml` — le
        # repêchage à 85 points, les planchers de niveau à 45 et 25. Un
        # classement plus juste qui vide le catalogue n'est pas un progrès.
        niveaux = Counter(m.tier for c in collections for m in c.places)
        globaux[(poids, langues, repechage)] = (
            len(retenus),
            len([p for p in retenus if rescued(p, essai)]),
            niveaux[1], niveaux[2], niveaux[3],
        )
        classements[(poids, langues, repechage)] = [
            (m.tier, par_id[m.place_id].name, par_id[m.place_id].score,
             par_id[m.place_id].pageviews_per_month)
            for m in nationale.places[: args.top]
        ]

    reference = {nom for _t, nom, _s, _v in classements[couples[0]]}
    for (poids, langues, repechage), lignes in classements.items():
        actuel = (" (réglage actuel)"
                  if poids == config.pageviews.weight
                  and langues == config.scoring.sitelinks_weight
                  and repechage == config.scoring.rescue_score else "")
        print(f"\n── consultations {poids:g} · langues {langues:g} · "
              f"repêchage {repechage:g}{actuel} ──")
        for rang, (tier, nom, score, vues_m) in enumerate(lignes, start=1):
            v = f"{vues_m:>7} vues" if vues_m else "      —     "
            marque = " " if nom in reference else "▲"
            print(f"  {marque} {rang:>2}. niveau {tier}  {score:>6.1f}  {v}  {nom}")
        partis = reference - {nom for _t, nom, _s, _v in lignes}
        if partis:
            print(f"     sortis du haut du classement : {', '.join(sorted(partis))}")

    print("\n── effet sur TOUT le catalogue ──")
    print(f'{"consult":>8}{"langues":>8}{"repêch.":>9}{"lieux":>8}{"écart":>9}'
          f'{"repêchés":>10}{"niveau 1":>10}{"niveau 2":>10}')
    base = globaux[couples[0]]
    for (poids, langues, rep), (lieux, repeches, n1, n2, _n3) in globaux.items():
        ecart = f"{lieux - base[0]:+d}" if lieux != base[0] else "—"
        print(f"{poids:>8g}{langues:>8g}{rep:>9g}{lieux:>8}{ecart:>9}"
              f"{repeches:>10}{n1:>10}{n2:>10}")
    print("\n  Un classement plus juste qui vide le catalogue n'est pas un progrès :")
    print("  `rescue_score`, `tier1_min_score` et `tier2_min_score` sont des seuils")
    print("  ABSOLUS. Baisser un poids les déplace tous.")

    print(f"\nRien n'a été modifié. Pour adopter un réglage, écris-le dans "
          f"`config/scoring.yaml`.")
    return 0


@contextmanager
def _silence():
    """Coupe le bruit d'une construction d'essai.

    Le tableau d'entonnoir et les avertissements de périmètre, répétés une fois
    par poids comparé, noieraient la mesure. Ils passent par le journal, donc
    par la sortie d'erreur : rediriger la sortie standard ne suffit pas.
    """
    tampon = io.StringIO()
    logging.disable(logging.CRITICAL)
    try:
        with redirect_stdout(tampon):
            yield
    finally:
        logging.disable(logging.NOTSET)


def cmd_merge(args: argparse.Namespace, config: Config) -> int:
    """Résout les conflits git des fichiers de curation.

    Deux soirées de relecture menées sur deux machines produisent deux versions
    du même fichier, et git ne sait pas les départager : il pose des marqueurs
    au milieu d'un travail que personne n'a perdu. Ces fichiers ne sont pas du
    texte mais des tables dont la clé est le Q-id — la fusion juste est l'union
    des deux côtés.
    """
    cibles = args.files or conflicted(args.manual)
    if not cibles:
        print(f"Aucun conflit dans {args.manual}.")
        return 0

    desaccords = 0
    for path in cibles:
        try:
            report = merge_file(path)
        except (OSError, ValueError) as exc:
            print(f"{path.name} : {exc}", file=sys.stderr)
            return 1
        if report is None:
            print(f"{path.name} : aucun marqueur de conflit, laissé tel quel.")
            continue
        print(f"{path.name} : {report.kept} lignes, dont {report.added} venues de l'autre "
              "machine.")
        for qid, mien, autre in report.disagreements:
            desaccords += 1
            print(f"  ⚠ {qid} : ici « {mien} », là-bas « {autre} » — j'ai gardé le tien.")

    if desaccords:
        # Ne pas fondre un désaccord dans un décompte : c'est le seul cas où la
        # machine a choisi à la place du curateur, il doit pouvoir y revenir.
        print(f"\n{desaccords} lieu(x) tranché(s) différemment des deux côtés. "
              "Relis-les si le doute demeure.")
    print("\nRelance `build` pour vérifier, puis `git add` et termine la fusion.")
    return 0


def cmd_fantomes(args: argparse.Namespace, config: Config) -> int:
    """Les lieux du catalogue dont le résumé dit que la chose n'est plus là.

    La revue se fait à plat, fiche par fiche, et il en reste toujours des
    centaines à lire : un lieu démoli au XVIIIe siècle peut y trôner des
    semaines au premier niveau d'un département. Ici la question est posée une
    fois, à tout le catalogue.
    """
    places_path = args.out / "places.json"
    if not places_path.exists():
        print(f"{places_path} absent — lance d'abord `build`.", file=sys.stderr)
        return 1

    places = _load_places(places_path)
    decisions = read_decisions(args.manual / "decisions.csv")
    trouves = fantomes(places)

    # Où le lieu siège : un fantôme au premier niveau d'une collection est
    # autrement plus urgent que le même au troisième.
    rangs: dict[str, list[str]] = defaultdict(list)
    collections_path = args.out / "collections.json"
    if collections_path.exists():
        for collection in json.loads(collections_path.read_text(encoding="utf-8")):
            for membre in collection["places"]:
                rangs[membre["place_id"]].append(
                    f"{collection['name']} N{membre['tier']}#{membre['rank']}")

    if not trouves:
        print("Aucun lieu suspect. (Le filet lit le français des résumés : "
              "il ne prouve rien, il rabat.)")
        return 0

    print(f"{len(trouves)} lieu(x) dont le résumé parle de disparition, "
          f"sur {len(places)} :\n")
    for place, motifs in trouves:
        verdict = decisions.get(place.wikidata_id, ("—", ""))[0]
        print(f"  {place.score or 0:>6.1f}  {place.wikidata_id:<11} {place.name}")
        print(f"          {', '.join(motifs)} · verdict actuel : {verdict}")
        for ou in rangs.get(place.wikidata_id, []):
            print(f"          {ou}")
        extrait = " ".join((place.summary or "").split())[:160]
        if extrait:
            print(f"          « {extrait}… »")
        print(f"          verdict {place.wikidata_id} drop --note \"...\"")
        print()

    print("Ce sont des CANDIDATS, pas des verdicts : le pont d'Avignon, dont il "
          "ne reste\nque quatre arches, se visite très bien. Vérifie chacun.")
    print("\nÉcarter un lieu promeut le suivant : relance après le prochain "
          "`build`.")
    return 0


def cmd_verdict(args: argparse.Namespace, config: Config) -> int:
    """Enregistre un verdict de curation sur un lieu, sans passer par la revue.

    `decisions.csv` est la mémoire de la curation, et jusqu'ici seule la page
    de revue savait y écrire. Retirer UN lieu repéré au détour d'une carte
    demandait d'ouvrir le fichier à la main — et un curateur qui doit éditer un
    CSV dans `nano` pour écarter un lieu finit par ne plus l'écarter.

    C'est le pendant de `pin` : un geste, un lieu, une raison. Le fichier reste
    trié et relisible, et la prochaine revue l'emporte toujours sur ce qu'on
    écrit ici — le verdict le plus récent gagne, comme partout ailleurs.
    """
    qid = (args.wikidata_id or "").strip()
    if not qid.startswith("Q") or not qid[1:].isdigit():
        print(f"« {qid} » n'est pas un identifiant Wikidata.", file=sys.stderr)
        return 1

    if not args.clear and args.decision not in DECISIONS:
        print(f"Verdict inconnu : {args.decision}. Verdicts valides : "
              + ", ".join(DECISIONS), file=sys.stderr)
        return 1

    places = read_raw(args.raw)
    connus = {place.wikidata_id: place.name for place in places}
    if qid not in connus:
        # Écarter un lieu absent de la collecte ne casse rien, mais c'est
        # presque toujours une faute de frappe sur l'identifiant.
        print(f"{qid} n'est pas dans la collecte — vérifie l'identifiant.",
              file=sys.stderr)
        return 1

    path = args.manual / "decisions.csv"
    decisions = read_decisions(path)
    avant = decisions.get(qid)

    if args.clear:
        if decisions.pop(qid, None) is None:
            print(f"{connus[qid]} ({qid}) n'avait aucun verdict.")
            return 0
    else:
        decisions[qid] = (args.decision, (args.note or "").replace(",", " ").strip())

    write_decisions(path, decisions, connus)

    nom = connus[qid]
    if args.clear:
        print(f"Verdict retiré sur {nom} ({qid}) — il était « {avant[0]} ».")
    elif avant and avant[0] != args.decision:
        print(f"{nom} ({qid}) : « {avant[0]} » devient « {args.decision} ».")
    else:
        print(f"{nom} ({qid}) : « {args.decision} » enregistré.")
    print("Enchaîne avec `build` pour que le catalogue en tienne compte.")
    return 0


def cmd_pin(args: argparse.Namespace, config: Config) -> int:
    """Épingle un lieu déjà collecté : il passe outre les planchers.

    `places.csv` désigne les lieux à ALLER CHERCHER, et n'est lu que par
    `fetch`. Y inscrire un lieu déjà collecté ne produit donc rien tant qu'on
    ne relance pas une demi-heure de collecte — le drapeau `pinned` vit dans
    `data/raw/`, pas dans la feuille.

    Cette commande le pose directement, comme `rename` pose un nom et
    `retheme` un rattachement. Le lieu franchit alors le plancher de notoriété
    ET le filtre alpin, et il l'emporte dans l'arbitrage entre thèmes.

    La ligne est aussi ajoutée à `places.csv` : sans elle, la prochaine
    collecte complète écraserait le drapeau sans un mot.
    """
    from .raw import read_raw, shard_of, shards, write_raw

    qid = (args.wikidata_id or "").strip()
    if not qid.startswith("Q") or not qid[1:].isdigit():
        print(f"« {qid} » n'est pas un identifiant Wikidata.", file=sys.stderr)
        return 1

    places = read_raw(args.raw)
    if not places:
        print(f"{args.raw} vide — lance d'abord `fetch` puis `sync`.", file=sys.stderr)
        return 1

    vises = [place for place in places if place.wikidata_id == qid]
    if not vises:
        print(f"{qid} n'est pas dans la collecte. Pour l'y faire entrer, "
              f"inscris-le dans {args.manual / 'places.csv'} puis relance "
              "`fetch`.", file=sys.stderr)
        return 1

    if args.theme:
        if args.theme not in {theme.id for theme in config.themes}:
            print(f"Thème inconnu : {args.theme}. Thèmes valides : "
                  + ", ".join(t.id for t in config.themes), file=sys.stderr)
            return 1
        vises = [place for place in vises if place.theme_id == args.theme] or vises

    if args.clear:
        touches = [place for place in vises if place.pinned]
        for place in touches:
            place.pinned = False
        if not touches:
            print(f"{qid} n'était pas épinglé.")
            return 0
    else:
        touches = [place for place in vises if not place.pinned]
        for place in touches:
            place.pinned = True
        if not touches:
            print(f"{qid} était déjà épinglé ({vises[0].name}).")
            return 0

    # `replacing` désigne les FICHIERS à réécrire, pas les thèmes. Épingler
    # déplace le lieu vers la réserve des ajouts — c'est la règle de
    # `shard_of` — et ne nommer que les thèmes le retirait de son fichier sans
    # jamais l'écrire ailleurs : le lieu disparaissait de la collecte.
    write_raw(args.raw, places,
              set(shards(args.raw)) | {shard_of(place) for place in places})
    verbe = "désépinglé" if args.clear else "épinglé"
    themes = ", ".join(sorted({place.theme_id for place in touches}))
    print(f"{vises[0].name} ({qid}) {verbe} dans {themes}.")

    if not args.clear:
        liste = args.manual / "places.csv"
        contenu = liste.read_bytes() if liste.exists() else b""
        if qid.encode() not in contenu:
            fin = b"" if contenu.endswith((b"\n", b"")) else b"\n"
            note = (args.note or "epingle a la main").replace(",", " ")
            ligne = f"{qid},{touches[0].theme_id},{note}\n".encode()
            with liste.open("ab") as fh:
                fh.write(fin + ligne)
            print(f"Inscrit dans {liste} — sans quoi la prochaine collecte "
                  "complète effacerait le drapeau.")
    print("Relance `build` pour en tenir compte.")
    return 0


def cmd_retheme(args: argparse.Namespace, config: Config) -> int:
    """Rattache un lieu au thème que le curateur juge juste.

    Le pipeline range d'après les classes Wikidata. C'est juste la plupart du
    temps, et faux quand la classe décrit une PARTIE du lieu : le musée
    Christian-Dior est classé « jardin » parce que la villa en a un remarquable.
    Wikidata n'a pas tort — c'est la hiérarchie des classes qui ne dit pas ce
    qu'on vient voir. Aucune règle générale ne rattrape cela, seul un humain le
    sait.
    """
    path = args.manual / "themes.csv"
    themes = read_themes(path)
    valides = {theme.id for theme in config.themes}

    if args.wikidata_id is None:
        if not themes:
            print("Aucun redressement. Usage : retheme Q123456 musees")
            print("Thèmes : " + ", ".join(sorted(valides)))
            return 0
        for qid in sorted(themes):
            theme, note = themes[qid]
            print(f"  {qid:<12} → {theme}" + (f"   ({note})" if note else ""))
        print(f"\n{len(themes)} redressement(s) dans {path}")
        return 0

    qid = args.wikidata_id.strip()
    if not qid.startswith("Q") or not qid[1:].isdigit():
        print(f"« {qid} » n'est pas un identifiant Wikidata.", file=sys.stderr)
        return 1

    if args.clear:
        if themes.pop(qid, None) is None:
            print(f"{qid} n'avait pas de thème choisi.")
            return 0
        write_themes(path, themes)
        print(f"{qid} reprend son rattachement automatique.")
        return 0

    if not args.theme_id:
        print("Il manque le thème. Usage : retheme Q123456 musees", file=sys.stderr)
        print("Thèmes : " + ", ".join(sorted(valides)), file=sys.stderr)
        return 1

    if args.theme_id not in valides:
        print(f"« {args.theme_id} » n'est pas un thème configuré.", file=sys.stderr)
        print("Thèmes : " + ", ".join(sorted(valides)), file=sys.stderr)
        return 1

    themes[qid] = (args.theme_id, args.note or "")
    write_themes(path, themes)
    print(f"{qid} appartiendra au thème « {args.theme_id} ».")
    print("Relance `build` : il quittera ses autres rattachements. La revue le "
          "signalera comme ayant CHANGÉ DE THÈME.")
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

    brouillon = args.out / AUTOSAVE

    class Revue(http.server.SimpleHTTPRequestHandler):
        """Sert la page, et RECUEILLE ce qu'elle décide.

        Faire dépendre une soirée de relecture d'un bouton qu'il faut penser à
        cliquer, puis d'un fichier qu'il faut reconnaître parmi ses homonymes
        numérotés par le navigateur, ne pouvait que casser. C'est arrivé deux
        fois, et la seconde a coûté une heure de travail.

        La page renvoie donc ses décisions au serveur à chaque clic. Elles sont
        écrites sur le disque, dans le dossier de sortie, et `apply-review` les
        y trouve sans qu'on ait à les nommer.
        """

        def end_headers(self):
            # La revue se sert toujours à la même adresse et son fichier change
            # à chaque `build` : sans cet en-tête, Chrome peut resservir la
            # version d'avant sans rien demander.
            self.send_header("Cache-Control", "no-store, must-revalidate")
            super().end_headers()

        def do_OPTIONS(self):  # noqa: N802 — nom imposé par http.server
            """Sonde de la page : le circuit répond-il, avant tout clic ?"""
            self.send_response(204 if self.path == "/decisions" else 404)
            self.end_headers()

        def do_POST(self):  # noqa: N802 — nom imposé par http.server
            if self.path != "/decisions":
                self.send_error(404)
                return
            taille = int(self.headers.get("Content-Length") or 0)
            if not 0 < taille <= 8_000_000:
                self.send_error(413)
                return
            corps = self.rfile.read(taille).decode("utf-8", errors="replace")
            # Un navigateur ne connaît que SA mémoire. Passer de Chrome au
            # navigateur Samsung, c'est repartir des seules décisions écrites
            # dans la page — et écraser le brouillon plus fourni qu'avait laissé
            # l'autre. On garde donc toujours la version la plus riche à côté.
            if brouillon.exists():
                ancien = brouillon.read_text(encoding="utf-8").count("\n")
                if ancien > corps.count("\n"):
                    brouillon.replace(brouillon.with_name("review-decisions.precedent.csv"))
            # Écriture atomique : une coupure de Wi-Fi au mauvais moment ne doit
            # pas laisser un fichier tronqué à la place du travail de la soirée.
            temporaire = brouillon.with_suffix(".part")
            temporaire.write_text(corps, encoding="utf-8")
            temporaire.replace(brouillon)
            self.send_response(204)
            self.end_headers()

        def log_message(self, *_args):
            return  # une ligne par clic noierait les messages utiles

    handler = functools.partial(Revue, directory=str(args.out))
    server = http.server.ThreadingHTTPServer((args.host, args.port), handler)
    url = f"http://127.0.0.1:{args.port}/review.html"

    # Sur certains Android, Chrome n'atteint pas la boucle locale d'une autre
    # application : la connexion est refusée alors que le serveur tourne. Passer
    # par l'adresse de l'appareil sur le Wi-Fi contourne le problème — la
    # requête sort et revient par l'interface réseau au lieu de rester à
    # l'intérieur.
    if args.host != "127.0.0.1":
        import socket

        try:
            sonde = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sonde.connect(("192.0.2.1", 1))  # adresse de documentation, rien n'est envoyé
            adresse = sonde.getsockname()[0]
            sonde.close()
            url = f"http://{adresse}:{args.port}/review.html"
        except OSError:
            pass
        print("⚠ Servie sur toutes les interfaces : n'importe qui sur ce réseau "
              "peut lire la page. À éviter hors de chez toi.")

    # Dire CE QU'ON RELIT avant de le relire. La page est construite depuis le
    # catalogue de CETTE machine : sur un clone où seuls quelques thèmes ont
    # été collectés, on peut passer une soirée entière à relire un cinquième du
    # catalogue sans que rien ne le signale.
    built = args.out / "places.json"
    if built.exists():
        places = json.loads(built.read_text(encoding="utf-8"))
        themes = {p.get("theme_id") for p in places}
        manquants = [t.id for t in config.themes if t.id not in themes]
        age = datetime.fromtimestamp(page.stat().st_mtime).strftime("%d/%m à %H:%M")
        print(f"Page construite le {age} : {len(places)} lieux, "
              f"{len(themes)} thèmes sur {len(config.themes)}.")
        if manquants:
            print(f"⚠ {len(manquants)} thèmes ABSENTS de cette page : "
                  + ", ".join(manquants[:8])
                  + (f" (+{len(manquants) - 8})" if len(manquants) > 8 else ""))
            print("  Cette machine ne les a jamais collectés. Tu relirais un "
                  "catalogue partiel.")
            print("  `git pull` puis `sync` les reprend du dépôt sans recollecter.")
        _compare_to_snapshot(len(places), args.manual / "tiers.csv")
        decidees = len(read_decisions(args.manual / "decisions.csv"))
        print(f"{decidees} décisions déjà prises y sont reportées : le filtre "
              "« À décider »")
        print("reprend donc là où tu t'es arrêté, et non au début.")

    print(f"Revue ouverte sur {url}")
    print(f"Tes décisions s'écrivent au fil des clics dans {brouillon.name}.")
    print("À l'arrêt : `apply-review` les reprendra sans que tu aies à les nommer.")
    threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nArrêté.")
    finally:
        server.server_close()
    return 0


def _compare_to_snapshot(built: int, snapshot_path: Path) -> None:
    """Dit si CE catalogue est plus maigre que celui qu'on a déjà relu.

    Le catalogue lui-même ne passe pas par git : chaque machine le reconstruit
    depuis sa propre collecte. `tiers.csv`, lui, est versionné — c'est la seule
    trace de la taille qu'avait le catalogue sur la machine qui a committé en
    dernier. La comparaison ne coûte rien et évite de relire un cinquième du
    travail en croyant le relire en entier.
    """
    snapshot = read_snapshot(snapshot_path)
    if not snapshot:
        return
    ecart = len(snapshot) - built
    print(f"Dernier catalogue relu et committé : {len(snapshot)} lieux.")
    # 2 % : le catalogue bouge d'une poignée de lieux entre deux revues sans
    # que rien n'aille mal. Au-delà, c'est une collecte qui manque.
    if ecart > max(20, len(snapshot) // 50):
        print(f"⚠ Il en manque {ecart} ici. Cette machine n'a pas tout collecté "
              "— relance `fetch` sur les thèmes concernés avant de relire.")


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

    rapproches_total = sum(1 for p in places if getattr(p, "osm_id", None))
    if not rapproches_total and places:
        # Sans la couche OpenStreetMap, DEUX mécanismes disparaissent en
        # silence : le filtre d'accès n'écarte plus rien, et le repêchage —
        # qui exige un accueil du public attesté — ne sauve plus personne.
        # Le catalogue rétrécit de plusieurs centaines de lieux sans qu'aucune
        # ligne ne dise pourquoi.
        print("\n⚠ AUCUNE donnée OpenStreetMap : ni ouverture au public, ni "
              "accès refusé.")
        print("    Le filtre d'accès n'écarte rien et le repêchage ne sauve "
              "personne — plusieurs")
        print("    centaines de lieux manquent au catalogue sans autre "
              "explication.")
        print("    Cette machine n'a pas `data/out/candidates.csv` ni "
              "`data/manual/candidates.csv`.")
        print("    Récupère-les de la machine qui a lancé `discover`, ou "
              "relance `discover` puis `adopt`.")

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
    parser.add_argument("--raw", type=Path, default=DEFAULT_RAW,
                        help="collecte versionnée, un fichier par thème")
    parser.add_argument("-v", "--verbose", action="store_true")

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("verify-qids", help="vérifie les Q-ids de la configuration (réseau requis)")

    suggest = sub.add_parser(
        "suggest-qids", help="propose des Q-ids pour les termes en attente (réseau requis)"
    )
    suggest.add_argument(
        "terms", nargs="*",
        help="termes à chercher — un PRÉFIXE de libellé, pas des mots-clés : "
             "« forêt de Bercé » ou « Bercé », jamais « forêt Bercé » "
             "(défaut : les termes en attente dans la config)")
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
        "--pageviews",
        action="store_true",
        help="ajouter les consultations Wikipédia (une requête par article)",
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
    discover.add_argument(
        "--cells", type=int, metavar="N",
        help="n'interroger que les N premières cellules. Vérifier qu'une requête "
             "rapporte quelque chose ne demande pas quarante cellules : deux "
             "suffisent, et coûtent une minute au lieu de dix.",
    )
    discover.add_argument(
        "--only", metavar="THÈMES",
        help="ne demander à Overpass que les tags de ces thèmes, séparés par des "
             "virgules (ex. cascades). Vérifier une hypothèse sur les cascades ne "
             "demande pas de rapporter neuf cents musées. L'ouverture au public du "
             "catalogue n'est alors PAS mise à jour : la collecte n'a vu qu'une "
             "catégorie d'objets.",
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
            "--strict",
            action="store_true",
            help="ne garder que les lieux explicitement relus",
        )

    build = sub.add_parser("build", help="score, construit les collections et exporte")
    add_decision_args(build)

    sub.add_parser(
        "relabel",
        help="rappose les labels sur la collecte, sans la recollecter (réseau requis)",
    )

    resolve = sub.add_parser(
        "resolve-list",
        help="retrouve les Q-ids d'une liste de noms dans la collecte",
    )
    resolve.add_argument("file", nargs="?", type=Path,
                         help="fichier de noms, un par ligne (défaut : entrée standard)")
    resolve.add_argument("--into", help="identifiant du label où écrire les lignes trouvées")
    resolve.add_argument("--seuil", type=float, default=0.6,
                         help="part des mots du nom à retrouver (défaut 0,6)")
    resolve.add_argument("--classe", metavar="Q-ID",
                         help="cherche aussi chez Wikidata parmi les instances de "
                              "cette classe (réseau requis) — ex. Q484170 pour une "
                              "commune française")

    explain = sub.add_parser(
        "explain", help="dit pourquoi un lieu est dans le catalogue, ou pourquoi il n'y est pas"
    )
    explain.add_argument("name", help="tout ou partie du nom du lieu")
    explain.add_argument("--limit", type=int, default=5, help="correspondances affichées")
    add_decision_args(explain)

    review = sub.add_parser("apply-review", help="enregistre les décisions d'une revue")
    review.add_argument("--review", type=Path, help="chemin de review.csv")
    add_decision_args(review)

    tenue = sub.add_parser(
        "retention",
        help="la collecte a-t-elle manqué un thème, ou le tri l'a-t-il vidé ?")
    tenue.add_argument(
        "--seuil", type=float, default=0.6,
        help="taux de rétention au-delà duquel un thème est dit affamé (défaut 0,6)")
    tenue.add_argument(
        "--rare", type=int, default=120,
        help="nombre de candidats en deçà duquel le thème est jugé maigre")

    gaps = sub.add_parser(
        "gaps",
        help="quelles classes de lieux nous échappent ? (réseau requis, long)",
    )
    gaps.add_argument(
        "--min-sitelinks", type=int, default=12,
        help="notoriété minimale des lieux recensés (défaut 12 ; plus bas = plus "
             "long). Sans effet avec --class, qui parcourt sa propre échelle de "
             "planchers, zéro compris.",
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

    audit = sub.add_parser(
        "adjustments", help="audite les promote/demote : servent-ils encore ?")
    add_decision_args(audit)

    balance = sub.add_parser(
        "weigh", help="montre ce qu'un poids de consultations ferait au classement")
    balance.add_argument("--theme", default="jardins", help="thème à observer")
    balance.add_argument("--weights", type=float, nargs="+", default=[0, 8, 16, 24],
                         help="poids de consultations à comparer")
    balance.add_argument("--sitelinks", type=float, nargs="+",
                         help="poids de notoriété à comparer, pour en DÉPLACER "
                              "vers les consultations plutôt qu'en empiler")
    balance.add_argument("--rescue", type=float, nargs="+",
                         help="seuils de repêchage à comparer : baisser un poids "
                              "baisse tous les scores, donc vide le catalogue "
                              "si ce seuil ABSOLU ne suit pas")
    balance.add_argument("--top", type=int, default=12, help="lieux affichés par poids")
    add_decision_args(balance)

    fusion = sub.add_parser(
        "merge", help="résout les conflits git des fichiers de curation")
    fusion.add_argument("files", nargs="*", type=Path,
                        help="fichiers à fusionner ; par défaut ceux de data/manual")

    sonde = sub.add_parser(
        "label-probe",
        help="par quelle propriété un label rattache-t-il ses membres ? (réseau requis)")
    sonde.add_argument("wikidata_id")

    sub.add_parser(
        "fantomes",
        help="lieux du catalogue dont le résumé dit qu'ils n'existent plus")

    verdict = sub.add_parser(
        "verdict",
        help="écarte ou valide un lieu sans passer par la revue (keep, drop, "
             "promote, demote)")
    verdict.add_argument("wikidata_id")
    verdict.add_argument("decision", nargs="?", default="",
                         help="keep, drop, promote ou demote")
    verdict.add_argument("--note", help="pourquoi ce verdict")
    verdict.add_argument("--clear", action="store_true",
                         help="retirer le verdict et rendre le lieu à l'automatique")

    epingle = sub.add_parser(
        "pin", help="épingle un lieu déjà collecté : il passe outre les planchers")
    epingle.add_argument("wikidata_id")
    epingle.add_argument("--theme", help="n'épingler que ce rattachement")
    epingle.add_argument("--note", help="pourquoi cet épinglage")
    epingle.add_argument("--clear", action="store_true", help="retirer l'épinglage")

    sub.add_parser(
        "pertes", help="quels redressements de thème écartent un lieu du catalogue")

    retheme = sub.add_parser(
        "retheme", help="rattache un lieu au thème choisi par le curateur")
    retheme.add_argument("wikidata_id", nargs="?")
    retheme.add_argument("theme_id", nargs="?")
    retheme.add_argument("--note", help="pourquoi ce rattachement")
    retheme.add_argument("--clear", action="store_true",
                         help="revenir au rattachement automatique")

    synchro = sub.add_parser(
        "sync", help="aligne la copie de travail sur la collecte versionnée")
    synchro.add_argument(
        "--depuis-la-copie", dest="from_working_copy", action="store_true",
        help="sens inverse : verse places_raw.json dans le dépôt")

    serve = sub.add_parser("review", help="ouvre la page de revue dans le navigateur")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument(
        "--host",
        default="127.0.0.1",
        help="interface d'écoute ; `0.0.0.0` quand le navigateur n'atteint pas "
             "la boucle locale (Android)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)-7s %(message)s",
    )
    if getattr(args, "review", None) is None and args.command == "apply-review":
        # Le brouillon écrit par `review` au fil des clics. La grande feuille
        # `review.csv` faisait un mauvais défaut : sa colonne `decision` est
        # vide, elle n'apporte donc jamais rien.
        args.review = args.out / AUTOSAVE

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
        "relabel": cmd_relabel,
        "resolve-list": cmd_resolve_list,
        "apply-review": cmd_apply_review,
        "stats": cmd_stats,
        "review": cmd_review,
        "sync": cmd_sync,
        "retheme": cmd_retheme,
        "fantomes": cmd_fantomes,
        "verdict": cmd_verdict,
        "pin": cmd_pin,
        "label-probe": cmd_label_probe,
        "pertes": cmd_pertes,
        "merge": cmd_merge,
        "weigh": cmd_weigh,
        "adjustments": cmd_adjustments,
        "check-lists": cmd_check_lists,
        "gaps": cmd_gaps,
        "retention": cmd_retention,
        "probe": cmd_probe,
        "rename": cmd_rename,
        "export-app": cmd_export_app,
        "export-outlines": cmd_export_outlines,
    }
    return handlers[args.command](args, config)
