"""Tests hors ligne du pipeline : scoring, niveaux, règles de collection.

Aucune requête réseau — ces tests valident la logique métier, pas Wikidata.
"""

from __future__ import annotations

import sys
import tempfile
from contextlib import contextmanager
from io import StringIO
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


@contextmanager
def _capture():
    """Capture ce qu'une commande imprime, pour l'inspecter."""
    import contextlib

    buffer = StringIO()
    with contextlib.redirect_stdout(buffer):
        yield buffer
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
             "iles", "jardins", "lacs", "plages", "rochers", "sommets",
             "sources", "volcans"},
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


class TestStarvedThemes(unittest.TestCase):
    """Un thème trop maigre pour faire une collection doit se signaler."""

    def test_a_theme_below_the_minimum_is_named_in_the_log(self):
        from roam_pipeline.collections import build_theme_collections

        # Cinq sources : c'est ce qu'a ramené la vraie collecte, sous le
        # minimum de huit. Sans avertissement, le thème disparaîtrait sans un
        # mot et l'onglet resterait vide dans l'application.
        maigre = [
            make_place(f"Source {i}", theme_id="sources", wikidata_id=f"Q{i}")
            for i in range(5)
        ]
        with self.assertLogs("roam_pipeline.collections", level="WARNING") as logs:
            built = build_theme_collections(maigre, CONFIG)

        self.assertEqual([c.slug for c in built], [])
        self.assertIn("sources 5", "\n".join(logs.output))

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

    def test_a_place_never_collected_says_so_rather_than_nothing(self):
        output = self._run("maison de van gogh", self._catalogue())
        self.assertIn("Aucun lieu", output)
        self.assertIn("places.csv", output)

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
