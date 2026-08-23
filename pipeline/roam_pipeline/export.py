"""Sorties du pipeline : JSON, feuille de revue éditoriale, seed SQL."""

from __future__ import annotations

import csv
import json
import logging
from collections import defaultdict
from pathlib import Path

from .config import Config
from .geo import departements, regions
from .alerts import alerts_for
from .score import score_breakdown
from .models import Collection, Place

LOG = logging.getLogger(__name__)

REVIEW_HEADER = [
    "decision",       # à remplir : (vide)=en attente, keep, drop, promote, demote
    "curator_note",
    "name",
    "theme",
    # « osm » : trouvé parce qu'OpenStreetMap atteste qu'on y accueille du
    # public, et non parce que Wikidata le classait quelque part.
    "origine",
    "departement",
    "best_tier",
    "score",
    # Détail du score : un classement qu'on ne peut pas auditer ne peut pas être
    # corrigé. Le relecteur doit voir pourquoi un lieu passe devant un autre.
    "notoriete",
    "bonus_labels",
    "bonus_article",
    "bonus_image",
    "bonus_frwiki",
    # Accueil du public : bonus s'il est attesté, malus s'il est refusé, zéro
    # s'il n'est pas renseigné.
    "bonus_acces",
    "sitelinks",
    "labels",
    "collections",
    # Points à vérifier : disparu, accès alpin, aucune photo.
    "alertes",
    "ouvert_au_public",
    "horaires",
    "lat",
    "lon",
    "wikidata_id",
    "wikipedia_url",
    "image_url",
]


def write_json(places: list[Place], collections: list[Collection], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "places.json").write_text(
        json.dumps([p.to_dict() for p in places], ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out_dir / "collections.json").write_text(
        json.dumps([c.to_dict() for c in collections], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    LOG.info("JSON écrit dans %s", out_dir)


def _membership(collections: list[Collection]) -> tuple[dict[str, list[str]], dict[str, int]]:
    """Collections de chaque lieu, et son niveau de priorité de revue.

    Le niveau retenu est celui de la COLLECTION THÉMATIQUE NATIONALE, pas le
    meilleur niveau toutes collections confondues. Ce dernier faisait passer
    pour « incontournable » tout lieu arrivé premier d'une petite collection
    départementale — les deux tiers du catalogue se retrouvaient en niveau 1,
    et la priorisation ne priorisait plus rien.
    """
    membership: dict[str, list[str]] = defaultdict(list)
    review_tier: dict[str, int] = {}

    for collection in collections:
        for cp in collection.places:
            membership[cp.place_id].append(collection.name)

    for collection in collections:
        if collection.kind != "theme":
            continue
        for cp in collection.places:
            review_tier[cp.place_id] = cp.tier

    # Hors de la collection nationale de son thème : à relire en dernier.
    for place_id in membership:
        review_tier.setdefault(place_id, 3)

    return membership, review_tier


def write_review_csv(
    places: list[Place],
    collections: list[Collection],
    out_path: Path,
    config: Config | None = None,
) -> None:
    """Feuille de revue éditoriale.

    Le pipeline propose, l'humain décide. La colonne `decision` est relue par
    `apply-review`. Le détail du score accompagne chaque ligne : un classement
    qu'on ne peut pas auditer ne peut pas être corrigé.

    Triée par niveau puis par thème : le travail est trop long pour être fait
    d'un bloc, il doit pouvoir être fait par tranches utiles.
    """
    membership, best_tier = _membership(collections)
    depts = departements()
    # Les niveaux 1 en tête, groupés par thème. Relire 1 900 lignes d'un bloc
    # est décourageant ; relire d'abord les 200 incontournables donne déjà un
    # catalogue jouable, et comparer des châteaux entre eux va plus vite que
    # de sauter d'un thème à l'autre.
    ordered = sorted(
        places,
        key=lambda p: (best_tier.get(p.wikidata_id, 9), p.theme_id, -p.score, p.name),
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(REVIEW_HEADER)
        for place in ordered:
            dept = depts.get(place.departement_code or "")
            parts = (
                score_breakdown(place, config)
                if config
                else dict.fromkeys(
                    ("notoriete", "labels", "article", "image", "frwiki", "acces"), ""
                )
            )
            writer.writerow(
                [
                    "",
                    "",
                    place.name,
                    place.theme_id,
                    place.source,
                    dept.name if dept else "",
                    best_tier.get(place.wikidata_id, ""),
                    f"{place.score:.1f}",
                    parts["notoriete"],
                    parts["labels"],
                    parts["article"],
                    parts["image"],
                    parts["frwiki"],
                    parts["acces"],
                    place.sitelinks,
                    "|".join(place.labels),
                    len(membership.get(place.wikidata_id, [])),
                    " ; ".join(alerts_for(place, config)) if config else "",
                    {True: "oui", False: "non"}.get(place.visitable, "inconnu"),
                    place.opening_hours or "",
                    f"{place.lat:.6f}",
                    f"{place.lon:.6f}",
                    place.wikidata_id,
                    place.wikipedia_url or "",
                    place.image_url or "",
                ]
            )
    LOG.info("feuille de revue : %s (%s lignes)", out_path, len(ordered))


def read_review_csv(path: Path) -> dict[str, tuple[str, str]]:
    """Relit les décisions de la feuille de revue : qid → (décision, note)."""
    decisions: dict[str, tuple[str, str]] = {}
    with path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            qid = (row.get("wikidata_id") or "").strip()
            decision = (row.get("decision") or "").strip().lower()
            if qid and decision:
                decisions[qid] = (decision, (row.get("curator_note") or "").strip())
    return decisions


def _sql_str(value: str | None) -> str:
    if value is None or value == "":
        return "null"
    return "'" + value.replace("'", "''") + "'"


def _sql_array(values: list[str]) -> str:
    if not values:
        return "'{}'"
    inner = ",".join(v.replace('"', '\\"') for v in values)
    return _sql_str("{" + inner + "}")


def write_seed_sql(
    places: list[Place], collections: list[Collection], config: Config, out_path: Path
) -> None:
    """Seed idempotent : référentiels, lieux (en `draft`), collections, appartenances."""
    lines: list[str] = [
        "-- Généré par roam_pipeline. Ne pas éditer à la main.",
        "-- Les lieux sont insérés en statut 'draft' : la publication est une",
        "-- décision humaine, jamais une sortie de pipeline.",
        "begin;",
        "",
        "-- Thèmes",
    ]

    for theme in config.themes:
        lines.append(
            "insert into themes (id, name, name_singular, icon, default_radius_m) values "
            f"({_sql_str(theme.id)}, {_sql_str(theme.name)}, {_sql_str(theme.name_singular)}, "
            f"{_sql_str(theme.icon)}, {theme.radius_m}) "
            "on conflict (id) do update set name = excluded.name, "
            "default_radius_m = excluded.default_radius_m;"
        )

    lines += ["", "-- Labels"]
    for label in config.labels:
        lines.append(
            "insert into labels (id, name, authority, score_bonus, makes_collection) values "
            f"({_sql_str(label.id)}, {_sql_str(label.name)}, {_sql_str(label.authority)}, "
            f"{label.score_bonus}, {str(label.makes_collection).lower()}) "
            "on conflict (id) do update set name = excluded.name, "
            "score_bonus = excluded.score_bonus;"
        )

    lines += ["", "-- Découpage administratif"]
    lines.append(
        "insert into geo_areas (id, level, code, name, parent_id) values "
        "('country:FR', 'country', 'FR', 'France', null) on conflict (id) do nothing;"
    )
    for region in regions().values():
        lines.append(
            "insert into geo_areas (id, level, code, name, parent_id) values "
            f"({_sql_str(region.id)}, 'region', {_sql_str(region.code)}, "
            f"{_sql_str(region.name)}, 'country:FR') on conflict (id) do nothing;"
        )
    for dept in departements().values():
        parent = f"region:{dept.parent_code}" if dept.parent_code else None
        lines.append(
            "insert into geo_areas (id, level, code, name, parent_id) values "
            f"({_sql_str(dept.id)}, 'departement', {_sql_str(dept.code)}, "
            f"{_sql_str(dept.name)}, {_sql_str(parent)}) on conflict (id) do nothing;"
        )

    lines += ["", "-- Lieux"]
    for place in places:
        dept_id = f"departement:{place.departement_code}" if place.departement_code else None
        region_id = f"region:{place.region_code}" if place.region_code else None
        lines.append(
            "insert into places (slug, name, theme_id, location, validation_radius_m, "
            "elevation_m, departement_id, region_id, score, inclusion_criteria, "
            "wikidata_id, wikipedia_url, commons_category, sitelink_count, cover_image_url, "
            "status, source) values ("
            f"{_sql_str(place.slug)}, {_sql_str(place.name)}, {_sql_str(place.theme_id)}, "
            f"ST_SetSRID(ST_MakePoint({place.lon}, {place.lat}), 4326)::geography, "
            f"{place.validation_radius_m}, "
            f"{place.elevation_m if place.elevation_m is not None else 'null'}, "
            f"{_sql_str(dept_id)}, {_sql_str(region_id)}, {place.score}, "
            f"{_sql_array(place.inclusion_criteria)}, {_sql_str(place.wikidata_id)}, "
            f"{_sql_str(place.wikipedia_url)}, {_sql_str(place.commons_category)}, "
            f"{place.sitelinks}, {_sql_str(place.image_url)}, 'draft', 'pipeline') "
            "on conflict (wikidata_id) do update set "
            "name = excluded.name, score = excluded.score, "
            "sitelink_count = excluded.sitelink_count, updated_at = now();"
        )
        for label_id in place.labels:
            lines.append(
                "insert into place_labels (place_id, label_id) select p.id, "
                f"{_sql_str(label_id)} from places p where p.wikidata_id = "
                f"{_sql_str(place.wikidata_id)} on conflict do nothing;"
            )

    lines += ["", "-- Collections"]
    for collection in collections:
        geo_id = (
            f"{collection.geo_level}:{collection.geo_code}"
            if collection.geo_level and collection.geo_code
            else None
        )
        tier_counts = "'{" + ",".join(str(n) for n in collection.tier_counts) + "}'"
        lines.append(
            "insert into collections (slug, name, kind, theme_id, label_id, geo_area_id, "
            "place_count, tier_counts, status) values ("
            f"{_sql_str(collection.slug)}, {_sql_str(collection.name)}, "
            f"{_sql_str(collection.kind)}, {_sql_str(collection.theme_id)}, "
            f"{_sql_str(collection.label_id)}, {_sql_str(geo_id)}, "
            f"{len(collection.places)}, {tier_counts}, 'draft') "
            "on conflict (slug) do update set name = excluded.name, "
            "place_count = excluded.place_count, tier_counts = excluded.tier_counts, "
            "updated_at = now();"
        )
        for cp in collection.places:
            lines.append(
                "insert into collection_places (collection_id, place_id, tier, rank) "
                f"select c.id, p.id, {cp.tier}, {cp.rank} from collections c, places p "
                f"where c.slug = {_sql_str(collection.slug)} and p.wikidata_id = "
                f"{_sql_str(cp.place_id)} on conflict (collection_id, place_id) "
                "do update set tier = excluded.tier, rank = excluded.rank;"
            )

    lines += ["", "commit;", ""]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    LOG.info("seed SQL : %s (%s instructions)", out_path, len(lines))


# ---------------------------------------------------------------------------
# Page de revue visuelle
# ---------------------------------------------------------------------------

REVIEW_PAGE_TITLE = "Roam — revue du catalogue"


def _thumbnail(image_url: str | None, width: int = 400) -> str:
    """Vignette Commons. `Special:FilePath` accepte un paramètre de largeur."""
    if not image_url:
        return ""
    separator = "&" if "?" in image_url else "?"
    return f"{image_url}{separator}width={width}"


def write_review_html(
    places: list[Place],
    collections: list[Collection],
    config: Config,
    out_path: Path,
) -> None:
    """Page de revue avec vignettes.

    Un nom seul ne permet pas de juger deux cents abbayes qu'on ne connaît pas.
    Une photo, si. La page est écrite en local et charge les images depuis
    Wikimedia Commons — c'est aussi pour cela qu'elle n'est pas un simple CSV.

    Les décisions sont conservées dans le navigateur et se réexportent en CSV
    compatible avec `apply-review`.
    """
    membership, best_tier = _membership(collections)
    depts = departements()

    rows = []
    for place in sorted(
        places, key=lambda p: (best_tier.get(p.wikidata_id, 9), p.theme_id, -p.score, p.name)
    ):
        dept = depts.get(place.departement_code or "")
        parts = score_breakdown(place, config)
        rows.append(
            {
                "id": place.wikidata_id,
                "name": place.name,
                "theme": config.theme(place.theme_id).name,
                "themeId": place.theme_id,
                "dept": dept.name if dept else "",
                "tier": best_tier.get(place.wikidata_id, 3),
                "score": place.score,
                "parts": parts,
                "sitelinks": place.sitelinks,
                "labels": place.labels,
                "collections": len(membership.get(place.wikidata_id, [])),
                "wikipedia": place.wikipedia_url or "",
                "image": _thumbnail(place.image_url),
                "alerts": alerts_for(place, config),
                "visitable": place.visitable,
                "hours": place.opening_hours,
                "source": place.source,
            }
        )

    themes = sorted({row["theme"] for row in rows})
    payload = json.dumps(rows, ensure_ascii=False)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        _REVIEW_TEMPLATE.replace("__DATA__", payload)
        .replace("__THEMES__", json.dumps(themes, ensure_ascii=False))
        .replace("__TITLE__", REVIEW_PAGE_TITLE),
        encoding="utf-8",
    )
    LOG.info("page de revue : %s (%s lieux)", out_path, len(rows))


_REVIEW_TEMPLATE = """<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
  :root {
    --bg: #FBFAF7; --surface: #FFFFFF; --alt: #F3F0EA; --text: #1A1917;
    --muted: #6F6A62; --border: #E7E3DB; --primary: #B4532B; --keep: #2F6F4E;
    --drop: #A33A3A;
  }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--bg); color: var(--text);
         font: 15px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
  header { position: sticky; top: 0; z-index: 10; background: var(--bg);
           border-bottom: 1px solid var(--border); padding: 14px 20px; }
  h1 { font-size: 19px; margin: 0 0 10px; }
  .bar { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
  select, button { font: inherit; padding: 7px 12px; border-radius: 8px;
                   border: 1px solid var(--border); background: var(--surface);
                   color: var(--text); cursor: pointer; }
  button.primary { background: var(--primary); color: #fff; border-color: var(--primary); }
  .count { color: var(--muted); font-size: 13px; margin-left: auto; }
  main { display: grid; gap: 14px; padding: 20px;
         grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); }
  .card { background: var(--surface); border: 1px solid var(--border); border-radius: 14px;
          overflow: hidden; display: flex; flex-direction: column; }
  .card.keep { border-color: var(--keep); box-shadow: inset 0 0 0 1px var(--keep); }
  .card.drop { opacity: .45; border-color: var(--drop); }
  .thumb { aspect-ratio: 4/3; background: var(--alt); object-fit: cover; width: 100%;
           display: block; }
  .noimg { aspect-ratio: 4/3; background: var(--alt); display: grid; place-items: center;
           color: var(--muted); font-size: 13px; }
  .body { padding: 12px 14px; display: flex; flex-direction: column; gap: 6px; flex: 1; }
  .name { font-weight: 700; line-height: 1.3; }
  .meta, .parts { color: var(--muted); font-size: 13px; }
  .parts { font-variant-numeric: tabular-nums; }
  .tags { display: flex; flex-wrap: wrap; gap: 4px; }
  .tag { background: var(--alt); border-radius: 999px; padding: 2px 8px; font-size: 11px; }
  .alert { background: #FBEEE6; color: #9A4520; border: 1px solid #E4C3B0;
           border-radius: 6px; padding: 4px 8px; font-size: 12px; }
  .open { background: #E3F0E8; color: #2F6F4E; border-radius: 6px;
          padding: 4px 8px; font-size: 12px; }
  .found { background: #EAEDF4; color: #3B4A6B; border-radius: 6px;
           padding: 4px 8px; font-size: 12px; }
  .alerts { display: flex; flex-direction: column; gap: 4px; }
  .tier { font-size: 11px; font-weight: 700; letter-spacing: .5px; color: var(--primary); }
  .actions { display: flex; gap: 6px; padding: 0 14px 12px; }
  .actions button { flex: 1; padding: 7px 0; font-size: 13px; }
  .actions button[data-on="keep"] { background: var(--keep); color: #fff; border-color: var(--keep); }
  .actions button[data-on="drop"] { background: var(--drop); color: #fff; border-color: var(--drop); }
  a { color: var(--primary); }
  .warn { background: #FBEEE6; border: 1px solid var(--primary); color: var(--primary);
          padding: 8px 12px; border-radius: 8px; font-size: 13px; margin: 12px 20px 0; }
</style>
</head>
<body>
<header>
  <h1>__TITLE__</h1>
  <div class="bar">
    <select id="theme"><option value="">Tous les thèmes</option></select>
    <select id="tier">
      <option value="">Tous les niveaux</option>
      <option value="1">Niveau 1 — les incontournables</option>
      <option value="2">Niveau 2</option>
      <option value="3">Niveau 3</option>
    </select>
    <select id="state">
      <option value="todo">À décider</option>
      <option value="">Tout</option>
      <option value="alert">À vérifier — disparu, accès, photo</option>
      <option value="open">Ouverts au public</option>
      <option value="osm">Découverts sur OpenStreetMap</option>
      <option value="keep">Gardés</option>
      <option value="drop">Écartés</option>
    </select>
    <button class="primary" id="export">Télécharger les décisions</button>
    <span class="count" id="count"></span>
  </div>
</header>
<div class="warn" id="warn" hidden></div>
<main id="grid"></main>

<script>
const DATA = __DATA__;
const THEMES = __THEMES__;
const KEY = "roam.review.v1";

let decisions = {};
try { decisions = JSON.parse(localStorage.getItem(KEY) || "{}"); }
catch (e) { decisions = {}; }

let persistent = true;
try { localStorage.setItem(KEY + ".probe", "1"); localStorage.removeItem(KEY + ".probe"); }
catch (e) { persistent = false; }
if (!persistent) {
  const warn = document.getElementById("warn");
  warn.hidden = false;
  warn.textContent = "Les décisions ne sont pas sauvegardées ici (page ouverte en fichier local). "
    + "Pense à télécharger avant de fermer, ou lance : python -m roam_pipeline review";
}

function save() {
  if (!persistent) return;
  try { localStorage.setItem(KEY, JSON.stringify(decisions)); } catch (e) {}
}

const grid = document.getElementById("grid");
const themeSel = document.getElementById("theme");
for (const t of THEMES) {
  const o = document.createElement("option");
  o.value = t; o.textContent = t; themeSel.append(o);
}

function visible() {
  const theme = themeSel.value;
  const tier = document.getElementById("tier").value;
  const state = document.getElementById("state").value;
  return DATA.filter(p => {
    if (theme && p.theme !== theme) return false;
    if (tier && String(p.tier) !== tier) return false;
    const d = decisions[p.id] || "";
    if (state === "todo") return !d;
    if (state === "alert") return p.alerts.length > 0;
    if (state === "open") return p.visitable === true;
    if (state === "osm") return p.source === "osm";
    if (state && d !== state) return false;
    return true;
  });
}

function card(p) {
  const el = document.createElement("article");
  const d = decisions[p.id] || "";
  el.className = "card" + (d ? " " + d : "");

  const img = p.image
    ? `<img class="thumb" loading="lazy" src="${p.image}" alt=""
           onerror="this.outerHTML='&lt;div class=&quot;noimg&quot;&gt;image indisponible&lt;/div&gt;'">`
    : `<div class="noimg">pas d'image</div>`;

  const parts = p.parts;
  el.innerHTML = img + `
    <div class="body">
      <div class="tier">NIVEAU ${p.tier} · ${p.collections} collection${p.collections > 1 ? "s" : ""}</div>
      <div class="name">${p.name}</div>
      <div class="meta">${p.theme}${p.dept ? " · " + p.dept : ""}</div>
      ${p.source === "osm"
        ? `<div class="found">Trouvé sur OpenStreetMap — Wikidata ne le classait nulle part</div>`
        : ""}
      <div class="parts">${p.score.toFixed(0)} pts =
        ${parts.notoriete} notoriété (${p.sitelinks} langues)
        ${parts.labels ? " + " + parts.labels + " labels" : ""}
        ${parts.article ? " + " + parts.article + " article" : ""}
        ${parts.image ? " + " + parts.image + " image" : ""}
        ${parts.frwiki ? " + " + parts.frwiki + " fr" : ""}
        ${parts.acces ? (parts.acces > 0 ? " + " : " − ") + Math.abs(parts.acces) + " accès" : ""}
        ${parts.ajustement ? (parts.ajustement > 0 ? " + " : " − ")
          + Math.abs(parts.ajustement) + " curation" : ""}</div>
      ${p.visitable === true
        ? `<div class="open">✓ ouvert au public${p.hours ? ` · ${p.hours}` : ""}</div>`
        : ""}
      ${p.alerts.length ? `<div class="alerts">${p.alerts.map(a => `<div class="alert">⚠︎ ${a}</div>`).join("")}</div>` : ""}
      <div class="tags">${p.labels.map(l => `<span class="tag">${l}</span>`).join("")}</div>
      ${p.wikipedia ? `<a href="${p.wikipedia}" target="_blank" rel="noopener">Voir sur Wikipédia →</a>` : ""}
    </div>
    <div class="actions">
      <button data-act="keep"${d === "keep" ? ' data-on="keep"' : ""}>Garder</button>
      <button data-act="drop"${d === "drop" ? ' data-on="drop"' : ""}>Écarter</button>
      <button data-act="promote" title="Faire remonter">↑</button>
      <button data-act="demote" title="Faire descendre">↓</button>
    </div>`;

  el.querySelectorAll("[data-act]").forEach(btn => {
    btn.onclick = () => {
      const act = btn.dataset.act;
      decisions[p.id] = decisions[p.id] === act ? "" : act;
      if (!decisions[p.id]) delete decisions[p.id];
      save();
      render();
    };
  });
  return el;
}

function render() {
  const list = visible();
  grid.replaceChildren(...list.map(card));
  const done = Object.keys(decisions).length;
  document.getElementById("count").textContent =
    `${list.length} affichés · ${done}/${DATA.length} décidés`;
}

for (const id of ["theme", "tier", "state"]) {
  document.getElementById(id).onchange = render;
}

document.getElementById("export").onclick = () => {
  const header = ["decision", "curator_note", "name", "wikidata_id"];
  const lines = [header.join(",")];
  for (const p of DATA) {
    const d = decisions[p.id];
    if (!d) continue;
    lines.push([d, "", `"${p.name.replace(/"/g, '""')}"`, p.id].join(","));
  }
  const blob = new Blob([lines.join("\\n")], { type: "text/csv;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "review-decisions.csv";
  a.click();
  URL.revokeObjectURL(a.href);
};

render();
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Catalogue de l'application
# ---------------------------------------------------------------------------

def write_app_catalog(
    places: list[Place],
    collections: list[Collection],
    config: Config,
    out_path: Path,
) -> None:
    """Écrit le catalogue dans la forme attendue par l'application.

    Le pipeline nomme ses champs en `snake_case`, l'application en `camelCase` :
    la conversion vit ici plutôt que dans l'application, pour que celle-ci n'ait
    jamais à connaître les conventions du pipeline.

    Seuls les lieux effectivement rattachés à une collection sortent — un lieu
    que l'application ne pourrait afficher nulle part n'a rien à y faire.
    """
    depts = departements()
    used = {cp.place_id for c in collections for cp in c.places}

    app_places = []
    for place in places:
        if place.wikidata_id not in used:
            continue
        dept = depts.get(place.departement_code or "")
        app_places.append(
            {
                "id": place.wikidata_id,
                "slug": place.slug,
                "name": place.name,
                "themeId": place.theme_id,
                "lat": round(place.lat, 6),
                "lon": round(place.lon, 6),
                "radiusM": place.validation_radius_m,
                "score": place.score,
                "departement": dept.name if dept else None,
                "regionCode": place.region_code,
                "summary": place.summary,
                "imageUrl": _thumbnail(place.image_url, 800) or None,
                "wikipediaUrl": place.wikipedia_url,
            }
        )

    app_collections = [
        {
            "slug": collection.slug,
            "name": collection.name,
            "kind": collection.kind,
            "themeId": collection.theme_id,
            "labelId": collection.label_id,
            "geoLevel": collection.geo_level,
            "geoCode": collection.geo_code,
            "placeCount": len(collection.places),
            "tierCounts": collection.tier_counts,
            "places": [
                {"placeId": cp.place_id, "tier": cp.tier, "rank": cp.rank}
                for cp in collection.places
            ],
        }
        for collection in collections
    ]

    payload = {
        "_note": (
            "Généré par `roam_pipeline export-app`. Ne pas éditer à la main. "
            "Descriptions et images issues de Wikipédia et Wikimedia Commons "
            "(CC BY-SA) — l'application doit citer la source."
        ),
        "themes": [
            {
                "id": theme.id,
                "name": theme.name,
                "nameSingular": theme.name_singular,
                "icon": theme.icon,
            }
            for theme in config.themes
        ],
        "places": app_places,
        "collections": app_collections,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    LOG.info(
        "catalogue de l'application : %s (%s lieux, %s collections)",
        out_path,
        len(app_places),
        len(app_collections),
    )
