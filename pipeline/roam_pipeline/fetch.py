"""Collecte des lieux candidats depuis Wikidata."""

from __future__ import annotations

import csv
import json
import logging
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from . import wikidata as wd
from .wikipedia import EXTRACT_BATCH, WikipediaClient, title_from_url
from .config import Config, Label, Theme
from .geo import normalize_dept_code, region_of
from .geocode import AddressClient, CommuneClient, departement_from_insee
from .models import Place
from .raw import EXTRA_SHARD, NO_THEME_SHARD, read_raw, shards, write_raw

LOG = logging.getLogger(__name__)


def fetch_theme(
    client: wd.SparqlClient,
    theme: Theme,
    label_members: dict[str, set[str]] | None = None,
) -> list[Place]:
    """Lieux candidats pour un thème.

    Les classes sont interrogées par lots : une requête sur toutes les classes
    d'un coup dépasse régulièrement le timeout de WDQS.
    """
    by_qid: dict[str, Place] = {}

    if not theme.collected_classes and not theme.from_labels:
        LOG.warning(
            "thème %s : aucune classe résolue (termes en attente : %s) — ignoré. "
            "Lance `suggest-qids` puis renseigne wikidata_classes.",
            theme.id,
            ", ".join(theme.search),
        )
        return []

    # Thème alimenté par des listes officielles : on part des membres des labels
    # plutôt que d'une classe Wikidata.
    if theme.from_labels:
        members: set[str] = set()
        for label_id in theme.from_labels:
            members |= (label_members or {}).get(label_id, set())
        if not members:
            LOG.warning("thème %s : aucun membre de label disponible", theme.id)
        for batch in wd.chunked(sorted(members), 150):
            for row in client.query(wd.items_query(batch)):
                place = _row_to_place(row, theme)
                if place is not None:
                    by_qid[place.wikidata_id] = place

    # Une classe à la fois, et par pages : les classes volumineuses (châteaux,
    # abbayes, cathédrales) dépassaient le délai de WDQS en une seule requête.
    broad = {b.qid for b in theme.broad_classes}
    for class_qid, floor in theme.collected_classes:
        LOG.info(
            "thème %s : classe %s (≥ %s langues%s)", theme.id, class_qid, floor,
            ", générique" if class_qid in broad else "",
        )
        for row in _paged(
            client,
            lambda limit, offset, q=class_qid, f=floor: wd.theme_query(
                [q], f, limit=limit, offset=offset
            ),
        ):
            place = _row_to_place(row, theme)
            if place is None:
                continue
            place.via_broad_class = class_qid in broad
            existing = by_qid.get(place.wikidata_id)
            # Une même entité peut remonter via plusieurs classes : on garde la
            # variante la mieux renseignée.
            if existing is None or _completeness(place) > _completeness(existing):
                by_qid[place.wikidata_id] = place

    LOG.info("thème %s : %s lieux candidats", theme.id, len(by_qid))
    return list(by_qid.values())


PAGE_SIZE = 800


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    """Lit un CSV en ignorant les lignes de commentaire.

    Les fichiers saisis à la main portent des explications en tête ; sans ce
    filtre, `csv` prendrait la première ligne de commentaire pour l'en-tête et
    lirait des colonnes qui n'existent pas.
    """
    lines = [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    return list(csv.DictReader(lines))


def _paged(client: wd.SparqlClient, build_query, page_size: int = PAGE_SIZE):
    """Parcourt une requête page par page jusqu'à épuisement."""
    offset = 0
    while True:
        rows = client.query(build_query(page_size, offset))
        yield from rows
        if len(rows) < page_size:
            return
        offset += page_size


def _completeness(place: Place) -> int:
    return sum(
        1
        for value in (place.image_url, place.departement_code, place.elevation_m, place.wikipedia_url)
        if value
    )


def _row_to_place(row: dict[str, str], theme: Theme) -> Place | None:
    qid = wd.qid_from_uri(row.get("item"))
    coords = wd.parse_point(row.get("coord"))
    name = row.get("itemLabel")

    if not qid or not coords or not name:
        return None
    # Un libellé resté sous forme de Q-id signifie une entité sans nom exploitable.
    if name == qid:
        return None

    return Place(
        wikidata_id=qid,
        name=name,
        theme_id=theme.id,
        lat=coords[0],
        lon=coords[1],
        sitelinks=int(row.get("sitelinks") or 0),
        has_frwiki=bool(row.get("frwiki")),
        wikipedia_url=row.get("frwiki"),
        image_url=row.get("image"),
        commons_category=row.get("commons"),
        elevation_m=_as_int(row.get("elevation")),
        admin_qid=wd.qid_from_uri(row.get("admin")),
        validation_radius_m=theme.radius_m,
    )


def _as_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


def read_place_list(config: Config, path: Path) -> dict[str, str]:
    """Lit un fichier `wikidata_id,theme_id,note` : `{qid: theme_id}`.

    Les thèmes inconnus sont écartés en le disant : une coquille dans la
    colonne ferait disparaître le lieu sans un mot.
    """
    wanted: dict[str, str] = {}
    if not path.exists():
        return wanted
    for row in read_csv_rows(path):
        qid = (row.get("wikidata_id") or "").strip()
        theme_id = (row.get("theme_id") or "").strip()
        if not qid or not theme_id:
            continue
        try:
            config.theme(theme_id)
        except KeyError:
            LOG.error("%s : thème inconnu « %s » pour %s — ignoré", path.name, theme_id, qid)
            continue
        wanted[qid] = theme_id
    return wanted


def fetch_listed_places(
    client: wd.SparqlClient,
    config: Config,
    wanted: dict[str, str],
    *,
    pinned: bool,
    source: str,
) -> list[Place]:
    """Récupère sur Wikidata des lieux désignés par leur Q-id.

    Sert aux deux listes tenues hors des requêtes par classe : les ajouts du
    curateur et les candidats trouvés sur OpenStreetMap. Seuls `pinned` et
    `source` les distinguent — un ajout du curateur est un verdict, un candidat
    n'est qu'une proposition qui devra franchir le plancher comme les autres.
    """
    if not wanted:
        return []

    places: list[Place] = []
    for batch in wd.chunked(sorted(wanted), 150):
        try:
            rows = client.query(wd.items_query(batch))
        except Exception as exc:
            LOG.error("lieux listés : lot échoué (%s)", exc)
            continue
        for row in rows:
            qid = wd.qid_from_uri(row.get("item"))
            if not qid or qid not in wanted:
                continue
            place = _row_to_place(row, config.theme(wanted[qid]))
            if place is None:
                LOG.warning("%s : sans coordonnées ou sans nom — ignoré", qid)
                continue
            place.pinned = pinned
            place.source = source
            places.append(place)

    missing = set(wanted) - {p.wikidata_id for p in places}
    if missing:
        report_missing(client, missing)
    return places


def diagnose_missing(rows: list[dict[str, str]], missing: set[str]) -> dict[str, list[str]]:
    """Range les Q-ids sans résultat par CAUSE, avec leur nom quand il existe.

    `items_query` exige des coordonnées. Une entité qui n'en a pas n'y produit
    donc aucune ligne — exactement comme une entité supprimée. Les deux
    tombaient sous le même message, « introuvable sur Wikidata », alors qu'ils
    n'appellent pas du tout le même geste : l'un est un identifiant mort à
    retirer de la liste, l'autre est un lieu bien réel qu'on perd en silence.
    """
    seen: dict[str, dict[str, str]] = {}
    for row in rows:
        qid = wd.qid_from_uri(row.get("item"))
        if not qid:
            continue
        entry = seen.setdefault(qid, {"label": "", "coord": ""})
        entry["label"] = entry["label"] or (row.get("itemLabel") or "")
        entry["coord"] = entry["coord"] or (row.get("coord") or "")

    causes: dict[str, list[str]] = {"absent": [], "sans coordonnées": [], "sans libellé": []}
    for qid in sorted(missing):
        entry = seen.get(qid)
        if entry is None:
            causes["absent"].append(qid)
        elif not entry["coord"]:
            causes["sans coordonnées"].append(f"{entry['label'] or qid} ({qid})")
        elif not entry["label"] or entry["label"] == qid:
            causes["sans libellé"].append(qid)
        else:
            # Ni l'un ni l'autre : l'entité a tout, et n'a pourtant rien rendu.
            causes.setdefault("inexpliqué", []).append(f"{entry['label']} ({qid})")
    return {cause: items for cause, items in causes.items() if items}


REMEDIES = {
    "absent": "identifiants morts (supprimés ou redirigés) — à retirer de la liste",
    "sans coordonnées": "EXISTENT mais sans coordonnées sur Wikidata — lieux réels, perdus ici",
    "sans libellé": "sans libellé exploitable",
    "inexpliqué": "rien ne les explique — à signaler",
}


def report_missing(client: wd.SparqlClient, missing: set[str]) -> None:
    rows: list[dict[str, str]] = []
    try:
        for batch in wd.chunked(sorted(missing), 150):
            rows.extend(client.query(wd.probe_query(batch)))
    except Exception as exc:
        LOG.warning(
            "%s Q-ids listés sans résultat, diagnostic impossible (%s) : %s",
            len(missing), exc, ", ".join(sorted(missing)),
        )
        return

    for cause, items in diagnose_missing(rows, missing).items():
        LOG.warning(
            "%s Q-ids %s : %s%s",
            len(items),
            REMEDIES.get(cause, cause),
            ", ".join(items[:12]),
            f" (+{len(items) - 12})" if len(items) > 12 else "",
        )


def fetch_manual_places(
    client: wd.SparqlClient, config: Config, manual_dir: Path
) -> list[Place]:
    """Lieux ajoutés à la main, dans `data/manual/places.csv`.

    Le pipeline ratera toujours des lieux : ceux que Wikidata classe mal, et
    ceux qu'il documente peu alors qu'on vient du monde entier les visiter.
    Cette liste est l'échappatoire du curateur — elle passe outre le plancher de
    notoriété et impose le thème indiqué.

    Colonnes : `wikidata_id,theme_id,note`.
    """
    places = fetch_listed_places(
        client, config, read_place_list(config, manual_dir / "places.csv"),
        pinned=True, source="wikidata",
    )
    LOG.info("ajouts manuels : %s lieux épinglés", len(places))
    return places


def fetch_adopted_places(
    client: wd.SparqlClient, config: Config, manual_dir: Path
) -> list[Place]:
    """Candidats adoptés depuis OpenStreetMap, dans `data/manual/candidates.csv`.

    Ces lieux entrent dans le catalogue comme n'importe quel autre : ils sont
    scorés, soumis au plancher de notoriété, dédoublonnés. Rien ne leur est
    accordé — la découverte n'est pas une caution. Le fichier existe pour que
    la collecte reste reproductible : sans lui, relancer `fetch` effacerait
    tout ce que `discover` a trouvé.
    """
    places = fetch_listed_places(
        client, config, read_place_list(config, manual_dir / "candidates.csv"),
        pinned=False, source="osm",
    )
    LOG.info("candidats adoptés : %s lieux", len(places))
    return places


def carry_osm_signals(places: list[Place], raw_dir: Path, raw_path: Path) -> int:
    """Reprend l'ouverture au public de la collecte précédente.

    Wikidata ne sait rien de l'accueil du public : ces champs ne viennent que
    d'OpenStreetMap, et donc que de `discover`, qui coûte vingt minutes. Une
    nouvelle collecte les écraserait par des valeurs vides, sans erreur et sans
    trace — le catalogue perdrait silencieusement la seule donnée qui dise si
    un lieu se visite.
    """
    # Le dépôt d'abord : sur un clone frais, `places_raw.json` n'existe pas
    # encore alors que la collecte, elle, est là — et avec elle l'ouverture au
    # public que personne ne veut recollecter.
    previous: list[dict] = [p.to_dict() for p in read_raw(raw_dir)]
    if not previous and raw_path.exists():
        try:
            previous = json.loads(raw_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            LOG.warning(
                "collecte précédente illisible (%s) — ouverture au public perdue", exc
            )
            return 0
    if not previous:
        return 0

    known = {
        item["wikidata_id"]: item
        for item in previous
        if item.get("wikidata_id") and item.get("osm_id")
    }
    carried = 0
    for place in places:
        item = known.get(place.wikidata_id)
        if item is None or place.osm_id:
            continue
        place.osm_id = item.get("osm_id")
        place.visitable = item.get("visitable")
        place.opening_hours = item.get("opening_hours")
        place.website = item.get("website")
        carried += 1

    if carried:
        LOG.info("ouverture au public reprise de la collecte précédente : %s lieux", carried)
    return carried


def resolve_admin(client: wd.SparqlClient, places: list[Place]) -> None:
    """Complète département et région à partir de la commune de rattachement.

    Seconde passe volontaire : bornée par les communes réellement rencontrées,
    elle coûte quelques requêtes, là où le même chemin transitif intégré à la
    requête de thème faisait échouer les classes volumineuses.
    """
    admin_qids = sorted({p.admin_qid for p in places if p.admin_qid})
    if not admin_qids:
        return

    codes: dict[str, tuple[str | None, str | None]] = {}
    for batch in wd.chunked(admin_qids, 200):
        try:
            rows = client.query(wd.admin_codes_query(batch))
        except Exception as exc:
            LOG.error("résolution administrative : lot échoué (%s)", exc)
            continue
        for row in rows:
            qid = wd.qid_from_uri(row.get("admin"))
            if qid:
                codes[qid] = (row.get("deptCode"), row.get("regionCode"))

    resolved = 0
    for place in places:
        if not place.admin_qid:
            continue
        dept_raw, region_raw = codes.get(place.admin_qid, (None, None))
        dept = normalize_dept_code(dept_raw)
        place.departement_code = dept
        # Le code de région se déduit du département : plus fiable que la
        # remontée Wikidata, qui rate les communes mal rattachées.
        region = region_of(dept) if dept else None
        place.region_code = region.code if region else region_raw
        if dept:
            resolved += 1

    LOG.info(
        "rattachement administratif : %s/%s lieux localisés (%s communes)",
        resolved,
        len(places),
        len(admin_qids),
    )


def enrich_article_sizes(places: list[Place], client: WikipediaClient | None = None) -> int:
    """Complète la taille de l'article francophone de chaque lieu.

    Séparé de la collecte : il travaille sur le fichier brut existant, donc
    ajouter ce signal ne coûte pas une nouvelle demi-heure sur Wikidata.
    """
    client = client or WikipediaClient()
    by_title: dict[str, list[Place]] = defaultdict(list)
    for place in places:
        title = title_from_url(place.wikipedia_url)
        if title:
            by_title[title].append(place)

    if not by_title:
        LOG.warning("aucun article francophone à interroger")
        return 0

    titles = sorted(by_title)
    found = 0
    for index, batch in enumerate(wd.chunked(titles, 50), start=1):
        try:
            sizes = client.article_sizes(batch)
        except Exception as exc:
            LOG.error("tailles d'articles : lot %s échoué (%s)", index, exc)
            continue
        for title, size in sizes.items():
            for place in by_title[title]:
                place.article_bytes = size
            found += 1

    LOG.info("taille d'article renseignée pour %s/%s articles", found, len(titles))
    return found


def enrich_summaries(places: list[Place], client: WikipediaClient | None = None) -> int:
    """Récupère une description courte pour chaque lieu.

    Sans elle, la fiche d'un lieu n'affiche qu'un nom et un thème — ce qui ne
    donne aucune raison d'y aller. Le texte vient de Wikipédia (CC BY-SA), et
    la fiche cite déjà sa source.
    """
    client = client or WikipediaClient()
    by_title: dict[str, list[Place]] = defaultdict(list)
    for place in places:
        title = title_from_url(place.wikipedia_url)
        if title and not place.summary:
            by_title[title].append(place)

    titles = sorted(by_title)
    if not titles:
        LOG.info("descriptions : rien à récupérer")
        return 0

    # `prop=extracts` est plafonné à vingt titres : la collecte est plus longue
    # que celle des tailles d'articles, d'où l'annonce préalable.
    batches = (len(titles) + EXTRACT_BATCH - 1) // EXTRACT_BATCH
    LOG.info("descriptions : %s articles, %s requêtes (~%s s)", len(titles), batches, batches)

    found = 0
    for index, batch in enumerate(wd.chunked(titles, EXTRACT_BATCH), start=1):
        try:
            summaries = client.intros(batch)
        except Exception as exc:
            LOG.error("descriptions : lot %s/%s échoué (%s)", index, batches, exc)
            continue
        for title, text in summaries.items():
            for place in by_title[title]:
                place.summary = text
            found += 1
        if index % 50 == 0:
            LOG.info("descriptions : %s/%s requêtes", index, batches)

    LOG.info("descriptions récupérées pour %s/%s articles", found, len(titles))
    return found


def enrich_communes(
    places: list[Place],
    address_client: AddressClient | None = None,
    commune_client: CommuneClient | None = None,
) -> int:
    """Rattache chaque lieu à sa commune, par ses coordonnées.

    La commune est la maille la plus fine de la carte de conquête : celle qui
    se colore en une seule visite, et donc celle qui donne le sentiment
    d'avancer dès le premier lieu. Wikidata ne la donne pas de façon fiable —
    `P131` manque sur les sites naturels, et pointe parfois un hameau ou un
    canton plutôt qu'une commune.

    Les coordonnées, elles, sont toujours là. Mêmes deux passes que pour le
    rattachement au département : l'API Adresse en masse, puis l'API Géo point
    par point pour ce qu'elle n'a pas su situer.

    Seuls les lieux sans commune sont interrogés : relancer la passe ne coûte
    donc rien une fois qu'elle a abouti.
    """
    missing = [p for p in places if not p.commune_code]
    if not missing:
        LOG.info("communes : tous les lieux sont déjà rattachés")
        return 0

    LOG.info("communes : %s lieux à rattacher", len(missing))
    resolved = 0

    def assign(place: Place, commune) -> bool:
        if commune is None:
            return False
        place.commune_code = commune.code
        place.commune_name = commune.name or place.commune_name
        # La commune fait autorité sur le département : elle vient du même
        # appel et ne peut pas le contredire.
        dept = normalize_dept_code(commune.departement)
        if dept:
            place.departement_code = dept
            known = region_of(dept)
            if known:
                place.region_code = known.code
        return True

    address_client = address_client or AddressClient()
    for batch in wd.chunked(missing, 500):
        try:
            found = address_client.reverse_communes(
                [(place.wikidata_id, place.lat, place.lon) for place in batch]
            )
        except Exception as exc:
            LOG.error("API Adresse : lot échoué (%s)", exc)
            continue
        for place in batch:
            if assign(place, found.get(place.wikidata_id)):
                resolved += 1

    still_missing = [p for p in missing if not p.commune_code]
    if still_missing:
        LOG.info(
            "API Géo : %s lieux restants, interrogés un par un (~%s s)",
            len(still_missing),
            int(len(still_missing) * 0.06),
        )
        commune_client = commune_client or CommuneClient()
        for place in still_missing:
            found = commune_client.locate_commune(place.lat, place.lon)
            if found and assign(place, found[0]):
                resolved += 1

    unresolved = [p for p in missing if not p.commune_code]
    LOG.info("communes : %s/%s lieux rattachés", resolved, len(missing))
    if unresolved:
        # Hors de France, ou en mer : un phare sur son rocher, une réserve de
        # baie. Ils resteront hors de la carte de conquête à l'échelle
        # communale, mais gardent leur département.
        LOG.info(
            "%s lieux sans commune (hors de France, ou en mer) : %s",
            len(unresolved),
            ", ".join(p.name for p in unresolved[:5]),
        )
    return resolved


def enrich_departements(
    places: list[Place],
    address_client: AddressClient | None = None,
    commune_client: CommuneClient | None = None,
) -> int:
    """Rattache par coordonnées les lieux que Wikidata ne situe pas.

    Deux passes, dans cet ordre :

    1. **API Adresse**, par lots de cinq cents. Rapide, mais elle cherche
       l'adresse la plus proche : un lieu isolé n'en a aucune à portée.
    2. **API Géo**, point par point, pour le reste. Elle répond par
       appartenance au polygone communal — la bonne question pour une cascade
       au fond d'une forêt. Plus lente, mais elle ne sert qu'aux cas restants.
    """
    missing = [p for p in places if not p.departement_code]
    if not missing:
        LOG.info("rattachement : tous les lieux ont déjà un département")
        return 0

    LOG.info("rattachement : %s lieux sans département", len(missing))
    resolved = 0

    def assign(place: Place, dept: str | None, region: str | None = None) -> bool:
        dept = normalize_dept_code(dept)
        if not dept:
            return False
        place.departement_code = dept
        known = region_of(dept)
        place.region_code = known.code if known else region or place.region_code
        return True

    address_client = address_client or AddressClient()
    for batch in wd.chunked(missing, 500):
        try:
            codes = address_client.reverse(
                [(place.wikidata_id, place.lat, place.lon) for place in batch]
            )
        except Exception as exc:
            LOG.error("API Adresse : lot échoué (%s)", exc)
            continue
        for place in batch:
            if assign(place, departement_from_insee(codes.get(place.wikidata_id))):
                resolved += 1

    still_missing = [p for p in missing if not p.departement_code]
    if still_missing:
        LOG.info(
            "API Géo : %s lieux restants, interrogés un par un (~%s s)",
            len(still_missing),
            int(len(still_missing) * 0.06),
        )
        commune_client = commune_client or CommuneClient()
        for place in still_missing:
            found = commune_client.locate(place.lat, place.lon)
            if found and assign(place, found[0], found[1]):
                resolved += 1

    unresolved = [p for p in missing if not p.departement_code]
    LOG.info("rattachement par coordonnées : %s/%s lieux situés", resolved, len(missing))
    if unresolved:
        # Ceux-là sont soit hors de France, soit en mer — un phare isolé, un
        # îlot. Les nommer évite de conclure trop vite à une panne.
        LOG.info(
            "%s lieux restent sans commune (hors de France ou en mer) : %s",
            len(unresolved),
            ", ".join(p.name for p in unresolved[:5]),
        )
    return resolved


def enrich_flags(client: wd.SparqlClient, places: list[Place]) -> int:
    """Complète date de disparition et altitude sur les lieux déjà collectés."""
    by_qid = {place.wikidata_id: place for place in places}
    found = 0

    for batch in wd.chunked(sorted(by_qid), 200):
        try:
            rows = client.query(wd.entity_flags_query(batch))
        except Exception as exc:
            LOG.error("signaux : lot échoué (%s)", exc)
            continue
        for row in rows:
            place = by_qid.get(wd.qid_from_uri(row.get("item")) or "")
            if place is None:
                continue
            if row.get("dissolved"):
                place.dissolved = row["dissolved"]
                found += 1
            if row.get("elevation") and place.elevation_m is None:
                try:
                    place.elevation_m = int(float(row["elevation"]))
                except ValueError:
                    pass

    LOG.info("signaux : %s lieux portent une date de disparition", found)
    return found


def enrich_exclusions(
    client: wd.SparqlClient, places: list[Place], class_qids: list[str]
) -> int:
    """Marque les lieux qui relèvent d'une classe disqualifiante.

    Marque, mais n'écarte pas : le retrait appartient à la construction, qui
    sait épargner un lieu épinglé et surtout qui NOMME ce qu'elle enlève. Une
    exclusion par classe est assez brutale pour mériter d'être relue.
    """
    # Repartir de zéro : retirer une classe de la liste doit rendre au
    # catalogue les lieux qu'elle écartait, sans quoi l'exclusion serait un
    # aller sans retour.
    for place in places:
        place.excluded_class = None
    if not class_qids or not places:
        return 0

    by_qid = {place.wikidata_id: place for place in places}
    marked = 0
    for batch in wd.chunked(sorted(by_qid), 200):
        try:
            rows = client.query(wd.class_ancestry_query(batch, class_qids))
        except Exception as exc:
            LOG.error("exclusions : lot échoué (%s)", exc)
            continue
        for row in rows:
            place = by_qid.get(wd.qid_from_uri(row.get("item")) or "")
            if place is None or place.excluded_class:
                continue
            place.excluded_class = row.get("classLabel") or wd.qid_from_uri(row.get("class"))
            marked += 1

    LOG.info("exclusions : %s lieux relèvent d'une classe écartée", marked)
    return marked


def enrich_visitors(
    client: wd.SparqlClient, places: list[Place], property_id: str | None
) -> int:
    """Complète la fréquentation annuelle. Renvoie le nombre de lieux servis."""
    # Repartir de zéro, comme pour les exclusions : un chiffre retiré de
    # Wikidata doit disparaître du score, pas y survivre indéfiniment.
    for place in places:
        place.visitors_per_year = None
    if not property_id or not places:
        return 0

    by_qid = {place.wikidata_id: place for place in places}
    for batch in wd.chunked(sorted(by_qid), 200):
        try:
            rows = client.query(wd.visitors_query(batch, property_id))
        except Exception as exc:
            LOG.error("fréquentation : lot échoué (%s)", exc)
            continue
        for row in rows:
            place = by_qid.get(wd.qid_from_uri(row.get("item")) or "")
            if place is None:
                continue
            try:
                count = int(float(row["visitors"]))
            except (KeyError, TypeError, ValueError):
                continue
            # Le plus élevé des chiffres publiés : une année de travaux ne doit
            # pas décider de ce que vaut un lieu.
            if count > 0 and (place.visitors_per_year or 0) < count:
                place.visitors_per_year = count

    served = sum(1 for p in places if p.visitors_per_year)
    LOG.info(
        "fréquentation : %s lieux sur %s portent un chiffre (%.0f %%)",
        served, len(places), 100 * served / max(len(places), 1),
    )
    return served


def fetch_label_members(client: wd.SparqlClient, label: Label, manual_dir: Path) -> set[str]:
    """Q-ids des lieux portant un label."""
    if label.is_manual:
        return _read_manual_label(label, manual_dir)

    if not label.qid:
        # Label en attente de résolution : mieux vaut l'ignorer bruyamment que
        # produire un catalogue amputé sans le dire.
        LOG.warning(
            "label %s : identifiant non résolu (terme « %s ») — ignoré. "
            "Lance `suggest-qids` pour le résoudre.",
            label.id,
            label.search,
        )
        return set()

    rows = client.query(wd.label_members_query(label.query_kind, label.qid or ""))
    qids = {qid for qid in (wd.qid_from_uri(r.get("item")) for r in rows) if qid}
    LOG.info("label %s : %s membres", label.id, len(qids))
    return qids


def _read_manual_label(label: Label, manual_dir: Path) -> set[str]:
    path = manual_dir / f"{label.id}.csv"
    if not path.exists():
        LOG.warning(
            "label %s : pas de source Wikidata et %s absent — label ignoré",
            label.id,
            path,
        )
        return set()
    qids = {
        row["wikidata_id"].strip()
        for row in read_csv_rows(path)
        if row.get("wikidata_id")
    }
    LOG.info("label %s : %s membres (liste manuelle)", label.id, len(qids))
    return qids


def apply_labels(places: list[Place], label_members: dict[str, set[str]]) -> None:
    """Reporte les labels sur les lieux déjà collectés."""
    for place in places:
        place.labels = sorted(
            label_id for label_id, qids in label_members.items() if place.wikidata_id in qids
        )


def run_fetch(
    client: wd.SparqlClient,
    config: Config,
    out_dir: Path,
    manual_dir: Path,
    only: list[str] | None = None,
    raw_dir: Path | None = None,
) -> list[Place]:
    """Collecte les candidats. `only` limite aux thèmes nommés.

    Une collecte complète dure une demi-heure ; quand un thème échoue, on doit
    pouvoir le reprendre seul plutôt que tout refaire. Les thèmes non demandés
    — et ceux qui ont échoué — sont donc conservés depuis la collecte
    précédente, thème par thème.

    C'est le découpage par fichier qui rend cette garantie solide : on ne
    réécrit QUE les thèmes réellement collectés. Un thème qui expire ne peut
    donc plus vider sa propre collecte, ce qu'un fichier unique réécrit d'un
    bloc faisait sans le dire.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_path = out_dir / "places_raw.json"
    raw_dir = raw_dir if raw_dir is not None else out_dir.parent / "raw"

    themes = [t for t in config.themes if not only or t.id in only]
    if only:
        unknown = set(only) - {t.id for t in config.themes}
        if unknown:
            raise KeyError(f"thème(s) inconnu(s) : {', '.join(sorted(unknown))}")

    label_members: dict[str, set[str]] = {}
    for label in config.labels:
        try:
            label_members[label.id] = fetch_label_members(client, label, manual_dir)
        except Exception as exc:  # un label en échec ne doit pas tuer la collecte
            LOG.error("label %s : collecte échouée (%s)", label.id, exc)
            label_members[label.id] = set()

    places: list[Place] = []
    failed: list[str] = []
    for theme in themes:
        try:
            places.extend(fetch_theme(client, theme, label_members))
        except Exception as exc:
            LOG.error("thème %s : collecte échouée (%s)", theme.id, exc)
            failed.append(theme.id)

    # Les ajouts manuels sont toujours recollectés, même en reprise partielle :
    # ils ne dépendent d'aucun thème en particulier.
    manual = fetch_manual_places(client, config, manual_dir)
    pinned_ids = {place.wikidata_id for place in manual}
    places = [p for p in places if p.wikidata_id not in pinned_ids] + manual

    # Les candidats adoptés ne complètent que ce qui manque : quand une requête
    # par classe a déjà trouvé le lieu, c'est ce rattachement-là qui vaut, pas
    # le thème deviné depuis une balise OpenStreetMap.
    known = {place.wikidata_id for place in places}
    adopted = [
        place
        for place in fetch_adopted_places(client, config, manual_dir)
        if place.wikidata_id not in known
    ]
    places += adopted

    resolve_admin(client, places)
    apply_labels(places, label_members)

    # L'ouverture au public ne vient que d'OpenStreetMap, donc de `discover`,
    # qui coûte vingt minutes : une nouvelle collecte l'écraserait sans trace.
    carry_osm_signals(places, raw_dir, raw_path)

    # On ne réécrit que ce qu'on a collecté. Les thèmes non demandés gardent
    # leur fichier ; ceux qui ont échoué aussi — leur dernière collecte réussie
    # vaut mieux que rien, et l'échec est déjà signalé par ailleurs.
    collected = {t.id for t in themes} - set(failed)
    written = write_raw(raw_dir, places, replacing=collected | {EXTRA_SHARD})
    LOG.info(
        "collecte écrite dans %s : %s",
        raw_dir,
        ", ".join(f"{name} {count}" for name, count in sorted(written.items())),
    )

    # Un thème retiré de la configuration garderait son fichier pour toujours :
    # aucune collecte ne le recouvre. Ses lieux ne sortaient dans aucune
    # collection mais faussaient chaque tableau de diagnostic.
    configured = {t.id for t in config.themes} | {EXTRA_SHARD, NO_THEME_SHARD}
    stale = [name for name in shards(raw_dir) if name not in configured]
    for name in stale:
        (raw_dir / f"{name}.json").unlink(missing_ok=True)
    if stale:
        LOG.warning(
            "thèmes disparus de la configuration, collectes abandonnées : %s",
            ", ".join(stale),
        )

    # La copie de travail, reconstituée : elle porte donc aussi les thèmes que
    # cette collecte n'a pas touchés.
    places = read_raw(raw_dir)
    raw_path.write_text(
        json.dumps([p.to_dict() for p in places], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    LOG.info("%s lieux écrits dans %s", len(places), raw_path)

    _write_fetch_state(out_dir, themes, places, failed)

    if failed:
        # Le message doit être actionnable : une demi-heure de collecte ne se
        # relance pas en entier pour deux thèmes.
        LOG.error(
            "%s thème(s) en échec : %s — reprends-les seuls avec "
            "`python -m roam_pipeline fetch --only %s`",
            len(failed),
            ", ".join(failed),
            " ".join(failed),
        )
    return places


FETCH_STATE = "fetch-state.json"


def _write_fetch_state(
    out_dir: Path, themes: list[Theme], places: list[Place], failed: list[str]
) -> None:
    """Enregistre l'issue de la collecte, thème par thème.

    Un thème en échec était signalé une fois, en fin de journal, puis oublié :
    la reprise partielle reconduisait ses anciennes données à chaque passage,
    et rien ne disait plus qu'elles étaient incomplètes. Le mont Blanc a
    disparu du catalogue de cette façon, sans qu'aucun compteur ne bouge.

    L'état est FUSIONNÉ avec le précédent : une reprise partielle ne dit rien
    des thèmes qu'elle n'a pas touchés, et effacer leur état les blanchirait.
    """
    path = out_dir / FETCH_STATE
    state: dict[str, dict] = {}
    if path.exists():
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            LOG.warning("%s illisible — état de collecte reparti de zéro", path)

    counts = Counter(place.theme_id for place in places)
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for theme in themes:
        state[theme.id] = {
            "ok": theme.id not in failed,
            "lieux": counts.get(theme.id, 0),
            "le": stamp,
        }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")


def read_fetch_state(out_dir: Path) -> dict[str, dict]:
    path = out_dir / FETCH_STATE
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return {}


def stale_themes(state: dict[str, dict], config: Config) -> list[tuple[str, str]]:
    """Thèmes dont les données ne sont pas fiables, et pourquoi.

    Deux cas, et le second est celui qui a coûté le mont Blanc : un thème dont
    la dernière collecte a échoué, et un thème dont on n'a aucune trace — ses
    lieux viennent alors d'une collecte antérieure au suivi, ou de nulle part.
    """
    out: list[tuple[str, str]] = []
    for theme in config.themes:
        entry = state.get(theme.id)
        if entry is None:
            out.append((theme.id, "jamais collecté depuis le suivi"))
        elif not entry.get("ok", True):
            out.append((theme.id, f"dernière collecte EN ÉCHEC ({entry.get('le', '?')})"))
        elif not entry.get("lieux"):
            out.append((theme.id, "collecté, mais aucun lieu rapporté"))
    return out
