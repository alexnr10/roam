"""Le référentiel italien : vingt régions, cent dix provinces.

L'équivalent de `data/reference/regions.csv` et `departements.csv`, qui sont
français et écrits à la main. Les codes, les rattachements et les noms italiens
viennent du GeoJSON officiel de l'ISTAT — celui-là même que `geo-layers`
télécharge pour le rattachement par point-dans-polygone. Ce qui est écrit ici,
et qu'aucune donnée ne porte, ce sont les noms FRANÇAIS et leur complément de
nom : « des Pouilles » ne se dérive pas de « Puglia ».

    python scripts/referentiel-it.py

Le choix de la langue est celui du curateur : les collections italiennes
portent des noms français — « Châteaux de Toscane » — parce que le catalogue
est écrit en français. Le jour où l'application proposera d'autres langues,
c'est ce fichier qui aura son équivalent, pas la mécanique.
"""

import csv
import json
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
SOURCE = RACINE / "data" / "reference" / "geo" / "it" / "province.geojson"
SORTIE = RACINE / "data" / "reference" / "it"

#: Les vingt régions, en français, avec leur complément de nom.
#
# Le français ne dérive pas « des Marches » de « Marche », ni « du Frioul » de
# « Friuli ». La table est écrite à la main, exactement comme celle des
# régions françaises.
REGIONS = {
    "01": ("Piémont", "du Piémont"),
    "02": ("Val d'Aoste", "du Val d'Aoste"),
    "03": ("Lombardie", "de Lombardie"),
    "04": ("Trentin-Haut-Adige", "du Trentin-Haut-Adige"),
    "05": ("Vénétie", "de Vénétie"),
    "06": ("Frioul-Vénétie Julienne", "du Frioul-Vénétie Julienne"),
    "07": ("Ligurie", "de Ligurie"),
    "08": ("Émilie-Romagne", "d'Émilie-Romagne"),
    "09": ("Toscane", "de Toscane"),
    "10": ("Ombrie", "d'Ombrie"),
    "11": ("Marches", "des Marches"),
    "12": ("Latium", "du Latium"),
    "13": ("Abruzzes", "des Abruzzes"),
    "14": ("Molise", "du Molise"),
    "15": ("Campanie", "de Campanie"),
    "16": ("Pouilles", "des Pouilles"),
    "17": ("Basilicate", "de Basilicate"),
    "18": ("Calabre", "de Calabre"),
    "19": ("Sicile", "de Sicile"),
    "20": ("Sardaigne", "de Sardaigne"),
}

#: Les provinces que le français NOMME autrement.
#
# Seulement celles dont l'exonyme est courant : on écrit Florence et Padoue,
# mais personne n'écrit « Bellune » pour Belluno. Sur-franciser est une faute
# aussi sûre que sous-franciser — c'est le nom que le lecteur reconnaît qui
# décide, pas la règle.
EXONYMES = {
    "Torino": "Turin",
    "Milano": "Milan",
    "Roma": "Rome",
    "Napoli": "Naples",
    "Firenze": "Florence",
    "Venezia": "Venise",
    "Genova": "Gênes",
    "Padova": "Padoue",
    "Bologna": "Bologne",
    "Mantova": "Mantoue",
    "Verona": "Vérone",
    "Vicenza": "Vicence",
    "Siracusa": "Syracuse",
    "Palermo": "Palerme",
    "Livorno": "Livourne",
    "Siena": "Sienne",
    "Pisa": "Pise",
    "Parma": "Parme",
    "Modena": "Modène",
    "Ferrara": "Ferrare",
    "Ravenna": "Ravenne",
    "Ancona": "Ancône",
    "Perugia": "Pérouse",
    "Trento": "Trente",
    "Treviso": "Trévise",
    "Bergamo": "Bergame",
    "Pavia": "Pavie",
    "Cremona": "Crémone",
    "Salerno": "Salerne",
    "Messina": "Messine",
    "Catania": "Catane",
    "Taranto": "Tarente",
    "Lucca": "Lucques",
    "Piacenza": "Plaisance",
    "Como": "Côme",
    "Savona": "Savone",
    "Reggio nell'Emilia": "Reggio d'Émilie",
    "Reggio Calabria": "Reggio de Calabre",
    "Pesaro e Urbino": "Pesaro et Urbin",
    # Bilingues dans la source : on garde la forme que le français emploie.
    "Valle d'Aosta/Vallée d'Aoste": "Aoste",
    "Bolzano/Bozen": "Bolzano",
    "Monza e della Brianza": "Monza et Brianza",
    # ⚠ La source porte le découpage sarde d'AVANT 2016 : quatre provinces
    # supprimées depuis y figurent encore, sous des noms de promotion
    # touristique. On leur rend leur nom administratif, que la source connaît
    # elle-même par son sigle — OT, CI, VS. Les polygones, eux, pavent bien la
    # Sardaigne : aucun lieu ne reste sans province.
    "Gallura Nord-Est Sardegna": "Olbia-Tempio",
    "Sulcis Iglesiente": "Carbonia-Iglesias",
    "Medio Campidano": "Medio Campidano",
}

VOYELLES = "AEIOUYÀÂÄÉÈÊËÎÏÔÖÛÜ"


def complement(nom: str) -> str:
    """Le complément de nom, par les règles d'élision du français.

    Les provinces portent des noms de villes : presque toutes prennent « de »,
    et seules l'élision devant voyelle et l'article de « L'Aquila » demandent
    une décision. La sortie est relue en entier — c'est une centaine de lignes,
    et une faute s'y verrait dans un titre de collection.
    """
    if nom.startswith("L'"):
        return f"de {nom}"
    if nom.startswith("La "):
        return f"de {nom}"
    if nom[0].upper() in VOYELLES:
        return f"d'{nom}"
    return f"de {nom}"


def main() -> None:
    if not SOURCE.exists():
        raise SystemExit(
            f"{SOURCE} absent — lance d'abord :\n"
            "    python -m roam_pipeline geo-layers --pays-config it"
        )
    donnees = json.loads(SOURCE.read_text(encoding="utf-8"))
    provinces = []
    for feature in donnees["features"]:
        p = feature["properties"]
        nom = EXONYMES.get(p["prov_name"], p["prov_name"])
        provinces.append((p["prov_istat_code"], nom, complement(nom), p["reg_istat_code"]))
    provinces.sort(key=lambda ligne: ligne[0])

    manquantes = {ligne[3] for ligne in provinces} - set(REGIONS)
    if manquantes:
        raise SystemExit(f"régions sans nom français : {sorted(manquantes)}")

    SORTIE.mkdir(parents=True, exist_ok=True)
    with (SORTIE / "regions.csv").open("w", encoding="utf-8", newline="\n") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["code", "name", "de_form"])
        for code, (nom, de) in sorted(REGIONS.items()):
            w.writerow([code, nom, de])

    with (SORTIE / "departements.csv").open("w", encoding="utf-8", newline="\n") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["code", "name", "de_form", "region_code"])
        w.writerows(provinces)

    print(f"{len(REGIONS)} régions et {len(provinces)} provinces écrites dans {SORTIE}")


if __name__ == "__main__":
    main()
