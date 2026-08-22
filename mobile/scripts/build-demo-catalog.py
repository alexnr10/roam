#!/usr/bin/env python3
"""Génère le catalogue de démonstration de l'application.

⚠️  DONNÉES DE DÉMONSTRATION. Les coordonnées sont approximatives (saisies à la
main, précision de l'ordre de la centaine de mètres) et la notoriété est une
appréciation, pas une mesure. Ce fichier existe uniquement pour faire tourner le
prototype avant que le pipeline de curation n'ait produit le vrai catalogue.

Il occupe la place du vrai catalogue en attendant : `roam_pipeline export-app`
écrase ce fichier avec la sortie du pipeline de curation.

    python3 mobile/scripts/build-demo-catalog.py
"""

from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "mobile" / "src" / "data" / "catalog.json"

THEMES = [
    ("chateaux", "Châteaux", "Château", "castle", 200),
    ("abbayes", "Abbayes et monastères", "Abbaye", "abbey", 150),
    ("cathedrales", "Cathédrales et basiliques", "Cathédrale", "cathedral", 120),
    ("villages", "Villages de caractère", "Village", "village", 600),
    ("sommets", "Sommets", "Sommet", "mountain", 1000),
    ("cascades", "Cascades", "Cascade", "waterfall", 300),
    ("gorges", "Gorges et canyons", "Gorges", "canyon", 2000),
    ("plages", "Littoral et plages", "Site", "beach", 500),
    ("grottes", "Grottes et gouffres", "Grotte", "cave", 200),
    ("lacs", "Lacs", "Lac", "lake", 1500),
    ("ponts", "Ponts et viaducs", "Pont", "bridge", 300),
    ("phares", "Phares", "Phare", "lighthouse", 200),
]

# nom, thème, lat, lon, département, notoriété (1-10), labels, résumé
PLACES = [
    ("Mont-Saint-Michel", "abbayes", 48.6360, -1.5115, "50", 10, ["unesco"],
     "Une abbaye posée sur un rocher que la marée isole encore deux fois par jour."),
    ("Château de Chambord", "chateaux", 47.6161, 1.5170, "41", 10, ["unesco"],
     "Le plus démesuré des châteaux de la Loire, et son escalier à double révolution."),
    ("Château de Chenonceau", "chateaux", 47.3249, 1.0705, "37", 9, [],
     "Le château-pont jeté sur le Cher, le plus gracieux de tous."),
    ("Château de Versailles", "chateaux", 48.8049, 2.1204, "78", 10, ["unesco"],
     "L'étalon de la démesure royale, jardins compris."),
    ("Château de Fontainebleau", "chateaux", 48.4021, 2.7003, "77", 8, ["unesco"],
     "Huit siècles de souverains ont ajouté leur aile ; le résultat tient debout."),
    ("Château du Haut-Kœnigsbourg", "chateaux", 48.2494, 7.3444, "67", 8, [],
     "Une forteresse rose reconstruite sur son éperon, avec toute la plaine d'Alsace en contrebas."),
    ("Château de Peyrepertuse", "chateaux", 42.8697, 2.5561, "11", 7, [],
     "Une citadelle cathare accrochée à une crête calcaire, à 800 mètres."),
    ("Palais des Papes", "chateaux", 43.9509, 4.8076, "84", 9, ["unesco"],
     "Le plus grand palais gothique du monde, bâti quand Avignon était Rome."),
    ("Cité de Carcassonne", "chateaux", 43.2061, 2.3639, "11", 9, ["unesco"],
     "Cinquante-deux tours et une double enceinte, restaurées par Viollet-le-Duc."),
    ("Abbaye de Fontenay", "abbayes", 47.6403, 4.3903, "21", 7, ["unesco"],
     "L'abbaye cistercienne la mieux conservée d'Europe, dans un vallon isolé."),
    ("Abbaye du Thoronet", "abbayes", 43.4603, 6.2639, "83", 6, [],
     "L'austérité cistercienne poussée à la perfection acoustique."),
    ("Abbaye de Sénanque", "abbayes", 43.9281, 5.1908, "84", 7, [],
     "Une abbaye romane et son champ de lavande, photographiée mille fois et pourtant."),
    ("Cathédrale de Chartres", "cathedrales", 48.4475, 1.4878, "28", 9, ["unesco"],
     "Les vitraux du XIIIe siècle les plus complets qui nous soient parvenus."),
    ("Cathédrale d'Amiens", "cathedrales", 49.8947, 2.3022, "80", 8, ["unesco"],
     "La plus vaste cathédrale gothique de France ; deux Notre-Dame de Paris tiendraient dedans."),
    ("Basilique Sainte-Marie-Madeleine de Vézelay", "cathedrales", 47.4661, 3.7481, "89", 8, ["unesco"],
     "Le départ historique d'un chemin de Compostelle, sur sa colline éternelle."),
    ("Rocamadour", "villages", 44.7994, 1.6181, "46", 9, [],
     "Un village empilé à la verticale d'une falaise, sanctuaire compris."),
    ("Conques", "villages", 44.5981, 2.3986, "12", 8, ["unesco", "plus-beaux-villages"],
     "Un village médiéval intact, et le trésor d'orfèvrerie le plus complet de France."),
    ("Saint-Cirq-Lapopie", "villages", 44.4658, 1.6714, "46", 8, ["plus-beaux-villages"],
     "Perché cent mètres au-dessus du Lot, sans une maison qui dépasse."),
    ("Gordes", "villages", 43.9114, 5.2003, "84", 8, ["plus-beaux-villages"],
     "Des maisons de pierre sèche en cascade sur un piton du Luberon."),
    ("Eguisheim", "villages", 48.0433, 7.3061, "68", 7, ["plus-beaux-villages"],
     "Un village concentrique, construit en cercles autour de son château."),
    ("Riquewihr", "villages", 48.1667, 7.2978, "68", 7, ["plus-beaux-villages"],
     "Des remparts, des colombages, et des vignes qui montent jusqu'aux portes."),
    ("Locronan", "villages", 48.0972, -4.2089, "29", 7, ["plus-beaux-villages"],
     "Une place de granit sans un fil électrique apparent."),
    ("Mont Blanc", "sommets", 45.8326, 6.8652, "74", 10, [],
     "Le toit de l'Europe occidentale, 4 806 mètres."),
    ("Aiguille du Midi", "sommets", 45.8789, 6.8873, "74", 8, [],
     "3 842 mètres atteints en vingt minutes de téléphérique, face aux glaciers."),
    ("Puy de Dôme", "sommets", 45.7722, 2.9644, "63", 8, ["unesco"],
     "Le volcan qui domine la chaîne des Puys, et son temple de Mercure au sommet."),
    ("Pic du Midi de Bigorre", "sommets", 42.9369, 0.1411, "65", 7, [],
     "Un observatoire à 2 877 mètres, et l'un des ciels nocturnes les plus purs d'Europe."),
    ("Cirque de Gavarnie", "sommets", 42.6975, -0.0089, "65", 8, ["unesco"],
     "Un amphithéâtre de 1 500 mètres de haut, et la plus grande cascade de France."),
    ("Cascade du Hérisson", "cascades", 46.6100, 5.8700, "39", 7, [],
     "Sept cascades enchaînées sur trois kilomètres de sentier forestier."),
    ("Cascades des Tufs", "cascades", 46.7050, 5.6400, "39", 6, [],
     "L'eau sort de la roche en éventail, au fond d'une reculée jurassienne."),
    ("Cascade de Gavarnie", "cascades", 42.6944, -0.0075, "65", 7, [],
     "423 mètres de chute libre depuis le cirque."),
    ("Gorges du Verdon", "gorges", 43.7500, 6.3300, "04", 9, [],
     "Sept cents mètres de calcaire vertical et une eau turquoise ; le point d'entrée est La Palud."),
    ("Gorges du Tarn", "gorges", 44.3200, 3.3200, "48", 8, ["unesco"],
     "Cinquante kilomètres de canyon entre deux causses."),
    ("Cirque de Navacelles", "gorges", 43.8917, 3.5083, "34", 7, ["unesco"],
     "Un méandre abandonné par sa rivière, creusé de 300 mètres."),
    ("Dune du Pilat", "plages", 44.5883, -1.2119, "33", 9, [],
     "La plus haute dune d'Europe, océan d'un côté, forêt de l'autre."),
    ("Falaises d'Étretat", "plages", 49.7069, 0.2050, "76", 9, [],
     "Trois arches de craie que tous les peintres impressionnistes ont tenté."),
    ("Pointe du Raz", "plages", 48.0383, -4.7375, "29", 8, [],
     "L'extrémité ouest de la Bretagne, et la mer qui s'y comporte en conséquence."),
    ("Cap Fréhel", "plages", 48.6853, -2.3181, "22", 7, [],
     "Des falaises de grès rose de 70 mètres, et des colonies d'oiseaux marins."),
    ("Calanque d'En-Vau", "plages", 43.2000, 5.5100, "13", 8, [],
     "Une crique d'eau claire au fond d'une faille calcaire, uniquement à pied ou en bateau."),
    ("Gouffre de Padirac", "grottes", 44.8567, 1.7500, "46", 8, [],
     "Un puits de 75 mètres, puis une rivière souterraine qu'on descend en barque."),
    ("Grotte de Lascaux IV", "grottes", 45.0533, 1.1667, "24", 8, ["unesco"],
     "Le fac-similé intégral de la chapelle Sixtine de la préhistoire."),
    ("Grotte Chauvet 2", "grottes", 44.3833, 4.4167, "07", 7, ["unesco"],
     "Les plus anciennes peintures connues, restituées à l'identique."),
    ("Lac d'Annecy", "lacs", 45.8500, 6.1700, "74", 8, [],
     "Le lac le plus transparent d'Europe, cerné de sommets."),
    ("Lac de Sainte-Croix", "lacs", 43.7600, 6.2200, "04", 7, [],
     "L'eau turquoise qui prolonge le Verdon, en pédalo si on veut."),
    ("Pont du Gard", "ponts", 43.9475, 4.5353, "30", 9, ["unesco"],
     "Trois étages d'aqueduc romain intacts depuis deux mille ans."),
    ("Viaduc de Millau", "ponts", 44.0797, 3.0225, "12", 8, [],
     "343 mètres de haut : le pont le plus élevé du monde, et il est autoroutier."),
    ("Phare de Cordouan", "phares", 45.5853, -1.1753, "33", 7, ["unesco"],
     "Le « Versailles des mers », en pleine embouchure de la Gironde."),
]

TIER1, TIER2 = 3, 5
MIN_PLACES = 4
LABEL_BONUS = {"unesco": 20, "plus-beaux-villages": 12}
LABEL_NAMES = {
    "unesco": "Patrimoine mondial de l'UNESCO",
    "plus-beaux-villages": "Les Plus Beaux Villages de France",
}


def slugify(value: str) -> str:
    import re
    import unicodedata

    ascii_only = (
        unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    )
    return re.sub(r"-{2,}", "-", re.sub(r"[^a-z0-9]+", "-", ascii_only).strip("-"))


def load_reference() -> tuple[dict, dict]:
    base = ROOT / "pipeline" / "data" / "reference"
    with (base / "departements.csv").open(encoding="utf-8") as fh:
        depts = {row["code"]: row for row in csv.DictReader(fh)}
    with (base / "regions.csv").open(encoding="utf-8") as fh:
        regions = {row["code"]: row for row in csv.DictReader(fh)}
    return depts, regions


def assign_tiers(members: list[dict]) -> list[dict]:
    ordered = sorted(members, key=lambda m: (-m["score"], m["name"]))
    out = []
    for index, member in enumerate(ordered):
        tier = 1 if index < TIER1 else 2 if index < TIER1 + TIER2 else 3
        out.append({"placeId": member["id"], "tier": tier, "rank": index + 1})
    return out


def main() -> int:
    depts, regions = load_reference()
    radius = {t[0]: t[4] for t in THEMES}

    places = []
    for name, theme, lat, lon, dept_code, renown, labels, summary in PLACES:
        dept = depts[dept_code]
        places.append(
            {
                "id": f"DEMO-{slugify(name)}",
                "slug": slugify(name),
                "name": name,
                "themeId": theme,
                "lat": lat,
                "lon": lon,
                "radiusM": radius[theme],
                "score": renown * 10 + sum(LABEL_BONUS.get(l, 0) for l in labels),
                "departement": dept["name"],
                "regionCode": dept["region_code"],
                "summary": summary,
                "labels": labels,
            }
        )

    by_id = {p["id"]: p for p in places}
    collections = []

    for theme_id, name, _singular, _icon, _radius in THEMES:
        members = [p for p in places if p["themeId"] == theme_id]
        if len(members) >= MIN_PLACES:
            collections.append(
                {"slug": f"theme-{theme_id}", "name": name, "kind": "theme",
                 "themeId": theme_id, "places": assign_tiers(members)}
            )

    for label_id, label_name in LABEL_NAMES.items():
        members = [p for p in places if label_id in p["labels"]]
        if len(members) >= MIN_PLACES:
            collections.append(
                {"slug": f"label-{label_id}", "name": label_name, "kind": "label",
                 "labelId": label_id, "places": assign_tiers(members)}
            )

    by_region: dict[str, list] = defaultdict(list)
    for place in places:
        by_region[place["regionCode"]].append(place)
    for code, members in by_region.items():
        if len(members) >= MIN_PLACES:
            collections.append(
                {"slug": f"geo-region-{code}", "name": f"Le meilleur {regions[code]['de_form']}",
                 "kind": "geo", "geoLevel": "region", "geoCode": code,
                 "places": assign_tiers(members)}
            )

    collections.append(
        {"slug": "geo-country-fr", "name": "Le meilleur de France", "kind": "geo",
         "geoLevel": "country", "geoCode": "FR", "places": assign_tiers(places)}
    )

    for collection in collections:
        counts = [0, 0, 0]
        for member in collection["places"]:
            counts[member["tier"] - 1] += 1
        collection["placeCount"] = len(collection["places"])
        collection["tierCounts"] = counts

    for place in places:
        place.pop("labels", None)

    catalog = {
        "_note": (
            "DONNÉES DE DÉMONSTRATION — coordonnées approximatives, notoriété "
            "appréciée à la main. Généré par mobile/scripts/build-demo-catalog.py. "
            "À remplacer par la sortie du pipeline de curation."
        ),
        "themes": [
            {"id": t[0], "name": t[1], "nameSingular": t[2], "icon": t[3]} for t in THEMES
        ],
        "places": places,
        "collections": collections,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{len(places)} lieux, {len(collections)} collections → {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
