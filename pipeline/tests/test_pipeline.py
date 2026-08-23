"""Tests hors ligne du pipeline : scoring, niveaux, règles de collection.

Aucune requête réseau — ces tests valident la logique métier, pas Wikidata.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from roam_pipeline.collections import (
    apply_geographic_scope,
    apply_notoriety_floor,
    build_all,
    dedupe,
    dedupe_across_themes,
    haversine_m,
)
from roam_pipeline.config import load_config
from roam_pipeline.export import _sql_str, write_seed_sql
from roam_pipeline.geo import departements, normalize_dept_code, region_of, regions
from roam_pipeline.models import Place, slugify
from roam_pipeline.fetch import enrich_departements
from roam_pipeline.geocode import AddressClient, CommuneClient, departement_from_insee
from roam_pipeline.wikipedia import title_from_url
from roam_pipeline.score import assign_tiers, compute_score, label_bonus, score_all

CONFIG = load_config()


def make_place(name: str, theme: str = "chateaux", **kwargs) -> Place:
    defaults = dict(
        wikidata_id=f"Q{abs(hash(name)) % 10_000_000}",
        name=name,
        theme_id=theme,
        lat=45.0,
        lon=2.0,
        sitelinks=5,
        departement_code="15",
        region_code="84",
    )
    defaults.update(kwargs)
    return Place(**defaults)


class TestConfig(unittest.TestCase):
    def test_config_loads(self):
        self.assertTrue(CONFIG.themes)
        self.assertTrue(CONFIG.labels)
        self.assertEqual(CONFIG.theme("chateaux").name, "Châteaux")

    def test_every_theme_has_a_source_or_is_pending(self):
        # Classe Wikidata, listes officielles, ou termes en attente de
        # résolution — mais jamais rien du tout.
        for theme in CONFIG.themes:
            self.assertTrue(
                theme.wikidata_classes or theme.from_labels or theme.search, theme.id
            )

    def test_label_sourced_themes_reference_known_labels(self):
        known = {label.id for label in CONFIG.labels}
        for theme in CONFIG.themes:
            for label_id in theme.from_labels:
                self.assertIn(label_id, known, theme.id)

    def test_fetch_floor_is_never_above_editorial_floor(self):
        # Collecter plus strictement que le plancher éditorial rendrait ce
        # dernier inopérant, et il faudrait recollecter pour l'assouplir.
        for theme in CONFIG.themes:
            self.assertLessEqual(theme.fetch_min_sitelinks, theme.min_sitelinks, theme.id)

    def test_non_manual_labels_are_resolved_or_pending(self):
        # Un label sans qid doit porter un terme de recherche : il est en attente
        # de résolution, pas silencieusement cassé.
        for label in CONFIG.labels:
            if not label.is_manual:
                self.assertTrue(label.qid or label.search, label.id)

    def test_a_theme_without_source_is_rejected(self):
        from roam_pipeline.config import Theme, _validate

        orphan = Theme(
            id="orphelin", name="Orphelin", name_singular="Orphelin", icon="",
            radius_m=100, min_sitelinks=1, fetch_min_sitelinks=1, cap=10, wikidata_classes=[],
        )
        with self.assertRaises(ValueError):
            _validate([orphan], CONFIG.labels)

    def test_a_theme_pointing_at_an_unknown_label_is_rejected(self):
        from roam_pipeline.config import Theme, _validate

        broken = Theme(
            id="casse", name="Cassé", name_singular="Cassé", icon="",
            radius_m=100, min_sitelinks=1, fetch_min_sitelinks=1, cap=10, wikidata_classes=[],
            from_labels=["label-inexistant"],
        )
        with self.assertRaises(ValueError):
            _validate([broken], CONFIG.labels)


class TestGeo(unittest.TestCase):
    def test_reference_completeness(self):
        self.assertEqual(len(departements()), 101)
        self.assertEqual(len(regions()), 18)

    def test_every_departement_maps_to_a_region(self):
        for code in departements():
            self.assertIsNotNone(region_of(code), code)

    def test_de_form_is_grammatical(self):
        # Le complément de nom est stocké, pas dérivé : c'est ce qui donne
        # « Châteaux du Cantal » et pas « Châteaux de Cantal ».
        self.assertEqual(departements()["15"].de_form, "du Cantal")
        self.assertEqual(departements()["50"].de_form, "de la Manche")
        self.assertEqual(departements()["40"].de_form, "des Landes")
        self.assertEqual(departements()["01"].de_form, "de l'Ain")

    def test_corsica_codes(self):
        self.assertIn("2A", departements())
        self.assertIn("2B", departements())

    def test_normalize_dept_code(self):
        self.assertEqual(normalize_dept_code("1"), "01")
        self.assertEqual(normalize_dept_code("2a"), "2A")
        self.assertEqual(normalize_dept_code("999"), None)
        self.assertEqual(normalize_dept_code(None), None)


class TestScoring(unittest.TestCase):
    def test_score_grows_with_notoriety(self):
        low = compute_score(make_place("A", sitelinks=2), CONFIG)
        high = compute_score(make_place("B", sitelinks=30), CONFIG)
        self.assertGreater(high, low)

    def test_notoriety_has_diminishing_returns(self):
        # Passer de 2 à 6 langues compte plus que passer de 40 à 44.
        a = compute_score(make_place("a", sitelinks=2), CONFIG)
        b = compute_score(make_place("b", sitelinks=6), CONFIG)
        c = compute_score(make_place("c", sitelinks=40), CONFIG)
        d = compute_score(make_place("d", sitelinks=44), CONFIG)
        self.assertGreater(b - a, d - c)

    def test_label_stacking_caps_small_labels(self):
        unesco = label_bonus(["unesco"], CONFIG)
        stacked = label_bonus(
            ["monument-historique-inscrit", "parc-national", "pavillon-bleu"], CONFIG
        )
        self.assertGreater(unesco, stacked)

    def test_label_stacking_adds_half_of_second(self):
        both = label_bonus(["unesco", "jardin-remarquable"], CONFIG)
        expected = (
            CONFIG.label("unesco").score_bonus + CONFIG.label("jardin-remarquable").score_bonus / 2
        )
        self.assertAlmostEqual(both, expected)

    def test_unknown_label_is_ignored(self):
        self.assertEqual(label_bonus(["label-qui-nexiste-pas"], CONFIG), 0.0)

    def test_image_and_frwiki_bonuses_apply(self):
        bare = compute_score(make_place("bare"), CONFIG)
        rich = compute_score(
            make_place("rich", image_url="https://example.org/x.jpg", has_frwiki=True), CONFIG
        )
        self.assertAlmostEqual(
            rich - bare, CONFIG.scoring.has_image_bonus + CONFIG.scoring.has_frwiki_bonus
        )


class TestArticleSignal(unittest.TestCase):
    """La taille d'article doit classer là où le décompte de langues est plat."""

    def _cascade(self, article_bytes: int) -> Place:
        return make_place(
            f"cascade-{article_bytes}", theme="cascades", sitelinks=2,
            has_frwiki=True, article_bytes=article_bytes,
        )

    def test_a_longer_article_scores_higher(self):
        stub = compute_score(self._cascade(1500), CONFIG)
        full = compute_score(self._cascade(30000), CONFIG)
        self.assertGreater(full, stub)

    def test_it_separates_places_with_identical_notoriety(self):
        # Deux cascades à deux langues : sans ce signal, elles seraient à égalité
        # et leur ordre dans la collection serait arbitraire.
        a, b = self._cascade(2000), self._cascade(40000)
        self.assertNotEqual(compute_score(a, CONFIG), compute_score(b, CONFIG))

    def test_growth_is_sublinear(self):
        # Quatre mille octets de plus valent beaucoup au départ et presque rien
        # ensuite : un article deux fois plus long n'est pas deux fois plus
        # remarquable, sinon les articles fleuves écraseraient tout.
        early = compute_score(self._cascade(5000), CONFIG) - compute_score(self._cascade(1000), CONFIG)
        late = compute_score(self._cascade(24000), CONFIG) - compute_score(self._cascade(20000), CONFIG)
        self.assertGreater(early, late * 3)

    def test_a_missing_article_costs_nothing_extra(self):
        self.assertEqual(
            compute_score(self._cascade(0), CONFIG),
            compute_score(make_place("sans", theme="cascades", sitelinks=2, has_frwiki=True), CONFIG),
        )


class TestWikipediaTitles(unittest.TestCase):
    def test_decodes_and_unslugs(self):
        self.assertEqual(
            title_from_url("https://fr.wikipedia.org/wiki/Ch%C3%A2teau_de_Chambord"),
            "Château de Chambord",
        )

    def test_ignores_anything_that_is_not_an_article(self):
        self.assertIsNone(title_from_url(None))
        self.assertIsNone(title_from_url("https://example.org/page"))
        self.assertIsNone(title_from_url("https://fr.wikipedia.org/wiki/"))


class TestTiers(unittest.TestCase):
    def test_tier_sizes_are_respected(self):
        places = [make_place(f"P{i}", sitelinks=200 - i) for i in range(60)]
        score_all(places, CONFIG)
        counts = {1: 0, 2: 0, 3: 0}
        for _, tier, _ in assign_tiers(places, CONFIG.tiers):
            counts[tier] += 1
        self.assertLessEqual(counts[1], CONFIG.tiers.tier1_size)
        self.assertLessEqual(counts[2], CONFIG.tiers.tier2_size)

    def test_floor_prevents_filling_tier1_with_weak_places(self):
        # Dix lieux obscurs ne doivent pas devenir « les incontournables »
        # simplement parce qu'ils sont les dix seuls de leur collection.
        weak = [make_place(f"W{i}", sitelinks=1) for i in range(10)]
        score_all(weak, CONFIG)
        tiers = {tier for _, tier, _ in assign_tiers(weak, CONFIG.tiers)}
        self.assertNotIn(1, tiers)

    def test_ranking_is_by_descending_score(self):
        places = [make_place(f"P{i}", sitelinks=i) for i in range(1, 20)]
        score_all(places, CONFIG)
        scores = [p.score for p, _, _ in assign_tiers(places, CONFIG.tiers)]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_ordering_is_stable_on_score_ties(self):
        places = [make_place(name, sitelinks=5) for name in ("Zèbre", "Alpha", "Milieu")]
        score_all(places, CONFIG)
        names = [p.name for p, _, _ in assign_tiers(places, CONFIG.tiers)]
        self.assertEqual(names, ["Alpha", "Milieu", "Zèbre"])


class TestDedupe(unittest.TestCase):
    def test_haversine_is_sane(self):
        # Paris → Lyon ≈ 392 km
        self.assertAlmostEqual(haversine_m(48.8566, 2.3522, 45.7640, 4.8357) / 1000, 392, delta=8)

    def test_near_identical_places_are_merged(self):
        a = make_place("Château de X", lat=45.0, lon=2.0, sitelinks=20)
        b = make_place("Chapelle du château de X", lat=45.0005, lon=2.0005, sitelinks=3)
        score_all([a, b], CONFIG)
        kept = dedupe([a, b])
        self.assertEqual([p.name for p in kept], ["Château de X"])

    def test_distinct_places_are_both_kept(self):
        a = make_place("Château A", lat=45.0, lon=2.0)
        b = make_place("Château B", lat=45.1, lon=2.1)
        score_all([a, b], CONFIG)
        self.assertEqual(len(dedupe([a, b])), 2)

    def test_same_location_different_themes_are_kept(self):
        a = make_place("Site", theme="chateaux", lat=45.0, lon=2.0)
        b = make_place("Site naturel", theme="cascades", lat=45.0, lon=2.0)
        score_all([a, b], CONFIG)
        self.assertEqual(len(dedupe([a, b])), 2)


class TestInseeDepartement(unittest.TestCase):
    """Le code de commune porte celui du département — mais pas au même endroit."""

    def test_metropole(self):
        self.assertEqual(departement_from_insee("63113"), "63")
        self.assertEqual(departement_from_insee("75056"), "75")

    def test_corse_uses_a_letter(self):
        self.assertEqual(departement_from_insee("2A004"), "2A")
        self.assertEqual(departement_from_insee("2B033"), "2B")

    def test_outre_mer_uses_three_digits(self):
        self.assertEqual(departement_from_insee("97411"), "974")
        self.assertEqual(departement_from_insee("97105"), "971")

    def test_garbage_is_rejected(self):
        for value in (None, "", "x", "12", "abcde"):
            self.assertIsNone(departement_from_insee(value), value)

    def test_every_result_is_a_known_departement(self):
        # Le code déduit doit exister dans le référentiel, sinon le lieu
        # serait rattaché à un département fantôme.
        from roam_pipeline.geo import departements

        for citycode in ("63113", "2A004", "2B033", "97411", "01001", "95001"):
            self.assertIn(departement_from_insee(citycode), departements(), citycode)


class TestReverseGeocoding(unittest.TestCase):
    """Analyse de la réponse de l'API Adresse, sans réseau."""

    class _Response:
        def __init__(self, text: str):
            self.text = text

        def raise_for_status(self):
            return None

    class _Session:
        def __init__(self, text: str):
            self.text = text
            self.sent = None
            self.headers = {}

        def post(self, url, files=None, timeout=None):
            self.sent = files["data"][1]
            return TestReverseGeocoding._Response(self.text)

    def _client(self, text: str) -> tuple[AddressClient, "_Session"]:
        client = AddressClient(min_interval_s=0)
        session = self._Session(text)
        client._session = session
        return client, session

    def test_reads_the_city_code_back_by_identifier(self):
        client, session = self._client(
            "id,latitude,longitude,result_citycode,result_city\n"
            "Q1,45.5,2.5,63113,Orcival\n"
            "Q2,42.1,9.1,2B033,Corte\n"
        )
        codes = client.reverse([("Q1", 45.5, 2.5), ("Q2", 42.1, 9.1)])
        self.assertEqual(codes, {"Q1": "63113", "Q2": "2B033"})
        # Les coordonnées partent bien dans le corps de la requête.
        self.assertIn("45.500000", session.sent)

    def test_a_point_outside_france_returns_nothing(self):
        client, _ = self._client("id,latitude,longitude,result_citycode\nQ9,51.5,-0.1,\n")
        self.assertEqual(client.reverse([("Q9", 51.5, -0.1)]), {})

    def test_no_points_no_request(self):
        client, session = self._client("")
        self.assertEqual(client.reverse([]), {})
        self.assertIsNone(session.sent)


class TestTwoTierGeocoding(unittest.TestCase):
    """L'API Géo doit rattraper ce que l'API Adresse ne trouve pas."""

    class _Address:
        def __init__(self, codes: dict[str, str]):
            self.codes = codes
            self.calls = 0

        def reverse(self, points):
            self.calls += 1
            return {i: self.codes[i] for i, _, _ in points if i in self.codes}

    class _Commune:
        def __init__(self, answer):
            self.answer = answer
            self.calls = 0

        def locate(self, lat, lon):
            self.calls += 1
            return self.answer

    def test_the_second_pass_only_sees_what_the_first_missed(self):
        trouve = make_place("Château", wikidata_id="Q1", departement_code=None)
        isole = make_place("Cascade du Rudlin", wikidata_id="Q2", departement_code=None)
        address = self._Address({"Q1": "63113"})
        commune = self._Commune(("88", "44"))

        resolved = enrich_departements([trouve, isole], address, commune)

        self.assertEqual(resolved, 2)
        self.assertEqual(trouve.departement_code, "63")
        self.assertEqual(isole.departement_code, "88")
        # Un seul appel unitaire : celui du lieu que la première passe a raté.
        self.assertEqual(commune.calls, 1)

    def test_the_region_follows_from_the_departement(self):
        place = make_place("Cascade", wikidata_id="Q2", departement_code=None, region_code=None)
        enrich_departements([place], self._Address({}), self._Commune(("88", "99")))
        # Le référentiel local fait foi sur le code de région, pas la réponse.
        self.assertEqual(place.region_code, "44")

    def test_a_point_at_sea_stays_unresolved(self):
        place = make_place("Îlot", wikidata_id="Q3", departement_code=None)
        self.assertEqual(enrich_departements([place], self._Address({}), self._Commune(None)), 0)
        self.assertIsNone(place.departement_code)

    def test_places_already_located_are_left_alone(self):
        place = make_place("Connu", departement_code="15")
        address = self._Address({})
        self.assertEqual(enrich_departements([place], address, self._Commune(None)), 0)
        self.assertEqual(address.calls, 0)


class TestGeographicScope(unittest.TestCase):
    def test_a_place_without_a_departement_is_dropped(self):
        # Sans département, un lieu n'entre dans aucune collection
        # géographique : il ne resterait que dans « Le meilleur de France ».
        places = [
            make_place("Mehetia", departement_code=None),
            make_place("Puy de Dôme", departement_code="63"),
        ]
        kept = apply_geographic_scope(places, CONFIG)
        self.assertEqual([p.name for p in kept], ["Puy de Dôme"])

    def test_overseas_departements_are_kept(self):
        # La ligne passe entre DOM et COM, pas entre métropole et outre-mer.
        for code in ("971", "972", "973", "974", "976"):
            kept = apply_geographic_scope([make_place("outre-mer", departement_code=code)], CONFIG)
            self.assertEqual(len(kept), 1, code)


class TestThemePriority(unittest.TestCase):
    """L'ordre des thèmes encode des arbitrages constatés sur de vrais lieux."""

    def _wins(self, *themes: str) -> str:
        places = [make_place("X", theme=t, wikidata_id="Q1") for t in themes]
        return dedupe_across_themes(places, CONFIG)[0].theme_id

    def test_a_waterfall_in_a_gorge_is_a_waterfall(self):
        # Le Trou de Fer était classé en gorges.
        self.assertEqual(self._wins("gorges", "cascades"), "cascades")

    def test_a_painted_cave_is_a_cave(self):
        # Lascaux est un site archéologique, mais on y va pour la grotte.
        self.assertEqual(self._wins("megalithes", "grottes"), "grottes")

    def test_a_castle_housing_a_museum_is_a_castle(self):
        # Castelnaud était classé en musées.
        self.assertEqual(self._wins("musees", "chateaux"), "chateaux")

    def test_a_museum_in_a_palace_is_a_museum(self):
        # Le Louvre est un palais, mais c'est d'abord un musée.
        self.assertEqual(self._wins("monuments", "musees"), "musees")


class TestCrossThemeDedupe(unittest.TestCase):
    """Un lieu ne doit exister qu'une fois, sous son thème le plus spécifique."""

    def _same_place_as(self, *themes: str) -> list[Place]:
        return [
            make_place("Château de Versailles", theme=t, wikidata_id="Q2946")
            for t in themes
        ]

    def test_the_more_specific_theme_wins(self):
        # Versailles est un palais, mais c'est d'abord un château.
        kept = dedupe_across_themes(self._same_place_as("monuments", "chateaux"), CONFIG)
        self.assertEqual([p.theme_id for p in kept], ["chateaux"])

    def test_order_of_arrival_does_not_matter(self):
        forward = dedupe_across_themes(self._same_place_as("chateaux", "monuments"), CONFIG)
        backward = dedupe_across_themes(self._same_place_as("monuments", "chateaux"), CONFIG)
        self.assertEqual(forward[0].theme_id, backward[0].theme_id)

    def test_a_museum_in_a_palace_stays_a_museum(self):
        kept = dedupe_across_themes(self._same_place_as("monuments", "musees"), CONFIG)
        self.assertEqual([p.theme_id for p in kept], ["musees"])

    def test_distinct_places_are_untouched(self):
        places = [
            make_place("A", theme="chateaux", wikidata_id="Q1"),
            make_place("B", theme="monuments", wikidata_id="Q2"),
        ]
        self.assertEqual(len(dedupe_across_themes(places, CONFIG)), 2)


class TestPinnedPlaces(unittest.TestCase):
    """Le curateur doit pouvoir imposer un lieu que les seuils écarteraient."""

    def test_a_pinned_place_ignores_the_notoriety_floor(self):
        # Le château d'Auvers-sur-Oise reçoit le monde entier sans être
        # documenté en dix langues.
        floor = CONFIG.theme("chateaux").min_sitelinks
        obscur = make_place("Château d'Auvers", theme="chateaux", sitelinks=floor - 5)
        self.assertEqual(apply_notoriety_floor([obscur], CONFIG), [])
        obscur.pinned = True
        self.assertEqual(len(apply_notoriety_floor([obscur], CONFIG)), 1)

    def test_a_pinned_place_imposes_its_theme(self):
        # L'ordre des thèmes place `chateaux` avant `jardins` ; l'épinglage
        # doit primer, parce que c'est une décision explicite.
        auto = make_place("Giverny", theme="chateaux", wikidata_id="Q1")
        choisi = make_place("Giverny", theme="jardins", wikidata_id="Q1")
        choisi.pinned = True
        kept = dedupe_across_themes([auto, choisi], CONFIG)
        self.assertEqual([p.theme_id for p in kept], ["jardins"])

    def test_the_theme_order_still_decides_between_two_pinned(self):
        a = make_place("X", theme="jardins", wikidata_id="Q1")
        b = make_place("X", theme="chateaux", wikidata_id="Q1")
        a.pinned = b.pinned = True
        self.assertEqual(dedupe_across_themes([a, b], CONFIG)[0].theme_id, "chateaux")


class TestManualCsv(unittest.TestCase):
    def test_comment_lines_are_ignored(self):
        # Les fichiers saisis à la main portent des explications en tête ; sans
        # ce filtre, la première ligne de commentaire deviendrait l'en-tête.
        import tempfile

        from roam_pipeline.fetch import _read_csv_rows

        path = Path(tempfile.mkdtemp()) / "places.csv"
        path.write_text(
            "# explication\n\nwikidata_id,theme_id,note\nQ42,jardins,Giverny\n",
            encoding="utf-8",
        )
        rows = _read_csv_rows(path)
        self.assertEqual(rows, [{"wikidata_id": "Q42", "theme_id": "jardins", "note": "Giverny"}])


class TestNotorietyFloor(unittest.TestCase):
    def test_places_below_their_theme_floor_are_dropped(self):
        floor = CONFIG.theme("sommets").min_sitelinks
        places = [
            make_place("obscur", theme="sommets", sitelinks=floor - 1),
            make_place("connu", theme="sommets", sitelinks=floor + 5),
        ]
        kept = apply_notoriety_floor(places, CONFIG)
        self.assertEqual([p.name for p in kept], ["connu"])

    def test_floor_is_per_theme(self):
        # Une cascade à 3 langues reste ; un sommet à 3 langues part.
        places = [
            make_place("cascade", theme="cascades", sitelinks=3),
            make_place("sommet", theme="sommets", sitelinks=3),
        ]
        self.assertEqual([p.name for p in apply_notoriety_floor(places, CONFIG)], ["cascade"])

    def test_unknown_theme_is_dropped(self):
        self.assertEqual(apply_notoriety_floor([make_place("x", theme="inconnu")], CONFIG), [])


class TestCollections(unittest.TestCase):
    def _spread(self, count: int, theme: str = "chateaux", dept: str = "15") -> list[Place]:
        places = [
            make_place(
                f"{theme}-{dept}-{i}",
                theme=theme,
                sitelinks=30 - (i % 20),
                lat=45.0 + i * 0.05,
                lon=2.0 + i * 0.05,
                departement_code=dept,
                region_code="84",
                image_url="https://example.org/x.jpg",
            )
            for i in range(count)
        ]
        return score_all(places, CONFIG)

    def test_small_collections_are_dropped(self):
        # « Cascades de la Creuse : 2 lieux » n'est pas une collection.
        _, collections = build_all(self._spread(3), CONFIG)
        self.assertEqual(collections, [])

    def test_collection_appears_once_threshold_is_met(self):
        _, collections = build_all(self._spread(CONFIG.collections.min_places), CONFIG)
        self.assertTrue(collections)
        for collection in collections:
            self.assertGreaterEqual(len(collection.places), CONFIG.collections.min_places)

    def test_cap_is_enforced(self):
        _, collections = build_all(self._spread(200), CONFIG)
        theme_collection = next(c for c in collections if c.slug == "theme-chateaux")
        self.assertLessEqual(len(theme_collection.places), CONFIG.theme("chateaux").cap)

    def test_a_place_belongs_to_several_collections(self):
        # C'est tout le produit : un lieu compte dans plusieurs collections.
        places, collections = build_all(self._spread(30), CONFIG)
        target = places[0].wikidata_id
        memberships = [c.slug for c in collections for cp in c.places if cp.place_id == target]
        self.assertGreaterEqual(len(memberships), 3)

    def test_cross_collection_is_named_grammatically(self):
        _, collections = build_all(self._spread(30), CONFIG)
        names = {c.slug: c.name for c in collections}
        self.assertEqual(names.get("chateaux-departement-15"), "Châteaux du Cantal")
        self.assertEqual(names.get("geo-departement-15"), "Le meilleur du Cantal")

    def test_orphan_places_are_dropped(self):
        # Deux cascades seules : aucune collection viable nulle part, donc
        # elles ne servent à rien et sortent du catalogue.
        retained, collections = build_all(self._spread(2, theme="cascades", dept="48"), CONFIG)
        self.assertEqual(retained, [])
        self.assertEqual(collections, [])

    def test_thin_theme_survives_through_geography(self):
        # 30 châteaux + 2 cascades dans la même région : il n'y a pas assez de
        # cascades pour une collection thématique, mais elles restent au
        # catalogue via la collection régionale. C'est le mécanisme qui évite
        # qu'un utilisateur en zone creuse n'ait rien à visiter.
        places = self._spread(30) + self._spread(2, theme="cascades", dept="48")
        retained, collections = build_all(places, CONFIG)
        slugs = {c.slug for c in collections}
        self.assertNotIn("theme-cascades", slugs)
        self.assertIn("geo-region-84", slugs)
        self.assertEqual(len([p for p in retained if p.theme_id == "cascades"]), 2)

    def test_country_collection_exists(self):
        _, collections = build_all(self._spread(30), CONFIG)
        self.assertIn("geo-country-fr", {c.slug for c in collections})


class TestExport(unittest.TestCase):
    def test_sql_escapes_quotes(self):
        self.assertEqual(_sql_str("Château d'If"), "'Château d''If'")
        self.assertEqual(_sql_str(None), "null")
        self.assertEqual(_sql_str(""), "null")

    def test_seed_sql_is_generated_and_quotes_survive(self):
        import tempfile

        places = score_all([make_place("Château d'If", sitelinks=40)], CONFIG)
        _, collections = build_all(places, CONFIG)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "seed.sql"
            write_seed_sql(places, collections, CONFIG, path)
            sql = path.read_text(encoding="utf-8")
        self.assertIn("begin;", sql)
        self.assertIn("commit;", sql)
        self.assertIn("Château d''If", sql)
        # Le pipeline ne publie rien.
        self.assertIn("'draft'", sql)
        self.assertNotIn("'published'", sql)


class TestSlugify(unittest.TestCase):
    def test_accents_and_punctuation(self):
        self.assertEqual(slugify("Château d'If"), "chateau-d-if")
        self.assertEqual(slugify("Mont-Saint-Michel"), "mont-saint-michel")
        self.assertEqual(slugify("Gorges du Verdon !"), "gorges-du-verdon")


if __name__ == "__main__":
    unittest.main(verbosity=2)
