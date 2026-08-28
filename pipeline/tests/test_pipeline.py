"""Tests hors ligne du pipeline : scoring, niveaux, règles de collection.

Aucune requête réseau — ces tests valident la logique métier, pas Wikidata.
"""

from __future__ import annotations

import json
import re
import sys
import tempfile
from contextlib import contextmanager
from io import StringIO
import unittest
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from roam_pipeline.collections import (
    apply_class_exclusion,
    apply_geographic_scope,
    apply_notoriety_floor,
    build_all,
    dedupe,
    dedupe_across_themes,
    haversine_m,
)
from roam_pipeline.config import CONFIG_DIR, Exclusions, Visitors, load_config
from roam_pipeline.export import (
    _sql_str, write_review_csv, write_review_html, write_seed_sql,
)
from roam_pipeline.geo import departements, normalize_dept_code, region_of, regions
from roam_pipeline.models import Place, display_name, slugify
from roam_pipeline import outlines
from roam_pipeline.fetch import REMEDIES, diagnose_missing, enrich_departements
from roam_pipeline.geocode import AddressClient, CommuneClient, departement_from_insee
from roam_pipeline.cli import _known_qids, _pending_terms, _probe_verdict, census
from roam_pipeline.wikipedia import title_from_url
from roam_pipeline.wikidata import (
    class_ancestry_query, class_census_query, class_members_query,
    class_thresholds_query, probe_query, visitors_query,
)
from roam_pipeline.review import (
    DECISIONS, apply_names, diff_tiers, read_names, read_snapshot, vanished,
    write_names, write_snapshot,
)


@contextmanager
def _capture():
    """Capture ce qu'une commande imprime, pour l'inspecter."""
    import contextlib

    buffer = StringIO()
    with contextlib.redirect_stdout(buffer):
        yield buffer
from roam_pipeline.score import (
    assign_tiers, compute_score, label_bonus, score_all, score_breakdown,
)

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


class TestCommuneEnrichment(unittest.TestCase):
    """La commune est la maille la plus fine de la carte de conquête."""

    class _Address:
        def __init__(self, communes):
            self.communes = communes
            self.calls = 0

        def reverse_communes(self, points):
            self.calls += 1
            return {i: self.communes[i] for i, _, _ in points if i in self.communes}

    class _Commune:
        def __init__(self, answer):
            self.answer = answer
            self.calls = 0

        def locate_commune(self, lat, lon):
            self.calls += 1
            return self.answer

    def _commune(self, code, name, dept):
        from roam_pipeline.geocode import Commune

        return Commune(code=code, name=name, departement=dept)

    def test_the_two_passes_split_the_work(self):
        from roam_pipeline.fetch import enrich_communes

        adresse = make_place("Musée", wikidata_id="Q1")
        isole = make_place("Cascade du Rudlin", wikidata_id="Q2")
        address = self._Address({"Q1": self._commune("27285", "Giverny", "27")})
        commune = self._Commune((self._commune("88106", "Chapelle-devant-Bruyères", "88"), "44"))

        resolved = enrich_communes([adresse, isole], address, commune)

        self.assertEqual(resolved, 2)
        self.assertEqual(adresse.commune_code, "27285")
        self.assertEqual(adresse.commune_name, "Giverny")
        self.assertEqual(isole.commune_code, "88106")
        # Un seul appel unitaire : celui que la passe en masse a raté.
        self.assertEqual(commune.calls, 1)

    def test_the_commune_corrects_the_departement(self):
        from roam_pipeline.fetch import enrich_communes

        # La commune et le département viennent du même appel : elle ne peut
        # pas le contredire, donc elle fait autorité sur un rattachement
        # Wikidata erroné.
        place = make_place("Lieu mal rattaché", wikidata_id="Q1", departement_code="75")
        enrich_communes(
            [place],
            self._Address({"Q1": self._commune("15014", "Aurillac", "15")}),
            self._Commune(None),
        )
        self.assertEqual(place.departement_code, "15")
        self.assertEqual(place.region_code, "84")

    def test_a_place_already_located_costs_no_call(self):
        from roam_pipeline.fetch import enrich_communes

        place = make_place("Connu", commune_code="15014")
        address = self._Address({})
        self.assertEqual(enrich_communes([place], address, self._Commune(None)), 0)
        self.assertEqual(address.calls, 0)

    def test_a_point_at_sea_keeps_its_departement(self):
        from roam_pipeline.fetch import enrich_communes

        # Un phare sur son rocher n'appartient à aucun polygone communal. Il
        # sort de la carte de conquête à l'échelle communale, pas du catalogue.
        phare = make_place("Phare isolé", wikidata_id="Q9", departement_code="29")
        self.assertEqual(
            enrich_communes([phare], self._Address({}), self._Commune(None)), 0
        )
        self.assertIsNone(phare.commune_code)
        self.assertEqual(phare.departement_code, "29")


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


class TestPublicAccessInScore(unittest.TestCase):
    """L'ouverture au public entre dans le classement, et dans le plancher."""

    def test_a_confirmed_open_place_scores_above_its_twin(self):
        from roam_pipeline.score import compute_score

        ouvert = make_place("Musée ouvert", sitelinks=10)
        ouvert.visitable = True
        inconnu = make_place("Musée jumeau", sitelinks=10)
        self.assertGreater(compute_score(ouvert, CONFIG), compute_score(inconnu, CONFIG))

    def test_an_unknown_access_costs_nothing(self):
        from roam_pipeline.score import score_breakdown

        # 62 % des lieux rapprochés n'ont aucune balise d'horaires. Les
        # pénaliser reviendrait à noter le zèle des contributeurs
        # d'OpenStreetMap, pas l'intérêt des lieux.
        inconnu = make_place("Sans balise", sitelinks=10)
        self.assertIsNone(inconnu.visitable)
        self.assertEqual(score_breakdown(inconnu, CONFIG)["acces"], 0.0)

    def test_an_explicit_refusal_costs_points(self):
        from roam_pipeline.score import score_breakdown

        ferme = make_place("Domaine privé", sitelinks=10)
        ferme.visitable = False
        self.assertLess(score_breakdown(ferme, CONFIG)["acces"], 0)

    def test_the_rescue_needs_a_confirmed_welcome(self):
        from roam_pipeline.score import rescued

        seuil = CONFIG.scoring.rescue_score

        # Attesté ouvert ET bien classé : repêché.
        ouvert = make_place("Musée de Giverny", sitelinks=5)
        ouvert.visitable, ouvert.score = True, seuil + 1
        self.assertTrue(rescued(ouvert, CONFIG))

        # Très bien classé mais accès inconnu : NON. Un plancher qui mesure la
        # documentation ne se franchit pas avec plus de documentation — c'est
        # l'erreur qui avait repêché 2 757 lieux d'un coup.
        documente = make_place("Château quelconque", sitelinks=5)
        documente.score = seuil + 100
        self.assertIsNone(documente.visitable)
        self.assertFalse(rescued(documente, CONFIG))

        # Ouvert mais mal classé : non plus, sinon toute billetterie entrerait.
        modeste = make_place("Petite ferme-musée", sitelinks=1)
        modeste.visitable, modeste.score = True, seuil - 1
        self.assertFalse(rescued(modeste, CONFIG))


class TestThemeKind(unittest.TestCase):
    """Roam promet des paysages autant que du patrimoine."""

    def test_every_theme_declares_its_kind(self):
        for theme in CONFIG.themes:
            self.assertIn(theme.kind, ("nature", "culture"), theme.id)

    def test_both_kinds_are_represented(self):
        kinds = {theme.kind for theme in CONFIG.themes}
        self.assertEqual(kinds, {"nature", "culture"})

    def test_the_natural_themes_are_the_expected_ones(self):
        # Nommés un par un : une réaffectation silencieuse fausserait le
        # décompte que `build` affiche, et donc le jugement porté dessus.
        nature = {theme.id for theme in CONFIG.themes if theme.kind == "nature"}
        self.assertEqual(
            nature,
            # Les jardins comptent en nature : dessinés de main d'homme, mais
            # on y va pour le paysage.
            {"cascades", "cirques", "dunes-marais", "forets", "gorges", "grottes",
             "iles", "jardins", "lacs", "plages", "rochers", "sommets", "volcans"},
        )

    def test_an_unknown_kind_is_refused(self):
        from roam_pipeline.config import Theme, _validate

        bancal = Theme(
            id="x", name="X", name_singular="X", icon="x", radius_m=100,
            min_sitelinks=1, fetch_min_sitelinks=1, cap=10,
            wikidata_classes=["Q1"], kind="paysage",
        )
        with self.assertRaises(ValueError):
            _validate([bancal], [])


class TestThemeOrder(unittest.TestCase):
    """Le plus spécifique avant le plus générique, sans exception."""

    # Couples dont la sous-classe est certaine : chaque membre de gauche EST
    # aussi un membre de droite dans Wikidata, donc le thème de gauche doit
    # être déclaré en premier, sinon celui de droite lui prend ses lieux.
    #
    # Chaque ligne vient d'une régression réelle, pas d'une précaution :
    # `maisons` après `musees` a coûté neuf lieux sur trente au thème créé
    # pour Giverny, et `dunes-marais` après `plages` quinze sur dix-sept.
    PLUS_SPECIFIQUE = [
        ("maisons", "musees"),        # une maison-musée est un musée
        ("dunes-marais", "plages"),   # une dune est une formation littorale
        ("volcans", "sommets"),       # un puy est un sommet
        ("cirques", "gorges"),        # un cirque est une vallée encaissée
    ]

    def test_the_more_specific_theme_is_declared_first(self):
        rang = {theme.id: index for index, theme in enumerate(CONFIG.themes)}
        for specifique, generique in self.PLUS_SPECIFIQUE:
            self.assertIn(specifique, rang)
            self.assertIn(generique, rang)
            self.assertLess(
                rang[specifique],
                rang[generique],
                f"« {specifique} » doit être déclaré avant « {generique} » : "
                f"sinon {generique} lui prend ses lieux au dédoublonnage croisé",
            )


class TestNatureFloors(unittest.TestCase):
    """Un paysage n'est pas documenté comme un monument."""

    def test_no_natural_theme_is_as_demanding_as_the_strictest_built_one(self):
        # Le plancher compte les versions linguistiques, c'est-à-dire la
        # DOCUMENTATION. Wikidata documente bien moins la nature que le bâti :
        # donner à une montagne le seuil d'un musée écartait 458 sommets sur
        # 497, plus que le filtre alpin lui-même. C'est la même erreur que le
        # score a corrigée avec `article_weight`, restée dans les planchers.
        plafond_culture = max(
            theme.min_sitelinks for theme in CONFIG.themes if theme.kind == "culture"
        )
        for theme in CONFIG.themes:
            if theme.kind != "nature":
                continue
            self.assertLess(
                theme.min_sitelinks,
                plafond_culture,
                f"le thème naturel {theme.id} est aussi exigeant que le bâti le plus strict",
            )


class TestBuildFunnel(unittest.TestCase):
    """Suivre les mêmes lieux d'un bout à l'autre, sans soustraire des lignes."""

    def _catalogue(self):
        places = []
        for i in range(12):
            place = make_place(f"Château {i}", theme_id="chateaux", wikidata_id=f"QC{i}",
                               sitelinks=20, lat=45 + i / 50, lon=2.0)
            place.departement_code, place.region_code = "15", "84"
            places.append(place)
        for i in range(6):
            # Les deux derniers sont hors périmètre, les deux suivants sous le
            # plancher : trois étapes différentes, sur le même thème.
            place = make_place(f"Dune {i}", theme_id="dunes-marais", wikidata_id=f"QD{i}",
                               sitelinks=10 if i < 2 else 1, lat=44 + i / 50, lon=-1.2)
            place.departement_code = "33" if i < 4 else None
            place.region_code = "75"
            places.append(place)
        return places

    def test_the_funnel_follows_a_theme_through_every_stage(self):
        from roam_pipeline.collections import build_all

        with self.assertLogs("roam_pipeline.collections", level="INFO") as logs:
            build_all(self._catalogue(), CONFIG)
        table = "\n".join(logs.output)

        self.assertIn("étape par étape", table)
        # Six dunes au départ, quatre après le périmètre, deux après le plancher.
        ligne = next(l for l in table.splitlines() if l.strip().startswith("dunes-marais"))
        self.assertEqual([int(n) for n in ligne.split()[1:]], [6, 4, 4, 4, 4, 4, 2, 2])

    def test_a_theme_without_any_place_is_left_out_of_the_funnel(self):
        from roam_pipeline.collections import build_all

        # Vingt lignes à zéro noieraient les deux qui parlent. L'assertion ne
        # porte que sur le tableau : l'avertissement des thèmes sans
        # collection, lui, DOIT nommer les thèmes vides — c'est ainsi que le
        # thème `maisons`, vide depuis sa création, a fini par se signaler.
        with self.assertLogs("roam_pipeline.collections", level="INFO") as logs:
            build_all(self._catalogue(), CONFIG)
        tableau = next(entry for entry in logs.output if "étape par étape" in entry)
        self.assertNotIn("cathedrales", tableau)
        self.assertIn("chateaux", tableau)


class TestStarvedThemes(unittest.TestCase):
    """Un thème trop maigre pour faire une collection doit se signaler."""

    def test_a_theme_below_the_minimum_is_named_in_the_log(self):
        from roam_pipeline.collections import build_theme_collections

        # Cinq lieux, sous le minimum de huit. Sans avertissement, le thème
        # disparaîtrait sans un mot et l'onglet resterait vide dans
        # l'application — c'est ce qui est arrivé au thème `sources`, dont la
        # vraie collecte n'a ramené que cinq candidats, et à `maisons`, jamais
        # collecté et vide depuis sa création sans que rien ne le dise.
        maigre = [
            make_place(f"Curiosité {i}", theme_id="rochers", wikidata_id=f"Q{i}")
            for i in range(5)
        ]
        with self.assertLogs("roam_pipeline.collections", level="WARNING") as logs:
            built = build_theme_collections(maigre, CONFIG)

        self.assertEqual([c.slug for c in built], [])
        self.assertIn("rochers 5", "\n".join(logs.output))

    def test_a_theme_with_enough_places_builds_quietly(self):
        from roam_pipeline.collections import build_theme_collections

        assez = [
            make_place(f"Volcan {i}", theme_id="volcans", wikidata_id=f"QV{i}")
            for i in range(CONFIG.collections.min_places)
        ]
        built = build_theme_collections(assez, CONFIG)
        self.assertIn("theme-volcans", [c.slug for c in built])


class TestAccessAndRescue(unittest.TestCase):
    """Deux règles nées de deux lieux précis."""

    def test_a_place_with_refused_access_leaves_the_catalogue(self):
        from roam_pipeline.collections import apply_access_filter

        # Le château d'Hérouville a une histoire passionnante et ne se visite
        # pas. L'application se joue sur place : il n'est pas collectionnable.
        ferme = make_place("Château d'Hérouville", sitelinks=10)
        ferme.visitable = False
        ouvert = make_place("Château voisin", sitelinks=10)
        kept = apply_access_filter([ferme, ouvert], CONFIG)
        self.assertEqual([p.name for p in kept], ["Château voisin"])

    def test_the_curator_can_keep_a_place_with_refused_access(self):
        from roam_pipeline.collections import apply_access_filter

        force = make_place("Château vu de la route", sitelinks=10)
        force.visitable, force.pinned = False, True
        self.assertEqual(len(apply_access_filter([force], CONFIG)), 1)

    def test_an_unknown_access_is_never_excluded(self):
        from roam_pipeline.collections import apply_access_filter

        # Les deux tiers du catalogue sont dans ce cas : les exclure viderait tout.
        inconnu = make_place("Sans balise", sitelinks=10)
        self.assertIsNone(inconnu.visitable)
        self.assertEqual(len(apply_access_filter([inconnu], CONFIG)), 1)

    def test_a_website_alone_does_not_reopen_a_refused_place(self):
        from roam_pipeline.collections import apply_access_filter

        # Régression : le château d'Hérouville a un site web descriptif —
        # patrimonial, pas billetterie — sans être ouvert au public. La
        # première version du filtre le laissait passer sur ce seul site web,
        # exactement le lieu qui avait motivé le filtre.
        herouville = make_place("Château d'Hérouville", sitelinks=10)
        herouville.visitable, herouville.website = False, "https://exemple.fr"
        self.assertEqual(apply_access_filter([herouville], CONFIG), [])

    def test_opening_hours_alone_do_reopen_a_refused_place(self):
        from roam_pipeline.collections import apply_access_filter

        # Contraste avec Hérouville : la grotte des Planches affiche des
        # horaires malgré `access=no` — la visite est guidée, pas fermée.
        grotte = make_place("Grotte des Planches", sitelinks=10)
        grotte.visitable, grotte.opening_hours = False, "Mo-Su 10:00-18:00"
        self.assertEqual(len(apply_access_filter([grotte], CONFIG)), 1)

    def test_giverny_is_rescued_from_the_floor(self):
        from roam_pipeline.collections import apply_notoriety_floor

        # Le musée des impressionnismes de Giverny : 5 langues seulement, mais
        # un long article français, une photo, et des horaires attestés.
        floor = CONFIG.theme("musees").min_sitelinks
        giverny = make_place("Musée des impressionnismes", theme_id="musees", sitelinks=5)
        giverny.visitable = True
        giverny.score = CONFIG.scoring.rescue_score + 1
        self.assertLess(giverny.sitelinks, floor)
        self.assertEqual(len(apply_notoriety_floor([giverny], CONFIG)), 1)

    def test_a_well_documented_place_alone_is_not_rescued(self):
        from roam_pipeline.collections import apply_notoriety_floor

        # Sans signe d'accueil du public, un bon score ne rachète rien.
        obscur = make_place("Château quelconque", theme_id="musees", sitelinks=5)
        obscur.score = CONFIG.scoring.rescue_score + 100
        self.assertEqual(apply_notoriety_floor([obscur], CONFIG), [])


class TestAlpineFilter(unittest.TestCase):
    """Un sommet sans preuve d'accès est écarté, faute de mieux."""

    def test_a_high_summit_without_any_signal_is_dropped(self):
        from roam_pipeline.collections import apply_alpine_filter

        sommet = make_place("Pointe sans nom", theme_id="sommets",
                            elevation_m=CONFIG.alerts.alpine_elevation_m + 200)
        self.assertEqual(apply_alpine_filter([sommet], CONFIG), [])

    def test_a_summit_below_the_threshold_is_kept(self):
        from roam_pipeline.collections import apply_alpine_filter

        colline = make_place("Colline accessible", theme_id="sommets",
                             elevation_m=CONFIG.alerts.alpine_elevation_m - 500)
        self.assertEqual(len(apply_alpine_filter([colline], CONFIG)), 1)

    def test_a_summit_without_elevation_data_is_kept(self):
        from roam_pipeline.collections import apply_alpine_filter

        # Pas de preuve du contraire non plus : l'absence de donnée n'est pas
        # un signal, contrairement à l'altitude elle-même.
        inconnu = make_place("Sommet sans altitude connue", theme_id="sommets")
        self.assertEqual(len(apply_alpine_filter([inconnu], CONFIG)), 1)

    def test_a_pinned_summit_survives_its_altitude(self):
        from roam_pipeline.collections import apply_alpine_filter

        # L'Aiguille du Midi : alpine par nature, mais un téléphérique y monte.
        # Le pipeline ne peut pas le savoir ; le curateur, si.
        aiguille = make_place("Aiguille du Midi", theme_id="sommets",
                              elevation_m=3842, pinned=True)
        self.assertEqual(len(apply_alpine_filter([aiguille], CONFIG)), 1)

    def test_the_threshold_only_applies_to_the_summits_theme(self):
        from roam_pipeline.collections import apply_alpine_filter

        # Un col ou un belvédère à haute altitude n'a pas le même problème
        # d'accès qu'un sommet : le filtre ne doit viser que « sommets ».
        col = make_place("Col perché", theme_id="monuments",
                         elevation_m=CONFIG.alerts.alpine_elevation_m + 500)
        self.assertEqual(len(apply_alpine_filter([col], CONFIG)), 1)


class TestFloorReliefIsVisible(unittest.TestCase):
    """Un lieu conservé par la remise doit se relire à part."""

    def test_a_place_under_its_floor_is_flagged(self):
        from roam_pipeline.export import under_floor

        # Le plancher des musées est éditorial : un musée sous ce seuil n'est
        # là que grâce à son accueil du public attesté.
        floor = CONFIG.theme("musees").min_sitelinks
        rescape = make_place("Musée ouvert", theme_id="musees", sitelinks=floor - 1)
        ordinaire = make_place("Musée connu", theme_id="musees", sitelinks=floor)
        self.assertTrue(under_floor(rescape, CONFIG))
        self.assertFalse(under_floor(ordinaire, CONFIG))


class TestExplain(unittest.TestCase):
    """« Pourquoi ce lieu n'est-il pas là ? » doit avoir une réponse."""

    def _run(self, name, places, decisions=""):
        import argparse
        import json
        import logging
        from roam_pipeline.cli import cmd_explain

        with tempfile.TemporaryDirectory() as tmp:
            out, manual = Path(tmp) / "out", Path(tmp) / "manual"
            out.mkdir()
            manual.mkdir()
            (out / "places_raw.json").write_text(
                json.dumps([p.to_dict() for p in places], ensure_ascii=False), encoding="utf-8"
            )
            if decisions:
                (manual / "decisions.csv").write_text(
                    "wikidata_id,decision,name,note\n" + decisions, encoding="utf-8"
                )
            args = argparse.Namespace(out=out, manual=manual, name=name, limit=5,
                                      adjust=60.0, strict=False)
            logging.disable(logging.CRITICAL)
            try:
                with _capture() as printed:
                    cmd_explain(args, CONFIG)
            finally:
                logging.disable(logging.NOTSET)
        return printed.getvalue()

    def _catalogue(self):
        places = []
        for index in range(12):
            place = make_place(f"Château {index}", wikidata_id=f"Q{index}",
                               theme_id="chateaux", sitelinks=20, lat=45 + index / 40, lon=2.0)
            place.departement_code, place.region_code, place.image_url = "27", "28", "x"
            place.has_frwiki = True
            places.append(place)
        return places

    def test_a_place_below_its_floor_says_so(self):
        floor = CONFIG.theme("chateaux").min_sitelinks
        obscur = make_place("Château d'Hérouville", wikidata_id="Q80", theme_id="chateaux",
                            sitelinks=floor - 2, lat=49.0, lon=2.1)
        obscur.departement_code, obscur.region_code = "95", "11"
        output = self._run("herouville", self._catalogue() + [obscur])
        self.assertIn("plancher de notoriété", output)
        self.assertIn("ÉCARTÉ", output)

    def test_a_place_never_collected_hands_over_to_probe(self):
        # `explain` ne connaît que le collecté : il ne peut pas dire POURQUOI un
        # lieu n'est jamais entré. Lui faire proposer un remède serait deviner ;
        # il doit passer le relais à l'outil qui, lui, va le mesurer.
        output = self._run("maison de van gogh", self._catalogue())
        self.assertIn("Aucun lieu", output)
        self.assertIn("probe", output)
        self.assertIn("maison de van gogh", output)

    def test_a_retained_place_lists_its_collections(self):
        giverny = make_place("Jardins de Giverny", wikidata_id="Q81", theme_id="jardins",
                             sitelinks=22, lat=49.07, lon=1.53)
        giverny.departement_code, giverny.region_code, giverny.image_url = "27", "28", "x"
        giverny.has_frwiki, giverny.visitable = True, True
        # Il faut assez de voisins pour qu'une collection existe (min_places).
        voisins = [
            make_place(f"Jardin {i}", wikidata_id=f"QJ{i}", theme_id="jardins",
                       sitelinks=15, lat=49.0 + i / 40, lon=1.5)
            for i in range(10)
        ]
        for place in voisins:
            place.departement_code, place.region_code = "27", "28"
        output = self._run("giverny", self._catalogue() + [giverny] + voisins)
        self.assertIn("dans le catalogue", output)
        self.assertIn("ouverture au public : confirmée", output)


class TestDurableDecisions(unittest.TestCase):
    """Les verdicts du curateur survivent aux reconstructions."""

    def _round_trip(self, decisions, names=None):
        from roam_pipeline.review import read_decisions, write_decisions

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "decisions.csv"
            write_decisions(path, decisions, names or {})
            return read_decisions(path)

    def test_decisions_survive_a_write_and_a_read(self):
        original = {"Q1": ("drop", "n'existe plus"), "Q2": ("keep", "")}
        self.assertEqual(self._round_trip(original, {"Q1": "Château disparu"}), original)

    def test_an_invented_decision_is_ignored(self):
        self.assertEqual(self._round_trip({"Q1": ("peut-être", "")}), {})

    def test_a_dropped_place_stays_out_and_a_kept_one_is_pinned(self):
        from roam_pipeline.review import apply_decisions

        ecarte = make_place("Écarté", wikidata_id="Q1")
        garde = make_place("Gardé", wikidata_id="Q2")
        ignore = make_place("Non relu", wikidata_id="Q3")
        kept, counts = apply_decisions(
            [ecarte, garde, ignore],
            {"Q1": ("drop", ""), "Q2": ("keep", "")},
            adjust=60.0,
        )
        self.assertEqual([p.name for p in kept], ["Gardé", "Non relu"])
        # Un lieu validé par un humain ne doit pas disparaître si un plancher bouge.
        self.assertTrue(garde.pinned)
        self.assertFalse(ignore.pinned)
        self.assertEqual(counts["pending"], 1)

    def test_promote_corrects_the_score_without_removing_anything(self):
        from roam_pipeline.review import apply_decisions

        haut = make_place("Remonté", wikidata_id="Q1")
        bas = make_place("Descendu", wikidata_id="Q2")
        kept, _ = apply_decisions(
            [haut, bas], {"Q1": ("promote", ""), "Q2": ("demote", "")}, adjust=60.0
        )
        self.assertEqual(len(kept), 2)
        self.assertEqual(haut.curator_adjustment, 60.0)
        self.assertEqual(bas.curator_adjustment, -60.0)


class TestAdoptedCandidates(unittest.TestCase):
    """Entrée des candidats OpenStreetMap dans le catalogue."""

    class _Client:
        def __init__(self, rows):
            self.rows = rows

        def query(self, _query):
            return self.rows

    def _row(self, qid, name, sitelinks=5):
        return {
            "item": f"http://www.wikidata.org/entity/{qid}",
            "itemLabel": name,
            "coord": "Point(2.0 45.0)",
            "sitelinks": str(sitelinks),
        }

    def test_an_adopted_candidate_is_not_pinned(self):
        from roam_pipeline.fetch import fetch_listed_places

        client = self._Client([self._row("Q1", "Jardins de Giverny")])
        places = fetch_listed_places(
            client, CONFIG, {"Q1": "jardins"}, pinned=False, source="osm"
        )
        self.assertEqual(len(places), 1)
        # Être découvert n'est pas être adoubé : le plancher de notoriété doit
        # s'appliquer comme au reste du catalogue.
        self.assertFalse(places[0].pinned)
        self.assertEqual(places[0].source, "osm")

    def test_a_curator_addition_stays_pinned(self):
        from roam_pipeline.fetch import fetch_listed_places

        client = self._Client([self._row("Q1", "Château d'Auvers-sur-Oise")])
        places = fetch_listed_places(
            client, CONFIG, {"Q1": "chateaux"}, pinned=True, source="wikidata"
        )
        self.assertTrue(places[0].pinned)

    def test_the_notoriety_floor_still_applies_to_an_adopted_candidate(self):
        from roam_pipeline.collections import apply_notoriety_floor

        adopted = make_place("Musée de village", theme_id="musees", sitelinks=0)
        adopted.source = "osm"
        self.assertEqual(apply_notoriety_floor([adopted], CONFIG), [])

    def test_an_unknown_theme_is_reported_rather_than_swallowed(self):
        from roam_pipeline.fetch import read_place_list

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "candidates.csv"
            path.write_text(
                "# commentaire\nwikidata_id,theme_id,note\n"
                "Q1,jardins,Giverny\nQ2,jardin,coquille\nQ3,,sans thème\n",
                encoding="utf-8",
            )
            with self.assertLogs("roam_pipeline.fetch", level="ERROR"):
                wanted = read_place_list(CONFIG, path)
        self.assertEqual(wanted, {"Q1": "jardins"})


class TestOpenStreetMap(unittest.TestCase):
    """Ouverture au public et découverte de lieux manquants."""

    def _site(self, **over):
        from roam_pipeline.overpass import OsmPlace

        base = dict(osm_id="way/1", name="Site", lat=45.0, lon=2.0, tags={"tourism": "museum"})
        base.update(over)
        return OsmPlace(**base)

    def test_managed_needs_a_sign_of_public_access(self):
        # Ni horaires, ni site, ni tarif : rien ne dit que ça accueille du public.
        self.assertFalse(self._site().managed)
        self.assertTrue(self._site(opening_hours="Mo-Su 10:00-18:00").managed)
        self.assertTrue(self._site(fee="yes").managed)

    def test_parsing_uses_the_centre_of_ways(self):
        from roam_pipeline.overpass import parse_elements

        parsed = parse_elements([
            {"type": "way", "id": 7, "center": {"lat": 49.1, "lon": 1.5},
             "tags": {"name": "Giverny", "leisure": "garden", "opening_hours": "Mo-Su"}},
            {"type": "node", "id": 8, "lat": 48.0, "lon": 2.0, "tags": {"historic": "castle"}},
        ])
        # Le second est écarté : sans nom, il n'est pas exploitable.
        self.assertEqual([(p.name, p.lat) for p in parsed], [("Giverny", 49.1)])

    def test_visit_info_matches_by_wikidata_then_by_proximity(self):
        from roam_pipeline.discover import apply_visit_info

        par_id = make_place("Par identifiant", wikidata_id="Q1", lat=10.0, lon=10.0)
        par_distance = make_place("Par proximité", wikidata_id="Q2", lat=45.0, lon=2.0)
        apply_visit_info(
            [par_id, par_distance],
            [
                self._site(wikidata_id="Q1", lat=0.0, lon=0.0, opening_hours="Mo-Su"),
                self._site(osm_id="way/2", lat=45.0005, lon=2.0, fee="yes"),
            ],
        )
        # L'identifiant prime sur la distance : le premier est apparié malgré
        # mille kilomètres d'écart.
        self.assertTrue(par_id.visitable)
        self.assertTrue(par_distance.visitable)

    def test_an_unmatched_place_stays_unknown_not_closed(self):
        from roam_pipeline.discover import apply_visit_info

        isole = make_place("Isolé", lat=0.0, lon=0.0)
        apply_visit_info([isole], [self._site(opening_hours="Mo-Su")])
        self.assertIsNone(isole.visitable)

    def test_names_agree_on_the_same_place(self):
        from roam_pipeline.discover import names_match

        self.assertTrue(names_match("Château de Chambord", "Chambord"))
        self.assertTrue(names_match("Abbaye du Mont-Saint-Michel", "Mont-Saint-Michel"))
        self.assertTrue(names_match("Jardins de Claude Monet", "Fondation Claude Monet"))

    def test_a_differing_place_type_breaks_the_match(self):
        from roam_pipeline.discover import names_match

        # Ils partagent leur partie distinctive et désignent pourtant deux
        # bâtiments différents : c'est la nature du lieu qui tranche.
        self.assertFalse(names_match("Château de la Roche", "Moulin de la Roche"))
        self.assertFalse(names_match("Église Saint-Pierre", "Château Saint-Pierre"))

    def test_unrelated_names_do_not_match(self):
        from roam_pipeline.discover import names_match

        self.assertFalse(names_match("Cascade du Hérisson", "Belvédère des Tufs"))
        self.assertFalse(names_match("", "Chambord"))

    def test_proximity_alone_does_not_match_a_different_place(self):
        from roam_pipeline.discover import apply_visit_info

        # Deux cents mètres séparent le château du moulin voisin : sans le
        # contrôle du nom, le château hériterait des horaires du moulin.
        chateau = make_place("Château de la Roche", lat=45.0, lon=2.0)
        apply_visit_info(
            [chateau],
            [self._site(name="Moulin de la Roche", lat=45.0018, lon=2.0, opening_hours="Mo-Su")],
        )
        self.assertIsNone(chateau.visitable)

    def test_a_very_close_object_matches_whatever_its_name(self):
        from roam_pipeline.discover import apply_visit_info

        # À cinquante mètres, c'est le même site : Wikidata pointe le centre de
        # l'édifice, OpenStreetMap son entrée.
        place = make_place("Château de la Roche", lat=45.0, lon=2.0)
        apply_visit_info(
            [place],
            [self._site(name="Entrée visiteurs", lat=45.00045, lon=2.0, fee="yes")],
        )
        self.assertTrue(place.visitable)

    def test_confident_candidates_need_access_and_documentation(self):
        from roam_pipeline.discover import is_confident

        self.assertTrue(is_confident(self._site(opening_hours="Mo-Su", wikidata_id="Q1")))
        # Un site web seul ne prouve rien : beaucoup de lieux privés en ont un.
        self.assertFalse(is_confident(self._site(website="https://a", wikidata_id="Q1")))
        # Des horaires sans rien à voir ne suffisent pas non plus.
        self.assertFalse(is_confident(self._site(opening_hours="Mo-Su")))

    def test_candidates_exclude_what_the_catalogue_already_has(self):
        from roam_pipeline.discover import find_candidates

        connu = make_place("Connu", wikidata_id="Q1", lat=45.0, lon=2.0)
        found = find_candidates(
            [connu],
            [
                self._site(wikidata_id="Q1", opening_hours="Mo-Su"),
                self._site(osm_id="way/3", lat=45.0002, lon=2.0, opening_hours="Mo-Su"),
                self._site(osm_id="way/4", lat=47.0, lon=3.0, opening_hours="Mo-Su", name="Neuf"),
            ],
        )
        # Le premier est connu par identifiant, le deuxième par proximité.
        self.assertEqual([s.name for s in found], ["Neuf"])

    def test_candidates_ignore_sites_without_a_sign_of_access(self):
        from roam_pipeline.discover import find_candidates

        self.assertEqual(find_candidates([], [self._site(lat=47.0, lon=3.0)]), [])

    def test_best_documented_candidates_come_first(self):
        from roam_pipeline.discover import find_candidates

        maigre = self._site(osm_id="way/5", lat=47.0, lon=3.0, name="Maigre", website="https://a")
        riche = self._site(
            osm_id="way/6", lat=48.0, lon=4.0, name="Riche",
            wikidata_id="Q9", opening_hours="Mo-Su", fee="yes",
        )
        self.assertEqual([s.name for s in find_candidates([], [maigre, riche])], ["Riche", "Maigre"])

    def test_the_overpass_query_is_bounded_by_the_french_border(self):
        from roam_pipeline.overpass import cell_query

        query = cell_query((48.0, 2.0, 50.0, 4.0))
        # L'emprise découpe le travail ; c'est la zone qui dit où est la France.
        self.assertIn('area["ISO3166-1"="FR"]', query)
        for line in query.splitlines():
            if line.strip().startswith("nwr"):
                self.assertIn("(area.fr)", line)

    def test_candidates_outside_france_are_dropped(self):
        from roam_pipeline.discover import keep_in_france

        # Le rectangle de collecte couvre Bâle et Milan autant que Colmar.
        colmar = self._site(osm_id="way/1", name="Musée Unterlinden", lat=48.08, lon=7.36)
        bale = self._site(osm_id="way/2", name="Zoo Basel", lat=47.54, lon=7.57)
        milan = self._site(osm_id="way/3", name="Pinacoteca di Brera", lat=45.47, lon=9.19)

        kept = keep_in_france([colmar, bale, milan], lambda points: {"way/1": "68"})
        self.assertEqual([s.name for s in kept], ["Musée Unterlinden"])
        # Le contrôle rapporte le département : la feuille de revue devient lisible.
        self.assertEqual(colmar.departement, "68")

    def test_only_an_explicit_refusal_is_flagged(self):
        from roam_pipeline.alerts import alerts_for

        ferme = make_place("Domaine privé", image_url="x")
        ferme.visitable = False
        self.assertIn("accès privé ou interdit", alerts_for(ferme, CONFIG))

        # Rapproché mais sans horaires : c'est le cas de 62 % des lieux, et ça
        # n'apprend rien. Le signaler noierait la revue.
        muet = make_place("Sans horaires", image_url="x")
        muet.osm_id = "way/9"
        self.assertEqual(alerts_for(muet, CONFIG), [])

    def test_a_refusal_without_any_welcome_marks_a_place_as_closed(self):
        from roam_pipeline.discover import apply_visit_info

        prive = make_place("Château privé", lat=45.0, lon=2.0)
        apply_visit_info(
            [prive],
            [self._site(name="Château privé", lat=45.0, lon=2.0, access="private")],
        )
        self.assertIs(prive.visitable, False)

    def test_opening_hours_outweigh_a_restricted_access(self):
        from roam_pipeline.discover import apply_visit_info

        # Sur une grotte aménagée, `access=no` dit qu'on n'entre pas SEUL — la
        # visite est guidée, et les horaires en attestent. Prendre le refus
        # d'abord écartait la grotte des Planches et celle de Marsoulas, qui se
        # visitent l'une et l'autre.
        #
        # Le compromis est assumé : un parc privé pourrait afficher des
        # horaires sans ouvrir. Le premier cas s'est produit 108 fois sur un
        # vrai passage, le second reste théorique.
        grotte = make_place("Grotte des Planches", lat=46.9, lon=5.8)
        apply_visit_info(
            [grotte],
            [self._site(name="Grotte des Planches", lat=46.9, lon=5.8,
                        opening_hours="Mo-Su 10:00-18:00", access="no")],
        )
        self.assertIs(grotte.visitable, True)


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

        from roam_pipeline.fetch import read_csv_rows

        path = Path(tempfile.mkdtemp()) / "places.csv"
        path.write_text(
            "# explication\n\nwikidata_id,theme_id,note\nQ42,jardins,Giverny\n",
            encoding="utf-8",
        )
        rows = read_csv_rows(path)
        self.assertEqual(rows, [{"wikidata_id": "Q42", "theme_id": "jardins", "note": "Giverny"}])


class TestNotorietyFloor(unittest.TestCase):
    def test_places_below_their_theme_floor_are_dropped(self):
        floor = CONFIG.theme("sommets").min_sitelinks
        places = [
            make_place("obscur", theme="sommets", sitelinks=floor - 1),
            make_place("connu", theme="sommets", sitelinks=floor + 5),
        ]
        kept = apply_notoriety_floor(places, CONFIG)
        self.assertEqual([p.name for p in kept], ["Connu"])

    def test_floor_is_per_theme(self):
        # Une cascade à 3 langues reste ; un sommet à 3 langues part.
        places = [
            make_place("cascade", theme="cascades", sitelinks=3),
            make_place("sommet", theme="sommets", sitelinks=3),
        ]
        self.assertEqual([p.name for p in apply_notoriety_floor(places, CONFIG)], ["Cascade"])

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


class TestOutlines(unittest.TestCase):
    """Contours administratifs : ils doivent maigrir sans se décoller.

    Le repère : deux carrés voisins qui partagent une arête, plus un troisième
    territoire à l'écart. La frontière commune porte un sommet inutile qui doit
    disparaître — mais des DEUX côtés à la fois.
    """

    @staticmethod
    def _square(code, x0, x1, extra=()):
        ring = [[x0, 0.0], *[list(point) for point in extra], [x1, 0.0], [x1, 1.0], [x0, 1.0], [x0, 0.0]]
        return {
            "type": "Feature",
            "properties": {"code": code, "nom": f"Zone {code}"},
            "geometry": {"type": "Polygon", "coordinates": [ring]},
        }

    @staticmethod
    def _rings(feature):
        geometry = feature["geometry"]
        polygons = (
            [geometry["coordinates"]]
            if geometry["type"] == "Polygon"
            else geometry["coordinates"]
        )
        return [ring for polygon in polygons for ring in polygon]

    def _shared_frontier(self, features, x):
        """Les sommets de chaque territoire posés sur la verticale `x`."""
        out = []
        for feature in features:
            points = {
                tuple(point)
                for ring in self._rings(feature)
                for point in ring
                if abs(point[0] - x) < 1e-9
            }
            out.append(points)
        return out

    def test_simplify_keeps_both_ends(self):
        arc = [(0, 0), (10, 1), (20, 0)]
        kept = outlines.simplify(arc, tolerance_km2=1e9)
        self.assertEqual(kept, [(0, 0), (20, 0)])

    def test_simplify_drops_a_pointless_vertex(self):
        # Un sommet aligné avec ses voisins ne dit rien : son triangle est nul.
        arc = [(0, 0), (100, 0), (200, 0), (200, 100)]
        kept = outlines.simplify(arc, tolerance_km2=0.001)
        self.assertNotIn((100, 0), kept)
        self.assertEqual(kept[0], (0, 0))
        self.assertEqual(kept[-1], (200, 100))

    def test_simplify_keeps_a_vertex_above_the_threshold(self):
        # Cent pas de grille en latitude valent une dizaine de kilomètres :
        # le triangle dépasse largement le seuil.
        arc = [(0, 0), (500, 500), (1000, 0)]
        kept = outlines.simplify(arc, tolerance_km2=1.0)
        self.assertEqual(len(kept), 3)

    def test_cut_splits_a_ring_at_its_bounds(self):
        ring = [(0, 0), (1, 0), (2, 0), (2, 2), (0, 2), (0, 0)]
        arcs = outlines.cut(ring, {(0, 0), (2, 0)})
        self.assertEqual(len(arcs), 2)
        # Les arcs se chaînent : la fin de l'un est le début du suivant.
        self.assertEqual(arcs[0][-1], arcs[1][0])
        self.assertEqual(arcs[-1][-1], arcs[0][0])

    def test_cut_leaves_an_island_whole(self):
        ring = [(0, 0), (1, 0), (1, 1), (0, 0)]
        self.assertEqual(outlines.cut(ring, set()), [tuple(ring)])

    def test_a_shared_frontier_stays_identical_on_both_sides(self):
        # LE test de la carte de conquête : un liseré de fond entre deux
        # départements coloriés se voit à l'œil nu, et vient de là.
        milieu = [[1.0, 0.4], [1.0, 0.5], [1.0, 0.6]]
        gauche = self._square("A", 0.0, 1.0)
        gauche["geometry"]["coordinates"] = [
            [[0.0, 0.0], [1.0, 0.0], *milieu, [1.0, 1.0], [0.0, 1.0], [0.0, 0.0]]
        ]
        droite = self._square("B", 1.0, 2.0)
        droite["geometry"]["coordinates"] = [
            [[1.0, 0.0], [2.0, 0.0], [2.0, 1.0], [1.0, 1.0], *milieu[::-1], [1.0, 0.0]]
        ]

        built = outlines.build_outlines([gauche, droite], tolerance_km2=5.0)
        self.assertEqual(len(built), 2)
        cote_a, cote_b = self._shared_frontier(built, 1.0)
        self.assertEqual(cote_a, cote_b)

    def test_the_frontier_actually_gets_simplified(self):
        # Sans ce garde-fou, un contour qui ne maigrit jamais passerait aussi
        # le test précédent.
        milieu = [[1.0, 0.4], [1.0, 0.5], [1.0, 0.6]]
        gauche = self._square("A", 0.0, 1.0)
        gauche["geometry"]["coordinates"] = [
            [[0.0, 0.0], [1.0, 0.0], *milieu, [1.0, 1.0], [0.0, 1.0], [0.0, 0.0]]
        ]
        built = outlines.build_outlines([gauche], tolerance_km2=5.0)
        self.assertLess(len(self._rings(built[0])[0]), 8)

    def test_an_islet_disappears_but_never_the_territory(self):
        petit = {
            "type": "Feature",
            "properties": {"code": "C", "nom": "Îlot"},
            "geometry": {
                "type": "MultiPolygon",
                "coordinates": [
                    [[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0], [0.0, 0.0]]],
                    [[[5.0, 5.0], [5.002, 5.0], [5.002, 5.002], [5.0, 5.002], [5.0, 5.0]]],
                ],
            },
        }
        built = outlines.build_outlines([petit], tolerance_km2=0.01, min_polygon_km2=1.0)
        self.assertEqual(built[0]["geometry"]["type"], "Polygon")

        # Seul au monde, le même îlot survit : un territoire ne s'efface pas.
        seul = {
            "type": "Feature",
            "properties": {"code": "D", "nom": "Rocher"},
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [[5.0, 5.0], [5.002, 5.0], [5.002, 5.002], [5.0, 5.002], [5.0, 5.0]]
                ],
            },
        }
        self.assertEqual(len(outlines.build_outlines([seul], 0.01, min_polygon_km2=1.0)), 1)

    def test_the_code_travels_as_an_identifier(self):
        # MapLibre colore par `feature-state`, qui a besoin d'un identifiant.
        built = outlines.build_outlines([self._square("2A", 0.0, 1.0)], tolerance_km2=0.01)
        self.assertEqual(built[0]["id"], "2A")
        self.assertEqual(built[0]["properties"]["code"], "2A")


class TestShippedOutlines(unittest.TestCase):
    """Le fichier embarqué dans l'application, tel quel."""

    PATH = Path(__file__).resolve().parents[2] / "mobile" / "src" / "data" / "outlines.json"

    @classmethod
    def setUpClass(cls):
        if not cls.PATH.exists():  # pragma: no cover
            raise unittest.SkipTest("contours non générés")
        import json

        cls.data = json.loads(cls.PATH.read_text(encoding="utf-8"))

    def test_every_area_of_the_catalogue_has_an_outline(self):
        # Un département sans contour est un trou blanc au milieu de la carte.
        for level, expected in (("region", regions()), ("departement", departements())):
            drawn = {f["properties"]["code"] for f in self.data[level]["features"]}
            self.assertEqual(set(expected) - drawn, set(), f"{level} sans contour")

    def test_the_overseas_departments_are_there(self):
        drawn = {f["properties"]["code"] for f in self.data["departement"]["features"]}
        for code in ("971", "972", "973", "974", "976"):
            self.assertIn(code, drawn)

    def test_the_licence_travels_with_the_data(self):
        # Licence ouverte : la mention de source est une obligation, pas un ornement.
        self.assertIn("Etalab", self.data["attribution"])

    def test_the_file_stays_light_enough_to_embed(self):
        self.assertLess(self.PATH.stat().st_size, 900 * 1024)


class TestDisplayName(unittest.TestCase):
    """Les libellés de Wikidata ne sont pas des titres."""

    def test_capitalises_only_the_first_letter(self):
        self.assertEqual(display_name("musée des impressionnismes Giverny"),
                         "Musée des impressionnismes Giverny")
        self.assertEqual(display_name("château d'Hérouville"), "Château d'Hérouville")

    def test_never_touches_the_rest_of_the_name(self):
        # `str.capitalize()` écrirait « Saint-cirq-lapopie » : il n'existe
        # aucune règle mécanique pour recapitaliser un nom propre français.
        self.assertEqual(display_name("Saint-Cirq-Lapopie"), "Saint-Cirq-Lapopie")
        self.assertEqual(display_name("phare de la Vieille"), "Phare de la Vieille")

    def test_normalises_whitespace(self):
        self.assertEqual(display_name("  cascade  du Hérisson "), "Cascade du Hérisson")

    def test_applies_to_every_place_whatever_its_source(self):
        # Posé à la construction du lieu et non au point de collecte : sinon
        # OpenStreetMap et les listes manuelles y échappaient.
        self.assertEqual(make_place("cascade du Hérisson").name, "Cascade du Hérisson")


class TestCuratorNames(unittest.TestCase):
    """Renommer est un geste durable, et distinct d'un verdict d'inclusion."""

    def test_a_chosen_name_survives_and_is_normalised(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "names.csv"
            write_names(path, {"Q1": "musée des impressionnismes"})
            self.assertEqual(read_names(path), {"Q1": "Musée des impressionnismes"})

    def test_it_replaces_the_wikidata_label(self):
        place = make_place("Musée des impressionnismes Giverny")
        place.wikidata_id = "Q3330248"
        changed = apply_names([place], {"Q3330248": "Musée des impressionnismes"})
        self.assertEqual(place.name, "Musée des impressionnismes")
        self.assertEqual(changed, 1)

    def test_an_unknown_place_is_left_alone(self):
        place = make_place("Château de Chambord")
        self.assertEqual(apply_names([place], {"Q999": "Autre"}), 0)
        self.assertEqual(place.name, "Château de Chambord")

    def test_renaming_is_not_a_verdict(self):
        # Les deux fichiers sont séparés exprès : un lieu peut être renommé ET
        # gardé, renommé ET écarté. Mélangés, `decision` deviendrait ambigu.
        self.assertNotIn("rename", DECISIONS)


class TestClassExclusion(unittest.TestCase):
    """Un parc d'attractions entré par la porte des musées."""

    @staticmethod
    def _config(qids):
        return replace(CONFIG, exclusions=Exclusions(qids=list(qids)))

    def test_a_disqualified_place_leaves_the_catalogue(self):
        marineland = make_place("Marineland", theme="musees", sitelinks=30)
        marineland.excluded_class = "parc à thème"
        musee = make_place("Musée du Louvre", theme="musees", sitelinks=80)

        kept = apply_class_exclusion([marineland, musee], self._config(["Q1"]))
        self.assertEqual([p.name for p in kept], ["Musée du Louvre"])

    def test_an_empty_list_changes_nothing(self):
        marineland = make_place("Marineland", theme="musees")
        marineland.excluded_class = "parc à thème"
        # Sans classe déclarée, la marque d'un `enrich` précédent ne doit pas
        # continuer d'agir : retirer une classe de la liste rend ses lieux.
        kept = apply_class_exclusion([marineland], self._config([]))
        self.assertEqual(len(kept), 1)

    def test_a_pinned_place_escapes_it(self):
        # L'exclusion par classe est brute : le curateur garde le dernier mot.
        zoo = make_place("Jardin des plantes", theme="jardins")
        zoo.excluded_class = "parc zoologique"
        zoo.pinned = True
        self.assertEqual(len(apply_class_exclusion([zoo], self._config(["Q1"]))), 1)

    def test_it_names_what_it_removes(self):
        # Une exclusion silencieuse serait indétectable : le Jardin des plantes
        # abrite une ménagerie, et personne ne s'apercevrait de sa disparition.
        marineland = make_place("Marineland", theme="musees")
        marineland.excluded_class = "parc à thème"
        with self.assertLogs("roam_pipeline.collections", level="INFO") as logs:
            apply_class_exclusion([marineland], self._config(["Q1"]))
        journal = "\n".join(logs.output)
        self.assertIn("Marineland", journal)
        self.assertIn("parc à thème", journal)

    def test_the_query_binds_both_sides(self):
        # Bornée par `VALUES` des deux côtés : c'est ce qui la rend tenable là
        # où le même chemin transitif posé dans `theme_query` expirait.
        sparql = class_ancestry_query(["Q10", "Q11"], ["Q20"])
        self.assertIn("VALUES ?item { wd:Q10 wd:Q11 }", sparql)
        self.assertIn("VALUES ?class { wd:Q20 }", sparql)
        self.assertIn("wdt:P31/wdt:P279* ?class", sparql)

    def test_a_class_cannot_be_collected_and_refused_at_once(self):
        # Sinon le thème se viderait sans qu'aucun message ne le dise.
        collected = CONFIG.themes[1].wikidata_classes[0]
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            for name in ("themes.yaml", "labels.yaml", "scoring.yaml"):
                (base / name).write_text(
                    (CONFIG_DIR / name).read_text(encoding="utf-8"), encoding="utf-8"
                )
            themes = (base / "themes.yaml").read_text(encoding="utf-8")
            # La liste réelle est commentée ligne à ligne : on remplace sa
            # forme, pas son texte, pour que le test survive à son contenu.
            patched, count = re.subn(
                r"^exclude_classes:.*?\n  search:",
                f"exclude_classes:\n  qids: [{collected}]\n  search:",
                themes,
                flags=re.MULTILINE | re.DOTALL,
            )
            assert count == 1, "bloc `exclude_classes` introuvable"
            (base / "themes.yaml").write_text(patched, encoding="utf-8")
            with self.assertRaises(ValueError) as raised:
                load_config(base)
        self.assertIn("exclude_classes", str(raised.exception))


class TestProbe(unittest.TestCase):
    """Pourquoi un lieu emblématique n'a-t-il jamais été collecté ?

    C'est le défaut le plus grave possible et le plus discret : une clause non
    remplie de `theme_query` ne lève rien, elle retire l'entité du résultat.
    Rien, nulle part, ne dit qu'un lieu manque.
    """

    @staticmethod
    def _entry(**over):
        base = {
            "label": "Fondation Claude Monet",
            "description": "maison et jardins",
            "country": "France",
            "country_qid": "Q142",
            "coord": "Point(1.53 49.07)",
            "sitelinks": 12,
            "frwiki": "https://fr.wikipedia.org/wiki/x",
            "admin": "Giverny",
            "classes": {},
        }
        base.update(over)
        return base

    #: Une route de collecte : (thème, libellé de la classe, plancher de CETTE classe).
    MAISONS = [("maisons", "maison-musée", 2)]
    GENERIQUE = [("maisons", "maison", 8)]

    def test_a_missing_country_is_named_first(self):
        # `theme_query` exige P17 = France. Sans elle, aucun thème ne peut voir
        # l'entité — et c'est invisible depuis le catalogue.
        lines = _probe_verdict(self._entry(country="", country_qid=""), self.MAISONS, CONFIG, False)
        self.assertIn("pays", lines[0])
        self.assertTrue(any("manual/places.csv" in line for line in lines))

    def test_a_foreign_country_blocks_too(self):
        lines = _probe_verdict(
            self._entry(country="Belgique", country_qid="Q31"),
            [("chateaux", "château", 3)], CONFIG, False,
        )
        self.assertIn("pays", lines[0])

    def test_missing_coordinates_are_named(self):
        lines = _probe_verdict(self._entry(coord=""), self.MAISONS, CONFIG, False)
        self.assertIn("coordonnée", lines[0])

    def test_an_unrecognised_class_is_named(self):
        lines = _probe_verdict(self._entry(), [], CONFIG, False)
        self.assertIn("classe", lines[0])

    def test_the_collection_floor_is_named_with_its_value(self):
        # Le plancher de COLLECTE, pas l'éditorial : le premier écarte avant
        # que le lieu n'existe, le second se règle sans recollecter.
        lines = _probe_verdict(
            self._entry(sitelinks=9), [("musees", "musée", 10)], CONFIG, False
        )
        self.assertIn("COLLECTE", lines[0])
        self.assertIn("10", lines[0])

    def test_the_floor_belongs_to_the_class_not_to_the_theme(self):
        # LE bug de la maison du docteur Gachet. Reconnue par `maisons` via la
        # classe générique « maison », qui exige huit langues — mais `probe`
        # comparait au plancher du THÈME (deux) et répondait « rien ne s'y
        # oppose, relance fetch », ce que le fetch démentait sans un mot.
        lines = _probe_verdict(self._entry(sitelinks=4), self.GENERIQUE, CONFIG, False)
        self.assertIn("COLLECTE", lines[0])
        self.assertIn("maison", lines[0])
        self.assertIn("8", lines[0])
        self.assertNotIn("Rien ne s'y oppose", " ".join(lines))

    def test_one_open_route_is_enough(self):
        # Deux classes mènent au même lieu : il suffit que l'une l'admette.
        lines = _probe_verdict(
            self._entry(sitelinks=4), self.MAISONS + self.GENERIQUE, CONFIG, False
        )
        self.assertIn("fetch --only maisons", lines[0])

    def test_nothing_blocking_and_absent_means_refetch(self):
        lines = _probe_verdict(self._entry(), self.MAISONS, CONFIG, False)
        self.assertIn("fetch --only maisons", lines[0])

    def test_already_collected_hands_over_to_explain(self):
        # `probe` répond sur la collecte, `explain` sur la construction : se
        # tromper d'outil fait chercher le défaut au mauvais endroit.
        lines = _probe_verdict(self._entry(), self.MAISONS, CONFIG, True)
        self.assertIn("explain", lines[0])

    def test_the_least_demanding_route_wins_per_class(self):
        from roam_pipeline.cli import _class_owners
        owners = _class_owners(CONFIG)
        # La classe générique porte SON plancher, pas celui du thème.
        self.assertEqual(owners["Q3947"], ("maisons", 8))
        self.assertEqual(owners["Q2087181"], ("maisons", CONFIG.theme("maisons").fetch_min_sitelinks))

    def test_the_query_demands_nothing(self):
        # L'inverse exact de `theme_query` : tout y est optionnel, puisque
        # c'est justement ce qui manque qu'on vient chercher.
        sparql = probe_query(["Q1"])
        for demanded in ("P17", "P625", "sitelinks", "P31"):
            self.assertIn(demanded, sparql)
        self.assertEqual(sparql.count("OPTIONAL"), 6)

    def test_known_qids_reads_both_formats(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "places_raw.json").write_text(
                json.dumps([{"wikidata_id": "Q1"}, {"wikidata_id": "Q2"}]), encoding="utf-8"
            )
            (base / "candidates.csv").write_text(
                "# commentaire\nwikidata_id,name\nQ3,Marineland\n", encoding="utf-8"
            )
            self.assertEqual(_known_qids(base / "places_raw.json"), {"Q1", "Q2"})
            self.assertEqual(_known_qids(base / "candidates.csv"), {"Q3"})
            self.assertEqual(_known_qids(base / "absent.json"), set())


class TestBroadClasses(unittest.TestCase):
    """Une classe générique, admise seulement très haut.

    La fondation Claude-Monet n'est chez Wikidata qu'une « maison ». Collecter
    cette classe au plancher du thème ramènerait toutes les maisons de France ;
    ne pas la collecter laisse dehors la maison de Monet. Le plancher est la
    sortie — et il ne vaut que s'il est vraiment plus haut.
    """

    def test_a_broad_class_is_collected_at_its_own_floor(self):
        maisons = CONFIG.theme("maisons")
        floors = dict(maisons.collected_classes)
        self.assertEqual(floors["Q3947"], 8)
        # Les classes propres du thème gardent le plancher du thème.
        self.assertEqual(floors["Q2087181"], maisons.fetch_min_sitelinks)

    def test_the_fondation_would_now_be_collected(self):
        # Onze langues, d'après `probe` : au-dessus du plancher générique.
        self.assertLessEqual(dict(CONFIG.theme("maisons").collected_classes)["Q3947"], 11)

    def test_a_broad_class_at_the_theme_floor_is_refused(self):
        # Sans écart, le garde-fou serait décoratif et le thème se noierait.
        with self.assertRaises(ValueError) as raised:
            self._load_with(
                "    broad_classes:\n      - qid: Q3947\n        fetch_min_sitelinks: 2"
            )
        self.assertIn("ramènerait tout", str(raised.exception))

    def test_a_broad_class_is_verified_like_any_other(self):
        # Un Q-id générique erroné ne lèverait rien : il rendrait zéro résultat,
        # et la maison de Monet manquerait encore.
        with self.assertRaises(ValueError):
            self._load_with(
                "    broad_classes:\n      - qid: 3947\n        fetch_min_sitelinks: 8"
            )

    @staticmethod
    def _load_with(block: str):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            for name in ("themes.yaml", "labels.yaml", "scoring.yaml"):
                (base / name).write_text(
                    (CONFIG_DIR / name).read_text(encoding="utf-8"), encoding="utf-8"
                )
            themes = (base / "themes.yaml").read_text(encoding="utf-8")
            # Le bloc réel porte un commentaire en fin de ligne : on le
            # remplace par sa forme, pas par son texte exact.
            themes, count = re.subn(
                r"    broad_classes:\n(?:      .*\n|        .*\n)+", block + "\n", themes
            )
            assert count == 1, "bloc `broad_classes` introuvable dans themes.yaml"
            (base / "themes.yaml").write_text(themes, encoding="utf-8")
            return load_config(base)


class TestMissingDiagnosis(unittest.TestCase):
    """« Introuvable sur Wikidata » disait deux choses très différentes.

    `items_query` exige des coordonnées : une entité qui n'en a pas n'y rend
    aucune ligne, comme une entité supprimée. Les deux tombaient sous le même
    message, alors que l'un est un identifiant mort à retirer et l'autre un
    lieu bien réel qu'on perd en silence — le défaut même qui a fait manquer
    Giverny.
    """

    @staticmethod
    def _row(qid, label="", coord=""):
        return {
            "item": f"http://www.wikidata.org/entity/{qid}",
            "itemLabel": label,
            "coord": coord,
        }

    def test_a_deleted_id_is_told_apart_from_a_real_place(self):
        causes = diagnose_missing(
            [self._row("Q1", "Maison de Monet")], {"Q1", "Q2"}
        )
        self.assertEqual(causes["absent"], ["Q2"])
        self.assertEqual(causes["sans coordonnées"], ["Maison de Monet (Q1)"])

    def test_the_name_travels_with_the_diagnosis(self):
        # Un Q-id nu n'aide personne : le geste à faire dépend du lieu que
        # c'est, et on ne va pas le chercher sur Wikidata pour douze lignes.
        causes = diagnose_missing([self._row("Q1", "Château de X")], {"Q1"})
        self.assertIn("Château de X", causes["sans coordonnées"][0])

    def test_an_unlabelled_entity_has_its_own_cause(self):
        causes = diagnose_missing([self._row("Q1", "Q1", "Point(1 2)")], {"Q1"})
        self.assertEqual(causes["sans libellé"], ["Q1"])

    def test_a_complete_entity_that_returned_nothing_is_flagged(self):
        # Ni supprimée, ni sans coordonnées, ni sans nom : quelque chose
        # d'autre cloche, et le taire serait revenir au point de départ.
        causes = diagnose_missing([self._row("Q1", "Truc", "Point(1 2)")], {"Q1"})
        self.assertEqual(causes["inexpliqué"], ["Truc (Q1)"])

    def test_nothing_missing_says_nothing(self):
        self.assertEqual(diagnose_missing([], set()), {})

    def test_every_cause_carries_a_remedy(self):
        for cause in ("absent", "sans coordonnées", "sans libellé", "inexpliqué"):
            self.assertIn(cause, REMEDIES)


class TestVisitorSignal(unittest.TestCase):
    """La fréquentation : le seul signal qui mesure l'affluence.

    Tous les autres postes mesurent ce qu'on ÉCRIT d'un lieu. Le décompte de
    langues classait une villa d'architecte devant la maison de Claude Monet,
    qui reçoit sept cent mille personnes par an.
    """

    @staticmethod
    def _config(**over):
        base = dict(property_id="P1", weight=10.0, scale=10_000)
        base.update(over)
        return replace(CONFIG, visitors=Visitors(**base))

    def test_a_place_without_a_count_loses_nothing(self):
        # La condition que le curateur a posée mot pour mot : exploiter le
        # chiffre quand il existe, sans impacter ceux qui ne l'ont pas.
        place = make_place("Château sans chiffre", sitelinks=10)
        config = self._config()
        self.assertEqual(score_breakdown(place, config)["visiteurs"], 0.0)
        # Et le total est exactement celui d'un catalogue sans le signal.
        muet = replace(CONFIG, visitors=Visitors())
        self.assertEqual(
            score_breakdown(place, config)["total"], score_breakdown(place, muet)["total"]
        )

    def test_the_bonus_grows_with_the_crowd(self):
        config = self._config()
        petit = make_place("Petit musée")
        petit.visitors_per_year = 10_000
        grand = make_place("Grand musée")
        grand.visitors_per_year = 1_000_000
        self.assertLess(
            score_breakdown(petit, config)["visiteurs"],
            score_breakdown(grand, config)["visiteurs"],
        )

    def test_it_never_becomes_a_malus(self):
        # Wikidata ne renseigne la fréquentation que d'une minorité de sites.
        # Un malus noterait le zèle des contributeurs, pas l'intérêt des lieux.
        for count in (None, 0, 1, 10, 10_000_000):
            place = make_place("X")
            place.visitors_per_year = count
            self.assertGreaterEqual(score_breakdown(place, self._config())["visiteurs"], 0.0)

    def test_an_unresolved_property_disables_the_signal(self):
        # Tant que l'identifiant n'est pas résolu, le signal ne doit rien faire
        # plutôt que d'inventer : une propriété fausse ne lève rien.
        place = make_place("Giverny")
        place.visitors_per_year = 700_000
        dormant = replace(CONFIG, visitors=Visitors(search="nombre de visiteurs", weight=10.0))
        self.assertFalse(dormant.visitors.active)
        self.assertEqual(score_breakdown(place, dormant)["visiteurs"], 0.0)

    def test_giverny_overtakes_a_better_documented_house(self):
        # Le cas qui a motivé le signal, en miniature.
        villa = make_place("Villa d'architecte", theme="maisons", sitelinks=30)
        giverny = make_place("Fondation Claude-Monet", theme="maisons", sitelinks=11)
        giverny.visitors_per_year = 700_000
        config = self._config()
        self.assertLess(
            score_breakdown(villa, config)["total"], score_breakdown(giverny, config)["total"]
        )

    def test_the_query_is_bounded(self):
        sparql = visitors_query(["Q1", "Q2"], "P1")
        self.assertIn("VALUES ?item { wd:Q1 wd:Q2 }", sparql)
        self.assertIn("wdt:P1", sparql)

    def test_a_malformed_property_is_refused_at_load(self):
        # Écrite sans son P, elle ne rendrait rien — en silence.
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            for name in ("themes.yaml", "labels.yaml", "scoring.yaml"):
                (base / name).write_text(
                    (CONFIG_DIR / name).read_text(encoding="utf-8"), encoding="utf-8"
                )
            scoring = (base / "scoring.yaml").read_text(encoding="utf-8")
            # On remplace la forme de la ligne, pas sa valeur : le test doit
            # survivre à la résolution de la propriété.
            patched, count = re.subn(
                r"^  property: .*$", "  property: 1174", scoring, flags=re.MULTILINE
            )
            assert count == 1, "ligne `property` introuvable dans scoring.yaml"
            (base / "scoring.yaml").write_text(patched, encoding="utf-8")
            with self.assertRaises(ValueError) as raised:
                load_config(base)
        self.assertIn("propriété", str(raised.exception))

    def test_the_search_term_is_pending_until_resolved(self):
        pending = _pending_terms(CONFIG)
        kinds = {kind for _owner, _term, kind in pending}
        if CONFIG.visitors.search and not CONFIG.visitors.property_id:
            # Cherchée parmi les entités, une propriété ne rend rien.
            self.assertIn("property", kinds)


class TestTierChanges(unittest.TestCase):
    """Un lieu validé peut descendre sans que personne ne l'ait décidé.

    Le niveau n'est pas une propriété du lieu : c'est son rang dans sa
    collection. Ajouter la fréquentation au score, ou seulement collecter dix
    lieux de plus, suffit à faire reculer un incontournable déjà relu — et rien
    ne le disait.
    """

    @staticmethod
    def _catalogue(bonus=0):
        places = [
            make_place(f"Château {i}", sitelinks=40 - i, lat=45 + i * 0.1, lon=2.0,
                       wikidata_id=f"Q{i}")
            for i in range(1, 15)
        ]
        if bonus:
            places[-1].sitelinks = bonus
        return score_all(places, CONFIG)

    def _state(self, places):
        from roam_pipeline.export import review_state
        retained, collections = build_all(places, CONFIG)
        return review_state(retained, collections)

    def test_a_snapshot_survives_a_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tiers.csv"
            write_snapshot(
                path, {"Q1": (1, "chateaux"), "Q2": (3, "musees")}, {"Q1": "Chambord"}
            )
            self.assertEqual(
                read_snapshot(path), {"Q1": (1, "chateaux"), "Q2": (3, "musees")}
            )

    def test_a_place_that_falls_is_named(self):
        with _capture():
            before = self._state(self._catalogue())
            after = self._state(self._catalogue(bonus=99))
        changes = diff_tiers(before, after)
        self.assertIn("descend", changes.values())
        self.assertIn("monte", changes.values())

    def test_the_first_run_signals_nothing(self):
        # Sans photographie précédente, tout serait « nouveau » : deux mille
        # lignes noieraient le signal le jour où il compte vraiment.
        self.assertEqual(diff_tiers({}, {"Q1": (1, "a"), "Q2": (2, "a")}), {})

    def test_a_place_gone_from_the_catalogue_is_counted_apart(self):
        # Il n'est plus là pour être relu : le confondre avec une descente
        # enverrait le curateur chercher une carte qui n'existe plus.
        avant = {"Q1": (1, "a"), "Q9": (2, "a")}
        apres = {"Q1": (1, "a")}
        self.assertEqual(vanished(avant, apres), ["Q9"])
        self.assertNotIn("Q9", diff_tiers(avant, apres))

    def test_an_unchanged_catalogue_reports_nothing(self):
        with _capture():
            state = self._state(self._catalogue())
        self.assertEqual(diff_tiers(state, state), {})

    def test_a_theme_change_outranks_a_tier_change(self):
        # Le Petit Palais validé en « maison d'artiste » puis rendu aux musées :
        # sa décision a été prise dans un autre contexte, et le rang qu'il
        # prend chez les musées ne dit rien de ce qu'il vaut là-bas.
        changes = diff_tiers(
            {"Q1": (1, "maisons")}, {"Q1": (3, "musees")}
        )
        self.assertEqual(changes["Q1"], "theme")

    def test_a_snapshot_without_a_theme_still_reads(self):
        # Les photographies prises avant que le thème n'y figure ne doivent pas
        # faire croire que tout le catalogue a changé de thème.
        self.assertEqual(diff_tiers({"Q1": (1, "")}, {"Q1": (1, "musees")}), {})

    def test_the_review_sheet_carries_the_change(self):
        # Le curateur relit dans la feuille, pas dans le journal.
        with _capture():
            places = self._catalogue()
            _retained, collections = build_all(places, CONFIG)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "review.csv"
            write_review_csv(places, collections, path, CONFIG, {"Q3": "descend"})
            lines = path.read_text(encoding="utf-8").splitlines()
        self.assertIn("changement", lines[0])
        self.assertTrue(any("descend" in line for line in lines[1:]))

    def test_the_review_page_offers_to_filter_on_it(self):
        # Relire ce qui a bougé est une session à part entière.
        with _capture():
            places = self._catalogue()
            _retained, collections = build_all(places, CONFIG)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "review.html"
            write_review_html(places, collections, CONFIG, path, {"Q3": "descend"})
            body = path.read_text(encoding="utf-8")
        self.assertIn('value="bouge"', body)
        self.assertIn("descendu depuis ta dernière revue", body)


class TestGapCensus(unittest.TestCase):
    """Le recensement des portes qu'on n'a pas ouvertes.

    La collecte part des classes qu'on connaît : elle ne peut pas dire ce
    qu'elle ignore. Une liste d'incontournables écrite de mémoire ne le peut
    pas non plus — elle oublie précisément ce qu'on oublie.
    """

    @staticmethod
    def _row(qid, label, class_qid, class_label):
        return {
            "item": f"http://www.wikidata.org/entity/{qid}",
            "itemLabel": label,
            "class": f"http://www.wikidata.org/entity/{class_qid}",
            "classLabel": class_label,
        }

    def test_it_counts_what_the_catalogue_lacks(self):
        rows = [
            self._row("Q1", "Fondation Claude-Monet", "Q3947", "maison"),
            self._row("Q2", "Maison du docteur Gachet", "Q3947", "maison"),
            self._row("Q3", "Château de Chambord", "Q23413", "château fort"),
        ]
        classes = census(rows, {"Q3947": 2, "Q23413": 1}, known={"Q3"}, owned={"Q23413"})
        maison = next(c for c in classes if c["qid"] == "Q3947")
        chateau = next(c for c in classes if c["qid"] == "Q23413")
        self.assertEqual(maison["manquants"], 2)
        self.assertEqual(chateau["manquants"], 0)
        # Le tri met les trous en tête, pas les grosses classes.
        self.assertEqual(classes[0]["qid"], "Q3947")

    def test_it_says_whether_the_class_is_already_collected(self):
        # Deux situations très différentes : une classe absente du radar, et
        # une classe collectée dont les absents sont sous un plancher.
        rows = [self._row("Q1", "X", "Q3947", "maison")]
        self.assertFalse(census(rows, {}, known=set(), owned=set())[0]["collectee"])
        self.assertTrue(census(rows, {}, known=set(), owned={"Q3947"})[0]["collectee"])

    def test_a_place_counted_once_per_class(self):
        # Une entité rend plusieurs lignes quand elle a plusieurs classes ; la
        # compter deux fois gonflerait le trou et ferait courir après un vide.
        rows = [
            self._row("Q1", "X", "Q3947", "maison"),
            self._row("Q1", "X", "Q3947", "maison"),
            self._row("Q1", "X", "Q23413", "château fort"),
        ]
        classes = census(rows, {}, known=set(), owned=set())
        self.assertEqual({c["qid"]: c["manquants"] for c in classes},
                         {"Q3947": 1, "Q23413": 1})

    def test_examples_help_decide(self):
        # Un décompte ne dit pas s'il faut ouvrir la porte ; des noms, si.
        rows = [self._row(f"Q{i}", f"Lieu {i}", "Q3947", "maison") for i in range(9)]
        entry = census(rows, {}, known=set(), owned=set())[0]
        self.assertEqual(len(entry["exemples"]), 5)
        self.assertIn("Lieu 0", entry["exemples"])

    def test_the_count_is_aggregated_by_the_server(self):
        # La version paginée retriait des dizaines de milliers de lignes à
        # chaque page et mourait en 504. L'agrégation se fait chez WDQS.
        sparql = class_census_query(12)
        self.assertIn("COUNT(DISTINCT ?item)", sparql)
        self.assertIn("GROUP BY ?class", sparql)
        self.assertNotIn("OFFSET", sparql)

    def test_members_are_bounded_by_their_classes(self):
        # C'est la classe qui mène la requête, pas l'ensemble des lieux de
        # France : d'où un coût sans rapport.
        sparql = class_members_query(["Q3947", "Q23413"], 12)
        self.assertIn("VALUES ?class { wd:Q3947 wd:Q23413 }", sparql)

    def test_the_threshold_table_counts_every_floor_at_once(self):
        # Baisser un plancher se décide sur un nombre, et ce nombre ne doit pas
        # coûter une demi-heure de collecte.
        sparql = class_thresholds_query("Q3947", [2, 8])
        self.assertIn("SUM(IF(?sitelinks >= 2, 1, 0)) AS ?n2", sparql)
        self.assertIn("SUM(IF(?sitelinks >= 8, 1, 0)) AS ?n8", sparql)


class TestClassesFoundByTheCensus(unittest.TestCase):
    """Les deux trous que `gaps` a nommés, et qu'il ne doit plus rouvrir."""

    def test_minor_basilicas_are_collected(self):
        # « basilique mineure » est un TITRE canonique, pas une forme
        # architecturale : Wikidata ne la range pas sous « basilique », et
        # cinquante édifices y échappaient — dont Notre-Dame de Fourvière.
        self.assertIn("Q120560", CONFIG.theme("cathedrales").wikidata_classes)

    def test_art_museums_are_collected(self):
        # Elle devrait remonter comme sous-classe de « musée ». Dans les faits
        # elle ne le fait pas : 55 absents sur 62, dont le Petit Palais. Une
        # hiérarchie qu'on suppose ne remplace pas une classe qu'on déclare.
        self.assertIn("Q207694", CONFIG.theme("musees").wikidata_classes)

    def test_a_control_character_does_not_kill_a_batch(self):
        # Un libellé Wikidata peut contenir un caractère de contrôle brut. Le
        # décodeur JSON le refuse par défaut, et tout un lot de classes mourait
        # pour un seul caractère.
        import json as _json
        payload = '{"results": {"bindings": [{"x": {"value": "a\x01b"}}]}}'
        with self.assertRaises(_json.JSONDecodeError):
            _json.loads(payload)
        self.assertEqual(_json.loads(payload, strict=False)["results"]["bindings"][0]["x"]["value"],
                         "a\x01b")


if __name__ == "__main__":
    unittest.main(verbosity=2)
