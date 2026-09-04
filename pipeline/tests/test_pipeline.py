"""Tests hors ligne du pipeline : scoring, niveaux, règles de collection.

Aucune requête réseau — ces tests valident la logique métier, pas Wikidata.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import re
import sys
import tempfile
import unicodedata
from contextlib import contextmanager
from io import StringIO
import unittest
import unittest.mock
from collections import Counter, defaultdict
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from roam_pipeline.raw import EXTRA_SHARD, read_raw, shards, write_raw
from roam_pipeline.merge import merge_file, merge_text, split_conflict
from roam_pipeline.wikipedia import WikipediaClient
from roam_pipeline.review import (
    CLEAR, DECISIONS, apply_decisions, apply_themes, name_hints, read_decisions,
    read_themes, theme_claims, theme_from_name, write_decisions, write_themes,
)
from roam_pipeline.collections import (
    _finalize,
    build_cross_collections,
    build_theme_collections,
    diameter_km,
    DUPLICATE_DISTANCE_M,
    fantomes,
    _mix_themes,
    _rank_within_theme,
    twins,
    rescue_thin_departements,
    _spread,
    apply_class_exclusion,
    apply_geographic_scope,
    apply_notoriety_floor,
    build_all,
    dedupe,
    dedupe_across_themes,
    haversine_m,
)
from roam_pipeline.config import CONFIG_DIR, Config, Exclusions, Visitors, load_config
from roam_pipeline.export import (
    review_tiers,
    _sql_str, read_review_csv, read_review_themes, write_review_csv, write_review_html, write_seed_sql,
)
from roam_pipeline.geo import departements, normalize_dept_code, region_of, regions
from roam_pipeline.models import (
    Collection, CollectionPlace, Place, display_name, slugify,
)
from roam_pipeline import outlines
from roam_pipeline import wikidata as wd
from roam_pipeline.fetch import (
    REMEDIES, diagnose_missing, enrich_departements, stale_themes,
)
from roam_pipeline.geocode import AddressClient, CommuneClient, departement_from_insee
from roam_pipeline.cli import (
    _known_qids, _pending_terms, _probe_verdict, census, cmd_pin, cmd_retention,
    cmd_verdict,
    empty_themes,
)
from roam_pipeline.wikipedia import title_from_url
from roam_pipeline.discover import (
    _atteste, guess_theme, is_confident, tag_filters_for,
)
from roam_pipeline.overpass import OsmPlace, cell_query
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


def _sans_lift() -> Config:
    """La configuration, sans le rapport de caractérisation d'un croisement.

    Les fixtures rassemblent un ou deux thèmes dans un seul département : le
    rapport y vaut mécaniquement ×1,0 et écarterait tous les croisements, ce
    qui n'a rien à voir avec ce que ces tests vérifient.
    """
    return replace(CONFIG, collections=replace(CONFIG.collections, min_theme_lift=0.0))


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


class TestCollectionNamesAreDistinguishable(unittest.TestCase):
    """Deux collections ne doivent pas porter le même nom à un pluriel près.

    Le thème s'appelait « Jardins remarquables » et le label « Jardin
    remarquable » — le second est le nom officiel du ministère de la Culture,
    le premier le lui avait emprunté. Dans la liste, deux entrées se suivaient
    sans que rien ne dise laquelle contenait quoi.

    `drop_twin_collections` ne voyait rien : il compare des noms exacts ET des
    listes de lieux identiques. Ici les deux différaient. C'est le NOM seul qui
    est en cause, parce que c'est tout ce que l'utilisateur a pour choisir.
    """

    @staticmethod
    def _pli(nom: str) -> str:
        """Le nom tel qu'on le distingue d'un coup d'œil : sans accents, sans
        casse, sans pluriel."""
        sans_accent = "".join(
            c for c in unicodedata.normalize("NFD", nom.lower())
            if not unicodedata.combining(c)
        )
        mots = re.findall(r"[a-z0-9]+", sans_accent)
        return " ".join(m[:-1] if m.endswith("s") and len(m) > 4 else m for m in mots)

    def test_no_theme_name_collides_with_a_label_name(self):
        par_pli = defaultdict(list)
        for theme in CONFIG.themes:
            par_pli[self._pli(theme.name)].append(f"thème « {theme.name} »")
        for label in CONFIG.labels:
            par_pli[self._pli(label.name)].append(f"label « {label.name} »")

        collisions = {pli: noms for pli, noms in par_pli.items() if len(noms) > 1}
        self.assertEqual(collisions, {}, f"noms indistinguables : {collisions}")

    def test_the_folding_catches_the_case_that_slipped_through(self):
        self.assertEqual(self._pli("Jardins remarquables"), self._pli("Jardin remarquable"))
        # Mais pas deux noms qui partagent seulement un mot générique : le thème
        # « Monuments et édifices remarquables » et le label « Monument
        # historique classé » se distinguent très bien.
        self.assertNotEqual(
            self._pli("Monuments et édifices remarquables"),
            self._pli("Monument historique classé"),
        )


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
        def __init__(self, answer, near=None):
            self.answer = answer
            # Réponse rendue aux points DÉCALÉS seulement : c'est ainsi qu'on
            # simule un polygone communal qui s'arrête au trait de côte.
            self.near = near
            self.calls = 0
            self.origine = None

        def locate_commune(self, lat, lon):
            self.calls += 1
            if self.origine is not None and (lat, lon) != self.origine:
                return self.near
            return self.answer

        def locate_commune_near(self, lat, lon, radii_m=(500, 1500, 3000)):
            # La vraie logique d'azimuts, sur un point d'interrogation factice :
            # le test porte sur l'anneau, pas sur le client HTTP.
            from roam_pipeline.geocode import CommuneClient

            self.origine = (lat, lon)
            return CommuneClient.locate_commune_near(self, lat, lon, radii_m)

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

    def test_a_beach_just_offshore_is_attached_to_the_nearest_commune(self):
        from roam_pipeline.fetch import enrich_communes

        # Un polygone communal s'arrête au trait de côte. Wikidata place la
        # plage de Pampelonne à un kilomètre au large : elle n'appartenait donc
        # à aucune commune, et sans commune pas de département, donc aucune
        # collection géographique. Elle marquait 75,7 — le meilleur score du
        # littoral de PACA après la presqu'île de Giens — et sortait sans un mot.
        plage = make_place("Pampelonne", wikidata_id="Q1760862",
                           lat=43.227944, lon=6.66853, departement_code=None)
        commune = self._Commune(None, near=(self._commune("83101", "Ramatuelle", "83"), "93"))
        self.assertEqual(
            enrich_communes([plage], self._Address({}), commune), 1
        )
        self.assertEqual(plage.commune_name, "Ramatuelle")
        self.assertEqual(plage.departement_code, "83")
        self.assertEqual(plage.region_code, "93")

    def test_a_point_outside_france_costs_no_ring_of_calls(self):
        from roam_pipeline.fetch import enrich_communes

        # La passe d'azimuts coûte jusqu'à vingt-quatre requêtes. Sur les sept
        # cent quatre-vingt-trois lieux non situés, la quasi-totalité sont des
        # collectivités du Pacifique : les interroger serait une dépense pure.
        vaipo = make_place("Cascade de Vaipo", wikidata_id="Q2",
                           lat=-8.9, lon=-140.1, departement_code=None)
        commune = self._Commune(None)
        enrich_communes([vaipo], self._Address({}), commune)
        # Une seule interrogation : la deuxième passe. Pas d'anneau.
        self.assertEqual(commune.calls, 1)

    def test_the_envelope_knows_metropole_and_the_dom(self):
        from roam_pipeline.geocode import plausibly_french

        for nom, lat, lon in (("Pampelonne", 43.227944, 6.66853),
                              ("Grande Anse, Guadeloupe", 16.33, -61.79),
                              ("Saint-Denis, La Réunion", -20.88, 55.45)):
            with self.subTest(nom):
                self.assertTrue(plausibly_french(lat, lon))
        for nom, lat, lon in (("Nuku Hiva", -8.9, -140.1),
                              ("Nouméa", -22.27, 166.44),
                              ("Kerguelen", -49.35, 70.22)):
            with self.subTest(nom):
                self.assertFalse(plausibly_french(lat, lon))


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
        # « basilique mineure » est un TITRE, accordé à quantité d'églises
        # abbatiales : l'ajouter aux cathédrales a envoyé Saint-Victor de
        # Marseille et ses semblables hors de leur thème.
        ("abbayes", "cathedrales"),
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
        # Six dunes au départ, quatre après le périmètre — les dunes n'étant pas
        # un thème de liste, l'appartenance ne leur retire rien — deux après le
        # plancher, deux encore après les deux plafonds puis après les sosies,
        # puis quatre de nouveau : leur département est pauvre et le repêchage
        # géographique leur rend leur place. Le plafond de thème repasse en
        # dernier et ne leur retire rien — les dunes n'en ont pas.
        ligne = next(l for l in table.splitlines() if l.strip().startswith("dunes-marais"))
        self.assertEqual([int(n) for n in ligne.split()[1:]],
                         [6, 4, 4, 4, 4, 4, 4, 2, 2, 2, 2, 4, 4, 4])

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
        )
        self.assertEqual([p.name for p in kept], ["Gardé", "Non relu"])
        # Un lieu validé par un humain ne doit pas disparaître si un plancher bouge.
        self.assertTrue(garde.pinned)
        self.assertFalse(ignore.pinned)
        self.assertEqual(counts["pending"], 1)

    def test_promote_moves_a_tier_without_removing_anything(self):
        from roam_pipeline.review import apply_decisions

        haut = make_place("Remonté", wikidata_id="Q1")
        bas = make_place("Descendu", wikidata_id="Q2")
        kept, _ = apply_decisions(
            [haut, bas], {"Q1": ("promote", ""), "Q2": ("demote", "")}
        )
        self.assertEqual(len(kept), 2)
        self.assertEqual(haut.tier_shift, -1)
        self.assertEqual(bas.tier_shift, 1)


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
        # Un lot d'un seul thème dans un seul département vaut ×1,0 : le
        # rapport de caractérisation l'écarterait, et ce n'est pas ce qu'on
        # teste ici.
        _, collections = build_all(self._spread(30), _sans_lift())
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
            # remplace par sa forme, pas par son texte exact. Plusieurs thèmes
            # en déclarent maintenant ; le premier suffit à faire le test, et
            # c'est la configuration ENTIÈRE qu'on veut voir refuser le bloc.
            themes, count = re.subn(
                r"    broad_classes:\n(?:      .*\n|        .*\n)+", block + "\n",
                themes, count=1,
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

    def test_the_page_alternates_themes_after_filtering(self):
        # Rangées par identifiant, les abbayes ouvraient chaque niveau — deux
        # cents d'affilée avant la première cathédrale. Rangées par rang dans
        # leur thème, les lieux déjà décidés laissaient des trous et seuls les
        # petits thèmes défilaient. L'alternance doit donc se calculer sur ce
        # qui est RÉELLEMENT affiché, donc après le filtre, donc dans la page.
        with _capture():
            places = self._catalogue()
            _retained, collections = build_all(places, CONFIG)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "review.html"
            write_review_html(places, collections, CONFIG, path)
            body = path.read_text(encoding="utf-8")
        self.assertIn("function alterner(lieux)", body)
        self.assertIn("return alterner(retenus);", body)
        # Les sosies gardent leur propre tri : une paire ne se juge qu'entière.
        self.assertIn('if (state === "sosie") {', body)

    def test_the_page_carries_the_decisions_already_taken(self):
        # La mémoire de la curation vit dans `decisions.csv`, versionné. Si elle
        # ne descend pas dans la page, elle n'existe que dans le navigateur qui
        # l'a produite : ouvrir la revue ailleurs — un autre appareil, une autre
        # adresse — repart de zéro et fait relire un travail déjà fait.
        with _capture():
            places = self._catalogue()
            _retained, collections = build_all(places, CONFIG)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "review.html"
            write_review_html(
                places, collections, CONFIG, path, None,
                decided={"Q3": "keep", "Q404": "drop"},
            )
            body = path.read_text(encoding="utf-8")
        decided = json.loads(
            body.split("const DECIDED = ", 1)[1].split(";\n", 1)[0]
        )
        self.assertEqual(decided, {"Q3": "keep"})

    def test_a_decision_on_an_absent_place_is_not_carried(self):
        # Un `drop` a fait disparaître son lieu du catalogue : le rappeler à une
        # page qui ne l'affiche pas ne servirait qu'à fausser le compteur.
        with _capture():
            places = self._catalogue()
            _retained, collections = build_all(places, CONFIG)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "review.html"
            write_review_html(
                places, collections, CONFIG, path, None, decided={"Q404": "drop"},
            )
            body = path.read_text(encoding="utf-8")
        self.assertIn("const DECIDED = {};", body)


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

    def test_the_ladder_goes_below_the_lowest_floor_in_use(self):
        # L'échelle commençait à deux, le plancher de collecte le plus bas déjà
        # écrit : à la question « combien de plages Wikidata décrit-il SOUS
        # notre plancher ? », la commande répondait par le silence. Or c'est
        # cette question-là qui décide s'il vaut la peine de descendre.
        from roam_pipeline.cli import THRESHOLDS
        self.assertEqual(THRESHOLDS[:3], [0, 1, 2])

    def test_the_threshold_query_filters_nothing(self):
        # Compter à partir de zéro n'a de sens que si la requête ne coupe pas
        # elle-même sur la notoriété.
        sparql = class_thresholds_query("Q3947", [0, 2])
        self.assertIn("SUM(IF(?sitelinks >= 0, 1, 0)) AS ?n0", sparql)
        self.assertNotIn("FILTER(?sitelinks", sparql)


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


class TestBroadRouteYields(unittest.TestCase):
    """Une porte large ne vaut pas une porte précise.

    Le Petit Palais est un « musée d'art » — classe propre de `musees` — et une
    « maison », classe générique de `maisons`, déclaré plus tôt pour protéger
    les maisons-musées. L'ordre seul en faisait une maison d'artiste, avec tous
    les musées-palais.
    """

    @staticmethod
    def _pair(broad_theme="maisons", specific_theme="musees"):
        large = make_place("Petit Palais", theme=broad_theme, wikidata_id="Q1")
        large.via_broad_class = True
        precis = make_place("Petit Palais", theme=specific_theme, wikidata_id="Q1")
        return large, precis

    def test_a_generic_entry_yields_to_a_specific_one(self):
        large, precis = self._pair()
        for order in ([large, precis], [precis, large]):
            kept = dedupe_across_themes(order, CONFIG)
            self.assertEqual([p.theme_id for p in kept], ["musees"])

    def test_it_beats_the_declaration_order(self):
        # `maisons` est déclaré AVANT `musees` : sans cette règle, l'ordre
        # gagnerait, et c'est précisément ce qui rangeait les palais-musées
        # chez les maisons d'artistes.
        themes = [t.id for t in CONFIG.themes]
        self.assertLess(themes.index("maisons"), themes.index("musees"))

    def test_two_generic_entries_fall_back_on_the_order(self):
        a, b = self._pair(broad_theme="maisons", specific_theme="musees")
        b.via_broad_class = True
        kept = dedupe_across_themes([b, a], CONFIG)
        self.assertEqual([p.theme_id for p in kept], ["maisons"])

    def test_a_place_with_only_a_generic_entry_keeps_its_theme(self):
        # La fondation Claude-Monet n'est QUE « maison » : elle doit rester
        # une maison d'artiste, sans quoi la correction précédente serait
        # défaite par celle-ci.
        seule = make_place("Fondation Claude-Monet", theme="maisons", wikidata_id="Q2")
        seule.via_broad_class = True
        kept = dedupe_across_themes([seule], CONFIG)
        self.assertEqual([p.theme_id for p in kept], ["maisons"])

    def test_a_pinned_place_still_imposes_its_theme(self):
        # Un choix explicite du curateur passe avant toute règle automatique.
        large, precis = self._pair()
        large.pinned = True
        kept = dedupe_across_themes([precis, large], CONFIG)
        self.assertEqual([p.theme_id for p in kept], ["maisons"])

    def test_amusement_parks_have_their_generic_class(self):
        # « parc de loisirs » est le terme générique français : sans lui, un
        # parc qu'aucune des sept classes précises ne nomme passait encore.
        self.assertIn("Q15982170", CONFIG.exclusions.qids)


class TestFetchState(unittest.TestCase):
    """Un thème dont la collecte a échoué ne doit pas se taire indéfiniment.

    L'échec était signalé une fois, en fin de journal, puis oublié : la reprise
    partielle reconduisait les anciennes données à chaque passage. Le mont
    Blanc a disparu du catalogue de cette façon, sans qu'aucun compteur ne
    bouge et sans qu'aucun message ne le dise.
    """

    def test_a_failed_theme_is_reported_at_every_build(self):
        state = {t.id: {"ok": True, "lieux": 5, "le": "2026-08-28"} for t in CONFIG.themes}
        state["sommets"] = {"ok": False, "lieux": 950, "le": "2026-08-20"}
        stale = dict(stale_themes(state, CONFIG))
        self.assertIn("sommets", stale)
        self.assertIn("ÉCHEC", stale["sommets"])

    def test_a_theme_that_returned_nothing_is_suspect(self):
        # Une collecte « réussie » qui ne rapporte rien est un échec silencieux.
        state = {t.id: {"ok": True, "lieux": 5, "le": "x"} for t in CONFIG.themes}
        state["phares"] = {"ok": True, "lieux": 0, "le": "x"}
        self.assertIn("phares", dict(stale_themes(state, CONFIG)))

    def test_an_untracked_theme_is_named_apart(self):
        # Distinct d'un échec : le suivi est récent, tout est « jamais vu » au
        # premier passage, et confondre les deux noierait le vrai signal.
        stale = dict(stale_themes({}, CONFIG))
        self.assertEqual(len(stale), len(CONFIG.themes))
        self.assertTrue(all(r.startswith("jamais") for r in stale.values()))

    def test_a_healthy_catalogue_says_nothing(self):
        state = {t.id: {"ok": True, "lieux": 5, "le": "x"} for t in CONFIG.themes}
        self.assertEqual(stale_themes(state, CONFIG), [])


class TestEmptyThemes(unittest.TestCase):
    """Un catalogue partiel ne doit pas avoir l'air complet.

    Sur une machine fraîchement clonée, `places_raw.json` n'existe pas :
    collecter deux ou trois thèmes suffit à produire un catalogue qui a l'air
    entier et auquel il manque vingt thèmes. C'est ainsi qu'un aperçu publié
    s'est retrouvé sans une seule abbaye — et que `explain maubuisson` ne
    répondait pas « écarté » mais « aucun lieu ».
    """

    def test_a_theme_without_a_single_candidate_is_named(self):
        raw = [make_place("Château de X", theme="chateaux")]
        vides = empty_themes(CONFIG, raw)
        self.assertIn("abbayes", vides)
        self.assertNotIn("chateaux", vides)

    def test_a_full_catalogue_names_nothing(self):
        raw = [make_place(f"Lieu {theme.id}", theme=theme.id) for theme in CONFIG.themes]
        self.assertEqual(empty_themes(CONFIG, raw), [])

    def test_the_proof_needs_no_state_file(self):
        # Le fichier d'état ne dit rien des collectes antérieures à sa mise en
        # place, et son message rassurant couvrait exactement ce cas. Le
        # catalogue brut, lui, ne ment pas.
        self.assertEqual(len(empty_themes(CONFIG, [])), len(CONFIG.themes))


class TestUnknownAccessReview(unittest.TestCase):
    """Le château de Champlatreux : privé, loué pour des mariages, au catalogue.

    Aucun signal ne le trahit. Wikidata ne dit rien de l'accueil du public, et
    OpenStreetMap ne le tague ni ouvert ni fermé. Sur deux mille deux cent
    quatre-vingt-dix lieux, mille deux cent soixante-sept sont dans ce cas :
    c'est la population où se cachent les lieux qu'on ne visite pas, et la
    seule façon de la traiter est de savoir la regarder.
    """

    @staticmethod
    def _page(places):
        with _capture():
            retained, collections = build_all(places, CONFIG)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "review.html"
            write_review_html(places, collections, CONFIG, path)
            return path.read_text(encoding="utf-8")

    def test_the_page_offers_to_filter_on_the_doubt(self):
        body = self._page([make_place("Château de Champlatreux", sitelinks=12)])
        self.assertIn('value="doute"', body)

    def test_a_place_without_a_signal_says_so_on_its_card(self):
        # Le filtre ne suffit pas : relire cent châteaux sans savoir lesquels
        # sont douteux, c'est relire sans rien voir.
        muet = make_place("Château de Champlatreux", sitelinks=12)
        self.assertIsNone(muet.visitable)
        self.assertIn("Accueil du public non renseigné", self._page([muet]))

    def test_a_confirmed_place_carries_no_doubt(self):
        ouvert = make_place("Château de Chambord", sitelinks=40)
        ouvert.visitable = True
        body = self._page([ouvert])
        self.assertIn('"visitable":true', body.replace(" ", ""))


class TestGeographicSpread(unittest.TestCase):
    """Un département ne doit pas occuper une collection nationale.

    Le score mesure la documentation, et Paris est documenté comme nulle part
    ailleurs : vingt-cinq des quarante ponts de la collection nationale étaient
    parisiens. Ce n'est pas un fait de géographie mais un fait d'écriture — les
    volcans sont vraiment en Auvergne, les ponts ne sont pas vraiment à Paris.
    """

    @staticmethod
    def _lieux(par_dept):
        places, score = [], 100.0
        for dept, combien in par_dept:
            for i in range(combien):
                p = make_place(f"Pont {dept}-{i}", theme="ponts", wikidata_id=f"Q{dept}{i}")
                p.departement_code, p.score = dept, score
                score -= 1
                places.append(p)
        return sorted(places, key=lambda p: (-p.score, p.name))

    def test_one_department_cannot_fill_the_collection(self):
        # Trois départements, quota de sept : vingt et une places possibles
        # pour vingt à pourvoir, donc le quota tient sans repli.
        ordre = self._lieux([("75", 20), ("33", 10), ("13", 10)])
        retenus = _spread(ordre, limit=20, max_per_dept=7)
        compte = Counter(p.departement_code for p in retenus)
        self.assertEqual(compte["75"], 7)
        self.assertEqual(len(retenus), 20)

    def test_a_quota_too_tight_to_fill_falls_back_rather_than_shrink(self):
        # Trois départements, quota de cinq : quinze places seulement pour
        # vingt à pourvoir. Le repli complète avec les meilleurs écartés — donc
        # des Parisiens — plutôt que de rendre une collection amputée.
        ordre = self._lieux([("75", 20), ("33", 10), ("13", 10)])
        retenus = _spread(ordre, limit=20, max_per_dept=5)
        self.assertEqual(len(retenus), 20)
        self.assertGreater(Counter(p.departement_code for p in retenus)["75"], 5)

    def test_the_best_of_each_territory_comes_first(self):
        # Le quota s'applique dans l'ordre du score : on prend le meilleur de
        # chaque département avant d'y revenir pour un deuxième.
        ordre = self._lieux([("75", 3), ("33", 3)])
        retenus = _spread(ordre, limit=2, max_per_dept=1)
        self.assertEqual({p.departement_code for p in retenus}, {"75", "33"})

    def test_it_never_shrinks_the_collection(self):
        # Sans ce repli, un thème concentré perdrait des lieux au lieu d'en
        # échanger : mieux vaut une collection un peu parisienne qu'une
        # collection trop courte pour exister.
        ordre = self._lieux([("75", 18), ("33", 2)])
        retenus = _spread(ordre, limit=15, max_per_dept=5)
        self.assertEqual(len(retenus), 15)
        self.assertGreater(Counter(p.departement_code for p in retenus)["75"], 5)

    def test_the_fallback_keeps_the_ranking(self):
        ordre = self._lieux([("75", 18), ("33", 2)])
        retenus = _spread(ordre, limit=15, max_per_dept=5)
        self.assertEqual(retenus, sorted(retenus, key=lambda p: (-p.score, p.name)))

    def test_only_the_biased_themes_carry_a_quota(self):
        # Les volcans SONT en Auvergne et les phares en Bretagne : leur imposer
        # un quota abîmerait une vérité géographique au lieu de corriger un
        # biais d'écriture.
        avec = {t.id for t in CONFIG.themes if t.max_per_departement}
        self.assertIn("ponts", avec)
        for nature in ("volcans", "phares", "grottes", "cascades", "sommets"):
            self.assertNotIn(nature, avec)

    def test_a_geographic_collection_keeps_no_quota(self):
        # « Ponts de Paris » doit évidemment être parisienne de bout en bout.
        with _capture():
            places = self._lieux([("75", 12)])
            _retained, collections = build_all(places, CONFIG)
        paris = [c for c in collections if c.geo_code == "75" and c.theme_id == "ponts"]
        if paris:
            self.assertEqual(len(paris[0].places), 12)


class TestVersionedCollection(unittest.TestCase):
    """La collecte est une donnée, pas un produit de construction.

    Wikidata bouge, les requêtes expirent, un thème échoue sans rien arrêter :
    deux machines qui lancent la même commande le même jour n'obtiennent pas le
    même catalogue. Or les décisions éditoriales portent sur des Q-id précis —
    une décision prise sur un lieu que l'autre machine n'a pas collecté ne veut
    rien dire. D'où un fichier par thème, versionné.
    """

    @staticmethod
    def _place(qid, theme="chateaux", **kwargs):
        return make_place(f"Lieu {qid}", theme=theme, wikidata_id=qid, **kwargs)

    def test_a_failed_theme_keeps_its_previous_collection(self):
        # Le fichier unique était réécrit d'un bloc : un thème qui expirait au
        # milieu d'une collecte complète perdait ses lieux, et seul le journal
        # le disait. Le mont Blanc a disparu de cette façon.
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp)
            write_raw(raw, [self._place("Q1", "sommets")], replacing={"sommets"})
            # Collecte suivante : `chateaux` réussit, `sommets` échoue et n'est
            # donc pas dans `replacing`.
            write_raw(raw, [self._place("Q2", "chateaux")], replacing={"chateaux"})
            recompose = {p.wikidata_id for p in read_raw(raw)}
        self.assertEqual(recompose, {"Q1", "Q2"})

    def test_a_theme_that_returns_nothing_loses_its_file(self):
        # Un thème retiré de la configuration, ou vidé volontairement, ne doit
        # pas revivre à chaque lecture.
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp)
            write_raw(raw, [self._place("Q1", "sommets")], replacing={"sommets"})
            write_raw(raw, [], replacing={"sommets"})
            self.assertEqual(read_raw(raw), [])
            self.assertEqual(shards(raw), [])

    def test_manual_additions_survive_a_partial_fetch(self):
        # Les ajouts épinglés appartiennent à des thèmes variés mais sont
        # recollectés à chaque passage : rangés dans le fichier de leur thème,
        # ceux des thèmes non recollectés disparaîtraient.
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp)
            write_raw(
                raw,
                [self._place("Q1", "sommets"), self._place("Q9", "abbayes", pinned=True)],
                replacing={"sommets", EXTRA_SHARD},
            )
            write_raw(raw, [self._place("Q2", "sommets")], replacing={"sommets"})
            recompose = {p.wikidata_id for p in read_raw(raw)}
        self.assertEqual(recompose, {"Q2", "Q9"})

    def test_an_addition_wins_over_the_automatic_attachment(self):
        # Un lieu épinglé l'emporte sur le rattachement automatique — c'est la
        # règle de la collecte, la lecture doit la respecter aussi.
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp)
            write_raw(raw, [self._place("Q1", "chateaux")], replacing={"chateaux"})
            write_raw(raw, [self._place("Q1", "maisons", pinned=True)],
                      replacing={EXTRA_SHARD})
            places = read_raw(raw)
        self.assertEqual(len(places), 1)
        self.assertEqual(places[0].theme_id, "maisons")

    def test_the_enrichment_survives_the_round_trip(self):
        # Ce qui coûte cher à obtenir — résumés, ouverture au public — doit
        # traverser le dépôt intact, sinon l'autre machine relit un catalogue
        # appauvri sans qu'aucune erreur ne le dise.
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp)
            write_raw(
                raw,
                [self._place("Q1", summary="Deux phrases.", visitable=True,
                             opening_hours="Tu-Su 10:00-18:00", visitors_per_year=42_000)],
                replacing={"chateaux"},
            )
            place = read_raw(raw)[0]
        self.assertEqual(place.summary, "Deux phrases.")
        self.assertIs(place.visitable, True)
        self.assertEqual(place.opening_hours, "Tu-Su 10:00-18:00")
        self.assertEqual(place.visitors_per_year, 42_000)

    def test_two_identical_collections_write_identical_bytes(self):
        # Un fichier réécrit dans un autre ordre à chaque collecte rendrait
        # tout `git diff` illisible, et donc inutile.
        with tempfile.TemporaryDirectory() as tmp:
            un, deux = Path(tmp) / "un", Path(tmp) / "deux"
            places = [self._place("Q3"), self._place("Q1"), self._place("Q2")]
            write_raw(un, places, replacing={"chateaux"})
            write_raw(deux, list(reversed(places)), replacing={"chateaux"})
            self.assertEqual(
                (un / "chateaux.json").read_text(encoding="utf-8"),
                (deux / "chateaux.json").read_text(encoding="utf-8"),
            )

    def test_the_file_holds_one_place_per_line(self):
        # C'est ce qui fait qu'un ajout de trois lieux se lit comme trois
        # lignes ajoutées, et non comme un fichier entier réécrit.
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp)
            write_raw(raw, [self._place("Q1"), self._place("Q2")], replacing={"chateaux"})
            body = (raw / "chateaux.json").read_text(encoding="utf-8")
        self.assertEqual(len(body.strip().splitlines()), 4)  # [ + 2 lieux + ]
        self.assertEqual(len(json.loads(body)), 2)

    def test_a_place_stays_in_every_theme_that_claimed_it(self):
        # Le Louvre est un palais ET un musée : la collecte le rend deux fois,
        # et c'est `dedupe_across_themes` qui tranche, avec la règle du plus
        # spécifique. Réduire à un lieu par Q-id à la lecture lui retirerait le
        # choix et laisserait l'ordre alphabétique des fichiers décider.
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp)
            write_raw(raw, [self._place("Q1", "musees")], replacing={"musees"})
            write_raw(raw, [self._place("Q1", "jardins")], replacing={"jardins"})
            themes = sorted(p.theme_id for p in read_raw(raw))
        self.assertEqual(themes, ["jardins", "musees"])

    def test_an_adopted_candidate_only_fills_a_gap(self):
        # Quand une requête par classe a déjà trouvé le lieu, c'est ce
        # rattachement-là qui vaut, pas le thème deviné depuis OpenStreetMap.
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp)
            write_raw(raw, [self._place("Q1", "musees")], replacing={"musees"})
            write_raw(raw, [self._place("Q1", "jardins", source="osm")],
                      replacing={EXTRA_SHARD})
            places = read_raw(raw)
        self.assertEqual([p.theme_id for p in places], ["musees"])

    def test_a_theme_gone_from_the_configuration_is_not_published(self):
        # Un thème retiré de la configuration n'est plus recollecté par
        # personne : son fichier resterait dans le dépôt indéfiniment, et ses
        # lieux fausseraient chaque diagnostic sans sortir dans aucune
        # collection. C'est ainsi que « sources » a survécu à sa suppression.
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp)
            write_raw(raw, [self._place("Q1", "sources")], replacing={"sources"})
            configures = {"chateaux", "musees", EXTRA_SHARD}
            oublies = [nom for nom in shards(raw) if nom not in configures]
            self.assertEqual(oublies, ["sources"])

    def test_an_unreadable_file_does_not_take_the_rest_down(self):
        # Un fichier tronqué par une interruption ne doit pas rendre tout le
        # catalogue illisible.
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp)
            write_raw(raw, [self._place("Q1", "sommets")], replacing={"sommets"})
            (raw / "chateaux.json").write_text("[{tronqu", encoding="utf-8")
            with _capture():
                places = read_raw(raw)
        self.assertEqual([p.wikidata_id for p in places], ["Q1"])


class TestCuratorTheme(unittest.TestCase):
    """Le rattachement automatique se trompe quand la classe décrit une PARTIE.

    Le musée Christian-Dior est classé « jardin » parce que sa villa en a un
    remarquable. Wikidata n'a pas tort : c'est la hiérarchie des classes qui ne
    dit pas ce qu'on vient voir. Aucune règle générale ne rattrape cela.
    """

    KNOWN = {"musees", "jardins", "maisons"}

    @staticmethod
    def _place(theme, qid="Q1", **kwargs):
        return make_place(f"Musée {qid}", theme=theme, wikidata_id=qid, **kwargs)

    def test_the_place_leaves_its_other_attachments(self):
        # Changer l'étiquette d'un seul exemplaire ne suffirait pas : le
        # doublon inter-thèmes resterait, et la règle du plus spécifique
        # continuerait de trancher toute seule.
        places = [self._place("jardins"), self._place("musees")]
        redressed, inconnus = apply_themes(places, {"Q1": ("musees", "")}, self.KNOWN)
        self.assertEqual(inconnus, [])
        self.assertEqual([(p.wikidata_id, p.theme_id) for p in redressed],
                         [("Q1", "musees")])

    def test_it_wins_against_the_declaration_order(self):
        # `musees` est déclaré avant `jardins` : sans le retrait des autres
        # rattachements, un lieu qu'on veut en jardins y resterait piégé.
        places = [self._place("musees"), self._place("jardins")]
        redressed, _ = apply_themes(places, {"Q1": ("jardins", "")}, self.KNOWN)
        with _capture():
            survivants = dedupe_across_themes(score_all(redressed, CONFIG), CONFIG)
        self.assertEqual([p.theme_id for p in survivants], ["jardins"])

    def test_a_human_decision_is_the_most_specific_attachment(self):
        # Entré par une classe générique, le lieu cédait devant n'importe quelle
        # entrée précise. Une décision humaine ne doit pas céder.
        places = [self._place("maisons", via_broad_class=True)]
        redressed, _ = apply_themes(places, {"Q1": ("maisons", "")}, self.KNOWN)
        self.assertFalse(redressed[0].via_broad_class)

    def test_an_unknown_theme_is_reported_and_changes_nothing(self):
        # Une faute de frappe dans le fichier ne doit pas faire disparaître un
        # lieu dans un thème qui n'existe pas.
        places = [self._place("jardins")]
        redressed, inconnus = apply_themes(places, {"Q1": ("musée", "")}, self.KNOWN)
        self.assertEqual(inconnus, ["Q1"])
        self.assertEqual([p.theme_id for p in redressed], ["jardins"])

    def test_the_choice_survives_a_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "themes.csv"
            write_themes(path, {"Q1": ("musees", "le jardin n'est pas le sujet")})
            relu = read_themes(path)
        self.assertEqual(relu, {"Q1": ("musees", "le jardin n'est pas le sujet")})

    def test_a_place_nobody_redirected_is_left_alone(self):
        places = [self._place("jardins", qid="Q9")]
        redressed, _ = apply_themes(places, {"Q1": ("musees", "")}, self.KNOWN)
        self.assertEqual([p.theme_id for p in redressed], ["jardins"])


class TestThemeDoubt(unittest.TestCase):
    """Attirer l'œil là où le rattachement mérite un second regard.

    Deux signaux, et un seul suffit : plusieurs thèmes ont réclamé le lieu, ou
    son NOM annonce autre chose que son thème. Ni l'un ni l'autre ne range quoi
    que ce soit — la revue reste le lieu de la décision, mais elle sait
    désormais où regarder.
    """

    HINTS = None

    def setUp(self):
        self.HINTS = name_hints(CONFIG)

    def test_the_name_carries_the_type_of_the_place(self):
        # Le nom français d'un lieu commence par son type. C'est le seul signal
        # que Wikidata ne donne pas quand la classe décrit une PARTIE du lieu.
        self.assertEqual(theme_from_name("Musée Christian Dior", self.HINTS), "musees")
        self.assertEqual(theme_from_name("Abbaye Saint-Victor", self.HINTS), "abbayes")

    def test_an_article_does_not_hide_the_type(self):
        self.assertEqual(theme_from_name("Le Pont du Gard", self.HINTS), "ponts")

    def test_a_name_that_announces_nothing_stays_silent(self):
        # Pas d'indice plutôt qu'un mauvais indice : « monuments » est le thème
        # fourre-tout, son nom ne prouve rien.
        self.assertIsNone(theme_from_name("Arc de Triomphe", self.HINTS))

    def test_a_word_claimed_by_two_themes_proves_nothing(self):
        # « Site » nomme trois thèmes : il ne peut désigner personne.
        self.assertNotIn("site", self.HINTS)

    def test_a_contested_place_is_flagged(self):
        # Le Louvre réclamé par « musées » et « châteaux » est un arbitrage du
        # pipeline, pas un fait. Après dédoublonnage il n'en reste aucune trace.
        places = [make_place("Palais du Louvre", theme="musees", wikidata_id="Q1"),
                  make_place("Palais du Louvre", theme="chateaux", wikidata_id="Q1")]
        self.assertEqual(theme_claims(places), {"Q1": ["chateaux", "musees"]})

    def test_a_place_one_theme_claimed_is_not_contested(self):
        places = [make_place("Château seul", theme="chateaux", wikidata_id="Q1")]
        self.assertEqual(theme_claims(places), {})

    def test_the_page_carries_both_signals(self):
        with _capture():
            places = [make_place(f"Jardin {i}", theme="jardins", wikidata_id=f"Q{i}",
                                 sitelinks=9, lat=45 + i * 0.1) for i in range(9)]
            places.append(make_place("Musée Christian Dior", theme="jardins",
                                     wikidata_id="Q99", sitelinks=9, lat=48.8))
            scored = score_all(places, CONFIG)
            retained, collections = build_all(scored, CONFIG)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "review.html"
            write_review_html(retained, collections, CONFIG, path,
                              claims={"Q99": ["jardins", "musees"]})
            body = path.read_text(encoding="utf-8")
        data = json.loads(body.split("const DATA = ", 1)[1].split(";\nconst THEMES", 1)[0])
        dior = next(row for row in data if row["id"] == "Q99")
        self.assertEqual(dior["suggests"], "musees")
        self.assertEqual(dior["disputed"], ["Musées"])
        self.assertIn('data-role="theme"', body)

    def test_a_theme_gone_from_the_configuration_does_not_break_the_page(self):
        # Une collecte antérieure peut porter des lieux d'un thème retiré de
        # `themes.yaml`. Lui demander son nom d'affichage pour une mention de
        # confort faisait tomber toute la construction.
        with _capture():
            places = [make_place(f"Jardin {i}", theme="jardins", wikidata_id=f"Q{i}",
                                 sitelinks=9, lat=45 + i * 0.1) for i in range(9)]
            scored = score_all(places, CONFIG)
            retained, collections = build_all(scored, CONFIG)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "review.html"
            write_review_html(retained, collections, CONFIG, path,
                              claims={"Q1": ["jardins", "sources"]})
            body = path.read_text(encoding="utf-8")
        data = json.loads(body.split("const DATA = ", 1)[1].split(";\nconst THEMES", 1)[0])
        self.assertEqual(next(r for r in data if r["id"] == "Q1")["disputed"], [])

    def test_the_sheet_carries_only_the_themes_that_changed(self):
        # Réécrire les deux mille autres ferait de `themes.csv` une copie du
        # catalogue, et de chaque revue un diff illisible.
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "decisions.csv"
            path.write_text(
                "decision,curator_note,theme_id,name,wikidata_id\n"
                "keep,,,\"Un jardin\",Q1\n"
                ",,musees,\"Musée Christian Dior\",Q2\n",
                encoding="utf-8",
            )
            self.assertEqual(read_review_themes(path), {"Q2": "musees"})
            self.assertEqual(read_review_csv(path), {"Q1": ("keep", "")})


class TestCurationMerge(unittest.TestCase):
    """Deux soirées de relecture menées chacune de son côté.

    Les fichiers de curation sont réécrits en entier, triés par identifiant :
    git ne sait pas les départager et pose des marqueurs au milieu d'un travail
    que personne n'a perdu. Ce ne sont pourtant pas des textes mais des tables
    dont la clé est le Q-id — la fusion juste est l'union des deux côtés.
    """

    ENTETE = "# Décisions.\n#\nwikidata_id,decision,name,note\n"

    def _conflit(self, nous, eux):
        return (self.ENTETE + "<<<<<<< HEAD\n" + nous + "=======\n" + eux
                + ">>>>>>> telephone\n")

    def test_the_two_versions_are_recovered_whole(self):
        # Les parties communes appartiennent aux deux versions : les oublier
        # amputerait le fichier de tout ce sur quoi les deux machines
        # s'accordent.
        texte = (self.ENTETE + "Q0,keep,Commun,\n<<<<<<< HEAD\nQ1,drop,A,\n"
                 "=======\nQ2,keep,B,\n>>>>>>> telephone\n")
        nous, eux = split_conflict(texte)
        self.assertIn("Q0,keep,Commun,", nous)
        self.assertIn("Q0,keep,Commun,", eux)
        self.assertIn("Q1,drop,A,", nous)
        self.assertNotIn("Q1,drop,A,", eux)

    def test_nothing_is_lost_from_either_side(self):
        fusion, rapport = merge_text(
            *split_conflict(self._conflit("Q1,keep,A,\n", "Q2,drop,B,\n"))
        )
        self.assertIn("Q1,keep,A,", fusion)
        self.assertIn("Q2,drop,B,", fusion)
        self.assertEqual(rapport.kept, 2)
        self.assertEqual(rapport.added, 1)

    def test_a_disagreement_is_named_not_silently_settled(self):
        # Le seul cas où la machine choisit à la place du curateur. Il doit
        # pouvoir y revenir, donc il doit le lire.
        fusion, rapport = merge_text(
            *split_conflict(self._conflit("Q1,drop,A,\n", "Q1,keep,A,\n"))
        )
        self.assertEqual(rapport.disagreements, [("Q1", "drop", "keep")])
        self.assertIn("Q1,drop,A,", fusion)

    def test_the_ancestor_section_is_ignored(self):
        # `merge.conflictStyle = diff3` ajoute une troisième version, celle
        # d'avant les deux revues : la reprendre ressusciterait des verdicts
        # que les deux machines ont changés.
        texte = (self.ENTETE + "<<<<<<< HEAD\nQ1,drop,A,\n|||||||\nQ1,keep,A,\n"
                 "=======\nQ2,keep,B,\n>>>>>>> telephone\n")
        nous, eux = split_conflict(texte)
        self.assertIn("Q1,drop,A,", nous)
        self.assertNotIn("Q1", eux)

    def test_the_comment_header_survives(self):
        # C'est lui qui explique le fichier à qui l'ouvre six mois plus tard.
        fusion, _ = merge_text(*split_conflict(self._conflit("Q1,keep,A,\n", "Q2,keep,B,\n")))
        self.assertTrue(fusion.startswith("# Décisions."))

    def test_a_file_without_conflict_is_left_alone(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "decisions.csv"
            path.write_text(self.ENTETE + "Q1,keep,A,\n", encoding="utf-8")
            self.assertIsNone(merge_file(path))
            self.assertIn("Q1,keep,A,", path.read_text(encoding="utf-8"))

    def test_a_table_without_the_key_is_refused(self):
        # Mieux vaut s'arrêter que fusionner au hasard un fichier qu'on n'a pas
        # compris.
        with self.assertRaises(ValueError):
            merge_text("a,b\n1,2\n", "a,b\n3,4\n")


class TestCuratorAdjustments(unittest.TestCase):
    """Un déplacement d'un niveau, pas un décalage de points.

    La première version ajoutait ou retirait soixante points. Un décalage de
    score ne peut pas exprimer une intention de rang : deux lieux au même score
    ne sont pas dans le même voisinage, et la même correction en déplaçait un de
    deux niveaux, un autre d'aucun. Mesuré sur le catalogue réel, seuls 25
    `demote` sur 73 descendaient d'un cran ; 27 en perdaient deux et 15
    disparaissaient du catalogue — alors qu'écarter, c'est `drop`.
    """

    @staticmethod
    def _collection(n=45):
        # Tous au-dessus du plancher du thème : il faut plus de 35 lieux pour
        # que le niveau 3 existe, et donc pour éprouver le bout de l'échelle.
        return [make_place(f"Château {i:02d}", sitelinks=60 - i // 2,
                           lat=45 + i * 0.1, wikidata_id=f"Q{i}")
                for i in range(1, n + 1)]

    def _niveaux(self, decisions):
        with _capture():
            places = score_all(self._collection(), CONFIG)
            kept, _ = apply_decisions(places, decisions)
            score_all(kept, CONFIG)
            _retenus, collections = build_all(kept, CONFIG)
        return review_tiers(collections)

    def test_a_demote_moves_exactly_one_tier(self):
        # L'intention du curateur est « descends-le d'un cran », pas « retire-lui
        # soixante points ». Le déplacement s'applique APRÈS le classement,
        # donc il vaut quel que soit le voisinage du lieu.
        avant = self._niveaux({})
        vise = next(q for q, t in avant.items() if t == 1)
        apres = self._niveaux({vise: ("demote", "")})
        self.assertEqual(apres[vise], avant[vise] + 1)

    def test_a_promote_moves_exactly_one_tier(self):
        avant = self._niveaux({})
        vise = next(q for q, t in avant.items() if t == 2)
        apres = self._niveaux({vise: ("promote", "")})
        self.assertEqual(apres[vise], 1)

    def test_a_demote_never_removes_a_place(self):
        # C'est toute la distinction entre `drop` et `demote`, et le malus en
        # points l'effaçait : quinze lieux du catalogue réel disparaissaient
        # sans que personne ait décidé de les écarter.
        avant = self._niveaux({})
        vise = next(q for q, t in avant.items() if t == 1)
        apres = self._niveaux({vise: ("demote", "")})
        self.assertIn(vise, apres)

    def test_the_scale_has_ends(self):
        # Un `demote` sur un niveau 3 ne peut rien faire. C'est honnête : il n'y
        # a pas de niveau 4, et écarter reste un geste distinct.
        avant = self._niveaux({})
        vise = next(q for q, t in avant.items() if t == 3)
        apres = self._niveaux({vise: ("demote", "")})
        self.assertEqual(apres[vise], 3)

    def test_a_demoted_place_frees_its_slot(self):
        # Le décompte porte sur le niveau FINAL. Sinon un lieu descendu occupe
        # une place de niveau 1 sans y figurer, et le lieu suivant recule sans
        # que personne l'ait voulu : cinquante-huit lieux gardés reculaient
        # ainsi d'un cran sur le catalogue réel.
        avant = self._niveaux({})
        premiers = [q for q, t in sorted(avant.items()) if t == 1]
        apres = self._niveaux({premiers[0]: ("demote", "")})
        self.assertEqual(sum(1 for t in avant.values() if t == 1),
                         sum(1 for t in apres.values() if t == 1))

    def test_no_one_else_moves_when_a_place_is_demoted(self):
        avant = self._niveaux({})
        vise = next(q for q, t in avant.items() if t == 1)
        apres = self._niveaux({vise: ("demote", "")})
        bouges = {q for q in avant if avant[q] != apres.get(q)}
        # Le lieu visé descend, et un seul autre monte pour prendre sa place.
        self.assertIn(vise, bouges)
        self.assertLessEqual(len(bouges), 2)

    def test_the_list_stays_ordered_by_tier(self):
        # Un lieu descendu garde son score : sans renumérotation, la collection
        # afficherait un niveau 3 avant un niveau 1.
        with _capture():
            places = score_all(self._collection(), CONFIG)
            kept, _ = apply_decisions(places, {"Q1": ("demote", "")})
            score_all(kept, CONFIG)
            _retenus, collections = build_all(kept, CONFIG)
        nationale = next(c for c in collections
                         if c.kind == "theme" and not c.geo_code)
        niveaux = [m.tier for m in nationale.places]
        self.assertEqual(niveaux, sorted(niveaux))

    def test_outside_the_national_collection_is_not_a_level(self):
        # « Niveau 3 » et « pas dans la collection nationale » sont deux états
        # différents. Les confondre a rendu la revue des abbayes interminable :
        # 23 lieux au niveau 3 de la collection, et 99 qui n'y sont pas du tout,
        # tous affichés « NIVEAU 3 ».
        with _capture():
            places = score_all(self._collection(60), CONFIG)
            retenus, collections = build_all(places, CONFIG)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "review.html"
            write_review_html(retenus, collections, CONFIG, path)
            body = path.read_text(encoding="utf-8")
        data = json.loads(body.split("const DATA = ", 1)[1].split(";\nconst THEMES", 1)[0])
        nationale = next(c for c in collections
                         if c.kind == "theme" and not c.geo_code)
        membres = {m.place_id for m in nationale.places}
        for row in data:
            self.assertEqual(row["national"], row["id"] in membres)
        # La collection nationale vient en tête : c'est elle que l'app montre.
        self.assertTrue(data[0]["national"])
        self.assertIn('value="nationale"', body)

    def test_a_verdict_can_be_withdrawn(self):
        # `clear` n'est pas un verdict qu'on enregistre, c'est un verdict qu'on
        # efface. Sans lui, se dédire demandait d'ouvrir le CSV à la main — et
        # un curateur qui doit éditer un fichier pour revenir sur une décision
        # finit par ne plus revenir sur ses décisions.
        self.assertNotIn(CLEAR, DECISIONS)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "decisions.csv"
            write_decisions(path, {"Q1": ("demote", ""), "Q2": ("keep", "")},
                            {"Q1": "Un pont", "Q2": "Une abbaye"})
            gardees = read_decisions(path)
            gardees.pop("Q1")
            write_decisions(path, gardees, {"Q2": "Une abbaye"})
            self.assertEqual(set(read_decisions(path)), {"Q2"})

    def test_a_sheet_that_brings_nothing_is_recognisable(self):
        # Rejouer un ANCIEN téléchargement ne change rien à `decisions.csv` :
        # c'est le seul signe, et il faut le voir. Chrome numérote les doublons
        # — « review-decisions (1).csv » — et le premier de la liste est le plus
        # vieux. Une revue entière a été perdue ainsi.
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "decisions.csv"
            write_decisions(path, {"Q1": ("keep", "")}, {"Q1": "Un château"})
            avant = read_decisions(path)
            rejoue = {"Q1": ("keep", "")}
            changed = sum(1 for q, d in rejoue.items()
                          if avant.get(q, ("", ""))[0] != d[0])
        self.assertEqual(changed, 0)

    def test_a_keep_still_pins(self):
        places = score_all(self._collection(), CONFIG)
        kept, _ = apply_decisions(places, {"Q1": ("keep", "")})
        self.assertTrue(next(p for p in kept if p.wikidata_id == "Q1").pinned)

    def test_a_field_the_model_no_longer_knows_is_ignored(self):
        # La collecte versionnée survit à ses lecteurs : les fichiers du dépôt
        # portent encore `curator_adjustment`. Le refuser rendrait tout le
        # catalogue illisible d'un coup.
        place = Place.from_dict({
            "wikidata_id": "Q1", "name": "Un château", "theme_id": "chateaux",
            "lat": 45.0, "lon": 2.0, "curator_adjustment": 60.0, "slug": "un-chateau",
        })
        self.assertEqual(place.name, "Un château")
        self.assertEqual(place.tier_shift, 0)


class TestPageviews(unittest.TestCase):
    """L'intérêt du public d'ici, quand les langues ne disent que celui du monde.

    Le Champ-de-Mars figure dans cinquante-six langues parce que la tour Eiffel
    s'y trouve, les jardins de la Fontaine dans six. Le décompte de langues
    mesure la documentation internationale d'un lieu, pas l'envie d'y aller.
    """

    @staticmethod
    def _config(weight, scale=500):
        return replace(CONFIG, pageviews=replace(CONFIG.pageviews,
                                                 weight=weight, scale=scale))

    def test_a_signal_collected_is_not_a_signal_adopted(self):
        # Poids nul par défaut : la donnée se collecte, s'observe, et ne pèse
        # que le jour où on l'écrit dans `scoring.yaml`. C'est ce qui permet de
        # mesurer avant d'adopter.
        place = make_place("Un jardin", pageviews_per_month=50_000)
        self.assertEqual(score_breakdown(place, self._config(0))["consultations"], 0.0)
        self.assertGreater(score_breakdown(place, self._config(16))["consultations"], 0)

    def test_no_data_costs_nothing(self):
        # Même règle que l'accueil du public et la fréquentation : l'absence de
        # donnée noterait le zèle des contributeurs, pas l'intérêt des lieux.
        for value in (None, 0):
            place = make_place("Un jardin", pageviews_per_month=value)
            self.assertEqual(
                score_breakdown(place, self._config(16))["consultations"], 0.0)

    def test_ten_times_the_views_is_not_ten_times_the_score(self):
        # L'écart qui compte est entre le jardin qu'on ignore et celui qu'on
        # cherche, pas entre le Luxembourg et Versailles.
        config = self._config(16)
        petit = score_breakdown(make_place("A", pageviews_per_month=500), config)
        grand = score_breakdown(make_place("B", pageviews_per_month=5_000), config)
        self.assertLess(grand["consultations"], petit["consultations"] * 4)
        self.assertGreater(grand["consultations"], petit["consultations"])

    def test_a_spike_does_not_decide(self):
        # Un lieu qui passe au journal télévisé gagne un pic. La médiane décrit
        # le mois ordinaire ; la moyenne aurait retenu l'actualité.
        client = _FakeViews([100, 120, 110, 90, 130, 100,
                             115, 105, 95, 125, 108, 40_000])
        self.assertEqual(client.pageviews("Un lieu"), 109)

    def test_no_recorded_view_is_unknown_not_zero(self):
        # 404 : l'article existe peut-être, mais rien n'est enregistré. Le
        # traiter comme zéro le pénaliserait pour un trou de données.
        self.assertIsNone(_FakeViews(None, status=404).pageviews("Un lieu"))


class _FakeViews(WikipediaClient):
    """Un client qui ne sort pas sur le réseau, pour éprouver la médiane."""

    class _Response:
        def __init__(self, counts, status):
            self._counts, self.status_code = counts, status

        def raise_for_status(self):
            return None

        def json(self):
            return {"items": [{"views": v} for v in self._counts or []]}

    class _Session:
        def __init__(self, counts, status):
            self._counts, self._status = counts, status

        def get(self, url, timeout=None):
            return _FakeViews._Response(self._counts, self._status)

    def __init__(self, counts, status=200):
        super().__init__(min_interval_s=0)
        self._session = self._Session(counts, status)


class TestThinDepartements(unittest.TestCase):
    """Le plancher mesure la documentation, très inégalement répartie.

    La Creuse gardait un lieu sur seize, les Ardennes trois sur vingt-neuf,
    pendant que Paris en gardait deux cent dix-huit. Ce que le plancher écartait
    n'était pas du remplissage : le château d'Oiron, les boiseries de
    Moutier-d'Ahun, les Pierres Jaumâtres.
    """

    @staticmethod
    def _lieu(nom, dept, sitelinks, score=50.0, **kwargs):
        place = make_place(nom, theme="chateaux", sitelinks=sitelinks,
                           departement_code=dept,
                           wikidata_id=f"Q{abs(hash(nom)) % 999999}", **kwargs)
        place.score = score
        return place

    def _repecher(self, au_dessus, sous_le_plancher, cible=12):
        essai = replace(CONFIG, collections=replace(CONFIG.collections,
                                                    min_per_departement=cible))
        with _capture():
            return rescue_thin_departements(au_dessus, sous_le_plancher, essai)

    def test_a_thin_departement_gets_its_best_candidates_back(self):
        au_dessus = [self._lieu("Gardé", "23", 20, 90.0, lat=46.0, lon=2.0)]
        sous = [self._lieu("Moutier-d Ahun", "23", 4, 71.0, lat=46.3, lon=2.1),
                self._lieu("Pierres Jaumâtres", "23", 3, 60.0, lat=46.4, lon=2.2)]
        repeches = self._repecher(au_dessus, sous)
        self.assertEqual(len(repeches), 3)
        self.assertTrue(all(p.geo_rescued for p in sous))

    def test_a_rich_departement_gets_nothing(self):
        # La Dordogne compte soixante-quatre lieux : la tour de Vésone, sous son
        # plancher, n y sera pas repêchée. Le mécanisme corrige la géographie,
        # pas les planchers.
        au_dessus = [self._lieu(f"Château {i}", "24", 20, 90.0, lat=45 + i * 0.01)
                     for i in range(12)]
        vesone = self._lieu("Tour de Vésone", "24", 4, 73.0, lat=45.18, lon=0.7)
        repeches = self._repecher(au_dessus, [vesone])
        self.assertEqual(len(repeches), 12)
        self.assertFalse(vesone.geo_rescued)

    def test_a_twin_that_dedupe_will_remove_does_not_count_as_a_place(self):
        # Le défaut trouvé en Ardennes et en Val-de-Marne : « château-bas de
        # Sedan » à 143 m du « château de Sedan », tous deux au-dessus du
        # plancher. Le comptage voyait douze lieux, le dédoublonnage en retirait
        # un juste après, et le département finissait à onze sans que rien ne
        # le dise. Le comptage doit donc porter sur une population déjà
        # dédoublonnée.
        catalogue = [
            self._lieu(f"Château {i}", "08", 20, 90.0, lat=49.0 + i * 0.01, lon=4.9)
            for i in range(10)
        ]
        sedan = self._lieu("Château de Sedan", "08", 20, 101.0,
                           lat=49.7020, lon=4.9430)
        sosie = self._lieu("Château-bas de Sedan", "08", 20, 76.9,
                           lat=49.7031, lon=4.9430)
        candidat = self._lieu("Sous le plancher", "08", 3, 70.0,
                              lat=49.5, lon=4.5)
        # Douze fiches, mais onze lieux : le sosie part au dédoublonnage.
        propre = dedupe(catalogue + [sedan, sosie])
        self.assertEqual(len(propre), 11)
        repeches = self._repecher(propre, [candidat])
        self.assertEqual(len(repeches), 12)
        self.assertIn("Sous le plancher", {p.name for p in repeches})

    def test_no_theme_takes_over_a_departement(self):
        # Le premier jet donnait sept châteaux sur douze en Seine-Saint-Denis.
        # Un « meilleur de » qui n'est qu'une liste de châteaux ne donne envie
        # d'aucun des douze.
        au_dessus = [self._lieu("Déjà là", "93", 20, 90.0, lat=48.0, lon=2.5)]
        sous = []
        for i in range(9):  # neuf châteaux, tous mieux notés que le reste
            sous.append(self._lieu(f"Château {i}", "93", 4, 80.0 - i,
                                   lat=48.1 + i * 0.02, lon=2.5))
        for i in range(9):
            place = self._lieu(f"Jardin {i}", "93", 4, 60.0 - i,
                               lat=48.5 + i * 0.02, lon=2.5)
            place.theme_id = "jardins"
            sous.append(place)
        repeches = self._repecher(au_dessus, sous)
        self.assertEqual(len(repeches), 12)
        themes = Counter(p.theme_id for p in repeches if p.geo_rescued)
        # Sans quota, les neuf châteaux — tous mieux notés — prenaient neuf des
        # onze places. Le plafond monte d'un cran à la fois : les deux thèmes
        # se partagent le département à une unité près.
        self.assertLessEqual(abs(themes["chateaux"] - themes["jardins"]), 1)
        self.assertGreaterEqual(themes["jardins"], 5)

    def test_the_theme_quota_never_leaves_a_departement_short(self):
        # Si le département n'a vraiment que des châteaux, mieux vaut sept
        # châteaux qu'un département à neuf lieux. Le second passage lève le
        # plafond — c'est la règle du quota géographique des collections
        # nationales, appliquée aux thèmes.
        au_dessus = [self._lieu("Déjà là", "90", 20, 90.0, lat=47.6, lon=6.8)]
        sous = [self._lieu(f"Château {i}", "90", 4, 80.0 - i,
                           lat=47.6 + i * 0.02, lon=6.9) for i in range(15)]
        repeches = self._repecher(au_dessus, sous)
        self.assertEqual(len(repeches), 12)

    def test_a_second_wikidata_entry_for_the_same_site_is_refused(self):
        # « Abbaye royale de Saint-Denis » à vingt mètres de « basilique
        # Saint-Denis » : le dédoublonnage ne les voit pas, il ne compare qu à
        # l intérieur d un thème.
        basilique = self._lieu("Basilique Saint-Denis", "93", 60, 158.0,
                               lat=48.9358, lon=2.3597)
        sosie = self._lieu("Abbaye royale de Saint-Denis", "93", 4, 96.0,
                           lat=48.9359, lon=2.3598)
        loin = self._lieu("Fort d Aubervilliers", "93", 3, 73.0, lat=48.91, lon=2.40)
        noms = {p.name for p in self._repecher([basilique], [sosie, loin])}
        self.assertNotIn("Abbaye royale de Saint-Denis", noms)
        self.assertIn("Fort d Aubervilliers", noms)

    def test_the_target_is_a_ceiling_not_a_quota(self):
        # On complète jusqu à la cible, jamais au-delà : le repêchage comble un
        # trou, il ne fabrique pas un catalogue.
        au_dessus = [self._lieu(f"Gardé {i}", "23", 20, 90.0, lat=46 + i * 0.02)
                     for i in range(10)]
        sous = [self._lieu(f"Repêchable {i}", "23", 3, 80.0 - i, lat=47 + i * 0.02)
                for i in range(8)]
        repeches = self._repecher(au_dessus, sous, cible=12)
        self.assertEqual(len(repeches), 12)
        self.assertEqual({p.name for p in repeches if p.geo_rescued},
                         {"Repêchable 0", "Repêchable 1"})

    def test_a_target_of_zero_disables_it(self):
        au_dessus = [self._lieu("Gardé", "23", 20)]
        sous = [self._lieu("Sous le plancher", "23", 3)]
        self.assertEqual(self._repecher(au_dessus, sous, cible=0), au_dessus)


class TestPin(unittest.TestCase):
    """`places.csv` désigne les lieux à ALLER CHERCHER, et n'est lu que par
    `fetch`. Y inscrire un lieu déjà collecté ne produit rien tant qu'on ne
    relance pas une demi-heure de collecte : le drapeau vit dans `data/raw/`.
    """

    def _run(self, brut, qid, **extra):
        with tempfile.TemporaryDirectory() as tmp:
            racine = Path(tmp)
            (racine / "raw").mkdir()
            (racine / "manual").mkdir()
            write_raw(racine / "raw", brut, {p.theme_id for p in brut})
            args = argparse.Namespace(
                raw=racine / "raw", manual=racine / "manual", wikidata_id=qid,
                theme=extra.get("theme"), note=extra.get("note"),
                clear=extra.get("clear", False))
            sortie = StringIO()
            with contextlib.redirect_stdout(sortie):
                code = cmd_pin(args, CONFIG)
            relu = read_raw(racine / "raw")
            liste = racine / "manual" / "places.csv"
            return code, sortie.getvalue(), relu, (
                liste.read_text(encoding="utf-8") if liste.exists() else "")

    def test_pinning_keeps_the_place_in_the_collection(self):
        # Le lieu change de FICHIER en étant épinglé — c'est la règle de
        # `shard_of`. Ne réécrire que les thèmes le retirait du sien sans
        # jamais l'écrire ailleurs : il disparaissait de la collecte.
        brut = [make_place(f"Sommet {i}", theme="sommets", wikidata_id=f"Q{i}")
                for i in range(5)]
        code, _texte, relu, liste = self._run(brut, "Q2")
        self.assertEqual(code, 0)
        self.assertEqual(len(relu), 5)
        vise = [p for p in relu if p.wikidata_id == "Q2"]
        self.assertEqual([p.pinned for p in vise], [True])
        self.assertIn("Q2", liste)

    def test_an_unknown_place_is_refused(self):
        brut = [make_place("Sommet", theme="sommets", wikidata_id="Q1")]
        code, texte, _relu, _liste = self._run(brut, "Q404")
        self.assertEqual(code, 1)

    def test_clearing_gives_the_flag_back(self):
        brut = [make_place("Sommet", theme="sommets", wikidata_id="Q1")]
        with tempfile.TemporaryDirectory() as tmp:
            racine = Path(tmp)
            (racine / "raw").mkdir()
            (racine / "manual").mkdir()
            write_raw(racine / "raw", brut, {"sommets"})
            base = argparse.Namespace(raw=racine / "raw", manual=racine / "manual",
                                      wikidata_id="Q1", theme=None, note=None)
            with contextlib.redirect_stdout(StringIO()):
                cmd_pin(argparse.Namespace(**vars(base), clear=False), CONFIG)
                cmd_pin(argparse.Namespace(**vars(base), clear=True), CONFIG)
            relu = read_raw(racine / "raw")
        self.assertEqual(len(relu), 1)
        self.assertFalse(relu[0].pinned)


class TestListOnlyThemes(unittest.TestCase):
    """Pour un thème nourri par des listes, la liste EST le critère.

    Amélie-les-Bains avait été saisie par erreur parmi les Plus Beaux Détours.
    Effacer sa ligne du CSV lui retirait son label, mais elle restait au
    catalogue : cinq versions linguistiques, et le plancher du thème est à
    trois. Elle devenait un « village de caractère » que personne n'avait
    choisi.
    """

    def _garder(self, lieux):
        from roam_pipeline.collections import apply_list_membership
        with _capture():
            return {p.name for p in apply_list_membership(lieux, CONFIG)}

    def _village(self, nom, labels=(), sitelinks=30, **extra):
        place = make_place(nom, theme="villages", sitelinks=sitelinks,
                           wikidata_id=f"Q{abs(hash(nom)) % 999961}", **extra)
        place.labels = list(labels)
        return place

    def test_a_place_off_every_list_is_dropped(self):
        dedans = self._village("Gordes", labels=["plus-beaux-villages"])
        dehors = self._village("Amélie-les-Bains", labels=[])
        self.assertEqual(self._garder([dedans, dehors]), {"Gordes"})

    def test_any_of_the_themes_lists_is_enough(self):
        # Le thème « villages » est alimenté par DEUX listes ; l'une suffit.
        detour = self._village("L'Isle-Adam", labels=["plus-beaux-detours"])
        self.assertEqual(self._garder([detour]), {"L'Isle-Adam"})

    def test_a_foreign_label_does_not_count(self):
        # Être Grand Site ne fait pas de vous un Plus Beau Village.
        egare = self._village("Grand Site quelconque", labels=["grand-site-de-france"])
        self.assertEqual(self._garder([egare]), set())

    def test_a_pinned_place_stays(self):
        epingle = self._village("Choisi à la main", labels=[])
        epingle.pinned = True
        self.assertEqual(self._garder([epingle]), {"Choisi à la main"})

    def test_a_theme_with_its_own_classes_is_untouched(self):
        # « chateaux » a des classes Wikidata : la règle ne le concerne pas.
        chateau = make_place("Château sans label", theme="chateaux",
                             wikidata_id="Q1", sitelinks=30)
        from roam_pipeline.collections import apply_list_membership
        with _capture():
            garde = apply_list_membership([chateau], CONFIG)
        self.assertEqual([p.name for p in garde], ["Château sans label"])


class TestRelabelCannotCreatePlaces(unittest.TestCase):
    """`relabel` appose des labels, il ne crée pas de lieux.

    Cent une communes des Plus Beaux Détours ont été saisies, puis
    « relabellisées », et n'ont rien produit : le thème « villages » n'a aucune
    classe Wikidata, il n'existe que par ses listes, et seul un `fetch` de ce
    thème va chercher les entités. Le journal ne disait rien.
    """

    def _relabel(self, brut, membres):
        from roam_pipeline.cli import cmd_relabel
        with tempfile.TemporaryDirectory() as tmp:
            racine = Path(tmp)
            for nom in ("raw", "manual", "out"):
                (racine / nom).mkdir()
            write_raw(racine / "raw", brut, {p.theme_id for p in brut})
            (racine / "out" / "places_raw.json").write_text(
                json.dumps([p.to_dict() for p in brut], ensure_ascii=False),
                encoding="utf-8")
            args = argparse.Namespace(raw=racine / "raw", manual=racine / "manual",
                                      out=racine / "out")
            with _capture() as sortie:
                with unittest.mock.patch("roam_pipeline.cli.wd.SparqlClient"), \
                     unittest.mock.patch("roam_pipeline.cli.fetch_label_members",
                                         side_effect=lambda _c, l, _m: membres.get(l.id, set())):
                    cmd_relabel(args, CONFIG)
            return sortie.getvalue()

    def test_a_member_absent_from_the_collection_is_announced(self):
        brut = [make_place("Gordes", theme="villages", wikidata_id="Q1")]
        texte = self._relabel(brut, {"plus-beaux-detours": {"Q911450", "Q6381"}})
        self.assertIn("ne sont PAS dans la collecte", texte)
        self.assertIn("fetch --only villages", texte)

    def test_nothing_is_said_when_every_member_is_there(self):
        brut = [make_place("L'Isle-Adam", theme="villages", wikidata_id="Q911450")]
        texte = self._relabel(brut, {"plus-beaux-detours": {"Q911450"}})
        self.assertNotIn("ne sont PAS dans la collecte", texte)


class TestSilentLabels(unittest.TestCase):
    """Un label qui ne rend rien ne doit pas ne rien dire.

    « Les Plus Beaux Détours de France » est configuré depuis le premier jour,
    alimente le thème « villages » et attendait toujours son fichier : cent
    quatre communes que le catalogue ne pouvait pas voir — L'Isle-Adam,
    Beaugency, Meymac — sans qu'une ligne le signale.
    """

    def test_a_label_without_members_is_announced(self):
        from roam_pipeline.collections import build_label_collections

        lieux = [make_place(f"Château {i}", theme="chateaux", wikidata_id=f"Q{i}")
                 for i in range(12)]
        with self.assertLogs("roam_pipeline.collections", level="WARNING") as logs:
            build_label_collections(lieux, CONFIG)
        texte = "\n".join(logs.output)
        self.assertIn("sans aucun membre", texte)
        self.assertIn("plus-beaux-detours", texte)

    def test_a_label_with_members_is_not_announced(self):
        from roam_pipeline.collections import build_label_collections

        lieux = []
        for i in range(12):
            place = make_place(f"Village {i}", theme="villages", wikidata_id=f"Q{i}",
                               sitelinks=20)
            place.labels = ["plus-beaux-detours"]
            lieux.append(place)
        with _capture():
            faites = build_label_collections(lieux, CONFIG)
        self.assertIn("label-plus-beaux-detours", {c.slug for c in faites})


class TestLabelCasings(unittest.TestCase):
    """Wikidata écrit « forêt de Fontainebleau » sans majuscule.

    Un massif forestier est un nom commun. La comparaison de libellé se fait au
    caractère près, majuscule comprise : quarante-quatre graphies des seize
    Forêts d'Exception ont rendu ZÉRO, alors que Fontainebleau y est avec
    vingt-huit versions linguistiques et la bonne classe.
    """

    def test_both_casings_are_asked(self):
        formes = wd.label_casings("Forêt de Fontainebleau")
        self.assertIn("Forêt de Fontainebleau", formes)
        self.assertIn("forêt de Fontainebleau", formes)

    def test_a_lowercase_name_also_gets_its_capital(self):
        formes = wd.label_casings("forêt de Bercé")
        self.assertIn("Forêt de Bercé", formes)

    def test_no_duplicate_when_the_case_does_not_change(self):
        # « L'Isle-Adam » ne produit qu'une forme utile de plus, pas trois.
        self.assertEqual(len(wd.label_casings("Étretat")), 2)
        self.assertEqual(wd.label_casings(""), [])

    def test_only_the_first_letter_moves(self):
        # « Val-d'Oise » ne doit pas devenir « val-d'oise » : le reste du nom
        # est intact, et c'est ce qui garde la comparaison exacte.
        self.assertEqual(wd.label_casings("Val Suzon"),
                         ["Val Suzon", "val Suzon"])

    def test_the_query_carries_every_form(self):
        requete = wd.label_lookup_query(["Forêt de Bercé"], "Q4421")
        self.assertIn('"Forêt de Bercé"@fr', requete)
        self.assertIn('"forêt de Bercé"@fr', requete)


class TestLabelQueryKinds(unittest.TestCase):
    """Toute liste utile n'est pas une désignation patrimoniale.

    Le Centre des monuments nationaux (Q2945551) est un établissement public :
    il ne DÉSIGNE pas ses monuments, il les gère. Une sonde qui ne teste que
    P1435, P463 et P31 rend zéro partout et conclut « à saisir à la main »,
    alors que Wikidata porte l'information sous une autre propriété.
    """

    def test_the_five_shapes_build_a_query(self):
        for kind in ("heritage", "member_of", "instance", "operator", "owner"):
            with self.subTest(kind):
                requete = wd.label_members_query(kind, "Q2945551")
                self.assertIn("wd:Q2945551", requete)
                self.assertIn("SELECT DISTINCT ?item", requete)

    def test_each_shape_asks_a_different_property(self):
        proprietes = set()
        for kind in ("heritage", "member_of", "instance", "operator", "owner"):
            ligne = next(l for l in wd.label_members_query(kind, "Q2945551").splitlines()
                         if "wd:Q2945551" in l)
            proprietes.add(ligne.strip())
        self.assertEqual(len(proprietes), 5)

    def test_an_unknown_shape_is_refused(self):
        # Se tromper de nom ne doit pas rendre une requête vide en silence :
        # elle donnerait zéro membre et on chercherait ailleurs pendant une
        # demi-heure de collecte.
        with self.assertRaises(ValueError):
            wd.label_members_query("exploitant", "Q2945551")


class TestThemeCap(unittest.TestCase):
    """Combien de lieux d'un thème le CATALOGUE montre, tous territoires confondus.

    La collection « Cathédrales et basiliques » en montrait soixante et une,
    mais le catalogue en portait cent quatre-vingt-treize : les cent
    trente-deux autres vivaient dans les collections départementales et
    s'affichaient toutes sur la carte.
    """

    def _lieu(self, nom, theme, score, dept, **extra):
        return make_place(nom, theme=theme, score=score, departement_code=dept,
                          wikidata_id=f"Q{abs(hash(nom)) % 999979}", **extra)

    def _cape(self, lieux, cap=5, mini=1):
        from roam_pipeline.collections import apply_theme_cap
        themes = [replace(t, catalogue_cap=cap if t.id == "cathedrales" else None)
                  for t in CONFIG.themes]
        config = replace(CONFIG, themes=themes,
                         collections=replace(CONFIG.collections, min_per_region=mini))
        with _capture():
            return apply_theme_cap(lieux, config)

    def test_only_the_best_survive(self):
        lieux = [self._lieu(f"Cathédrale {i}", "cathedrales", 100 - i, "75")
                 for i in range(9)]
        gardes = self._cape(lieux, mini=0)
        self.assertEqual(len(gardes), 5)
        self.assertEqual({p.name for p in gardes},
                         {f"Cathédrale {i}" for i in range(5)})

    def test_a_theme_without_a_cap_is_untouched(self):
        lieux = [self._lieu(f"Château {i}", "chateaux", 100 - i, "75")
                 for i in range(20)]
        self.assertEqual(len(self._cape(lieux)), 20)

    def test_every_region_keeps_at_least_one(self):
        # Les quatre cathédrales des DOM sont seules dans leur région : jamais
        # dans les meilleures de France, donc emportées d'un bloc sans minimum.
        metropole = [self._lieu(f"Métropole {i}", "cathedrales", 200 - i, "75")
                     for i in range(5)]
        outremer = self._lieu("Cathédrale de Cayenne", "cathedrales", 40, "973")
        gardes = self._cape(metropole + [outremer])
        self.assertIn("Cathédrale de Cayenne", {p.name for p in gardes})
        self.assertEqual(len(gardes), 5)

    def test_without_the_minimum_the_overseas_falls(self):
        metropole = [self._lieu(f"Métropole {i}", "cathedrales", 200 - i, "75")
                     for i in range(5)]
        outremer = self._lieu("Cathédrale de Cayenne", "cathedrales", 40, "973")
        gardes = self._cape(metropole + [outremer], mini=0)
        self.assertNotIn("Cathédrale de Cayenne", {p.name for p in gardes})

    def test_an_official_list_is_reserved_before_the_score(self):
        # Les 187 Plus Beaux Villages SONT la liste de l'association : un
        # plafond qui coupe dedans coupe dans la curation humaine.
        gros = [self._lieu(f"Cathédrale {i}", "cathedrales", 200 - i, "75")
                for i in range(5)]
        petite = self._lieu("Basilique labellisée", "cathedrales", 10, "75",
                            labels=["unesco"])
        gardes = self._cape(gros + [petite], mini=0)
        self.assertIn("Basilique labellisée", {p.name for p in gardes})

    def test_a_pinned_place_comes_first_of_all(self):
        gros = [self._lieu(f"Cathédrale {i}", "cathedrales", 200 - i, "75")
                for i in range(5)]
        epingle = self._lieu("Choisie à la main", "cathedrales", 5, "75")
        epingle.pinned = True
        gardes = self._cape(gros + [epingle], mini=0)
        self.assertIn("Choisie à la main", {p.name for p in gardes})

    def test_a_review_keep_is_not_a_free_pass(self):
        # `keep` pose le même drapeau qu'un épinglage à la main, et il y en a
        # 1555 : les compter comme des dispenses remplissait le plafond avant
        # qu'une seule région n'ait eu sa part. « Si c'est juste un keep mais
        # que ce dernier se situe à la fin du classement c'est normal qu'il
        # sorte. »
        lieux = [self._lieu(f"Cathédrale {i}", "cathedrales", 100 - i, "75")
                 for i in range(9)]
        for place in lieux:
            place.pinned = True
            place.kept_in_review = True
        gardes = self._cape(lieux, mini=0)
        self.assertEqual(len(gardes), 5)
        self.assertEqual({p.name for p in gardes},
                         {f"Cathédrale {i}" for i in range(5)})

    def test_the_review_hierarchy_ranks_before_the_score(self):
        # Le tri du plafond suit la hiérarchie que le curateur a construite :
        # un lieu qu'il a MONTÉ d'un niveau passe devant un mieux documenté
        # qu'il n'a pas touché, et un lieu qu'il a DESCENDU sort le premier.
        lieux = [self._lieu(f"Cathédrale {i}", "cathedrales", 100 - i, "75")
                 for i in range(6)]
        monte = self._lieu("Remontée en revue", "cathedrales", 10, "75")
        monte.tier_shift = -1
        lieux[0].tier_shift = 1  # la mieux notée, mais descendue d'un niveau
        gardes = {p.name for p in self._cape(lieux + [monte], cap=5, mini=0)}
        self.assertIn("Remontée en revue", gardes)
        self.assertNotIn("Cathédrale 0", gardes)

    def test_the_cap_has_the_last_word_over_the_rescue(self):
        # Placé avant le repêchage géographique, le plafond était défait : le
        # repêchage remontait des cathédrales restées sous le plancher pour
        # combler des départements pauvres, et 80 redevenaient 97.
        from roam_pipeline.collections import build_all
        themes = [replace(t, catalogue_cap=3) if t.id == "cathedrales" else t
                  for t in CONFIG.themes]
        config = replace(CONFIG, themes=themes)
        lieux = []
        for i in range(20):
            place = make_place(f"Cathédrale {i}", theme="cathedrales",
                               wikidata_id=f"QC{i}", sitelinks=20 if i < 10 else 1,
                               lat=43 + i / 20, lon=1 + i / 20)
            place.departement_code, place.region_code = "34", "76"
            lieux.append(place)
        with _capture():
            retenus, _cols = build_all(lieux, config)
        self.assertLessEqual(
            sum(1 for p in retenus if p.theme_id == "cathedrales"), 3)

    def test_a_theme_under_its_cap_loses_nothing(self):
        lieux = [self._lieu(f"Cathédrale {i}", "cathedrales", 100 - i, "75")
                 for i in range(3)]
        self.assertEqual(len(self._cape(lieux)), 3)

    def test_the_cap_is_applied_again_after_the_rescue(self):
        # Le repêchage n'a pas de budget : appelé sur un thème qui a de la place
        # — neuf musées partis en doublons en laissent — il ajoutait sans
        # compter, et cent cinquante musées devenaient cent soixante-huit. Le
        # plafond repasse donc APRÈS lui.
        #
        # Il ne peut pas remplacer le premier passage pour autant : appliqué
        # seul après, il vidait les départements que le repêchage venait de
        # remplir. Les deux ensemble laissent le repêchage garnir les
        # départements pauvres sans que le thème dépasse son compte.
        trop = [self._lieu(f"Cathédrale {i}", "cathedrales", 100 - i, "75")
                for i in range(9)]
        self.assertEqual(len(self._cape(trop, mini=0)), 5)

    def test_a_saturated_theme_is_closed_to_the_rescue(self):
        # Le repêchage comble un TERRITOIRE pauvre ; il n'a pas à rouvrir un
        # quota fermé. Sans cette liste, quatre-vingts cathédrales redevenaient
        # quatre-vingt-dix-sept.
        from roam_pipeline.collections import saturated_themes
        themes = [replace(t, catalogue_cap=5 if t.id == "cathedrales" else None)
                  for t in CONFIG.themes]
        config = replace(CONFIG, themes=themes)
        pleines = [self._lieu(f"Cathédrale {i}", "cathedrales", 100, "75")
                   for i in range(5)]
        self.assertEqual(saturated_themes(pleines, config), {"cathedrales"})
        self.assertEqual(saturated_themes(pleines[:4], config), set())


class TestCommuneCap(unittest.TestCase):
    """Paris comptait 162 lieux, Marseille — la deuxième ville — 21.

    Sur 135 jardins français, 51 étaient parisiens ; la commune suivante en
    avait quatre. Le plancher mesure la documentation, et un square parisien a
    un article de Wikipédia là où un beau jardin du Gers n'en a pas.
    """

    def _lieu(self, nom, theme, score, commune, code):
        return make_place(nom, theme=theme, score=score, commune_name=commune,
                          commune_code=code, wikidata_id=f"Q{abs(hash(nom)) % 999983}")

    def _cape(self, lieux, cap=6):
        from roam_pipeline.collections import apply_commune_cap
        config = replace(CONFIG,
                         collections=replace(CONFIG.collections, max_per_commune=cap))
        with _capture():
            return apply_commune_cap(lieux, config)

    def test_only_the_best_of_a_theme_survive_in_one_commune(self):
        lieux = [self._lieu(f"Square {i}", "jardins", 100 - i, "Paris", "75104")
                 for i in range(10)]
        gardes = self._cape(lieux)
        self.assertEqual(len(gardes), 6)
        self.assertEqual({p.name for p in gardes},
                         {f"Square {i}" for i in range(6)})

    def test_the_cap_is_per_theme_not_per_commune(self):
        # Un simple « les N meilleurs de Paris » garderait le musée Grévin et
        # jetterait la Sainte-Chapelle : les musées écrasent tout au score.
        musees = [self._lieu(f"Musée {i}", "musees", 150 - i, "Paris", "75101")
                  for i in range(8)]
        chapelle = self._lieu("Sainte-Chapelle", "monuments", 129, "Paris", "75101")
        gardes = self._cape(musees + [chapelle])
        self.assertIn("Sainte-Chapelle", {p.name for p in gardes})
        self.assertEqual(sum(1 for p in gardes if p.theme_id == "musees"), 6)

    def test_the_arrondissements_are_one_city(self):
        # 75101 à 75120 sont les arrondissements de Paris. Un plafond posé sur
        # le code de commune s'y appliquait vingt fois et laissait passer vingt
        # fois trop — personne ne pense « j'ai fait le 5e », on fait Paris.
        lieux = [self._lieu(f"Jardin {i}", "jardins", 100 - i, "Paris",
                            f"751{1 + i // 2:02d}") for i in range(10)]
        self.assertEqual(len(self._cape(lieux)), 6)

    def test_lyon_and_marseille_too(self):
        for ville, codes in (("Lyon", ["69381", "69385", "69387"]),
                             ("Marseille", ["13201", "13208", "13212"])):
            with self.subTest(ville):
                lieux = [self._lieu(f"{ville} {i}", "musees", 100 - i, ville,
                                    codes[i % 3]) for i in range(9)]
                self.assertEqual(len(self._cape(lieux)), 6)

    def test_two_communes_each_get_their_share(self):
        paris = [self._lieu(f"Paris {i}", "musees", 100 - i, "Paris", "75101")
                 for i in range(8)]
        lille = [self._lieu(f"Lille {i}", "musees", 90 - i, "Lille", "59350")
                 for i in range(3)]
        self.assertEqual(len(self._cape(paris + lille)), 9)

    def test_a_hand_pinned_place_passes_over_the_cap(self):
        # Une ligne de places.csv est un lieu que le curateur a ajouté lui-même :
        # le plafond n'a pas à défaire ce geste.
        lieux = [self._lieu(f"Musée {i}", "musees", 100 - i, "Paris", "75101")
                 for i in range(8)]
        lieux[-1].pinned = True
        gardes = self._cape(lieux)
        self.assertIn("Musée 7", {p.name for p in gardes})
        self.assertEqual(len(gardes), 6)

    def test_a_review_keep_does_not_pass_over_the_cap(self):
        # Ici aussi `keep` cessait d'être un verdict pour devenir un bouclier :
        # les 1555 lieux gardés en revue remplissaient le plafond à eux seuls.
        lieux = [self._lieu(f"Musée {i}", "musees", 100 - i, "Paris", "75101")
                 for i in range(8)]
        for place in lieux:
            place.pinned = True
            place.kept_in_review = True
        gardes = self._cape(lieux)
        self.assertEqual({p.name for p in gardes},
                         {f"Musée {i}" for i in range(6)})

    def test_the_review_hierarchy_ranks_before_the_score(self):
        lieux = [self._lieu(f"Musée {i}", "musees", 100 - i, "Paris", "75101")
                 for i in range(7)]
        lieux[0].tier_shift = 1   # la mieux notée, mais descendue en revue
        lieux[-1].tier_shift = -1  # la moins notée, mais remontée
        gardes = {p.name for p in self._cape(lieux)}
        self.assertIn("Musée 6", gardes)
        self.assertNotIn("Musée 0", gardes)

    def test_a_place_without_a_commune_is_never_cut(self):
        # Un phare en mer n'a pas de commune : le plafond ne peut rien en dire.
        phares = [make_place(f"Phare {i}", theme="phares", score=50,
                             commune_code=None, wikidata_id=f"Q{900 + i}")
                  for i in range(10)]
        self.assertEqual(len(self._cape(phares)), 10)

    def test_a_cap_of_zero_disables_it(self):
        lieux = [self._lieu(f"Musée {i}", "musees", 100 - i, "Paris", "75101")
                 for i in range(9)]
        self.assertEqual(len(self._cape(lieux, cap=0)), 9)


class TestFantomes(unittest.TestCase):
    """Un lieu qu'on ne peut pas visiter est l'échec le plus coûteux : il
    envoie quelqu'un faire la route pour rien.

    Trois sont passés en revue sans être vus. Une revue à plat demande de lire
    deux mille quatre cents fiches ; ceux-là se disent eux-mêmes, dans leur
    propre résumé.
    """

    def _cherche(self, resume, nom="Un lieu"):
        place = make_place(nom, "chateaux", wikidata_id="Q1", summary=resume)
        return [m for _p, motifs in fantomes([place]) for m in motifs]

    def test_the_three_that_slipped_through_are_caught(self):
        cas = {
            "Tour du Temple":
                "La tour du Temple et son enclos constituaient la maison du "
                "Temple, ancienne forteresse parisienne située dans le nord du "
                "Marais, qui fut détruite en 1808.",
            "Château de Madrid":
                "Construit à partir de 1528 sur l'ordre du roi de France "
                "François Ier et achevé pour son fils Henri II, il est "
                "entièrement démoli à la fin du XVIIIe siècle.",
            "Portus Itius":
                "Sa localisation exacte est inconnue mais il se situerait "
                "probablement à Saint-Omer ou dans ses environs.",
        }
        for nom, resume in cas.items():
            with self.subTest(nom):
                self.assertTrue(self._cherche(resume, nom), nom)

    def test_a_ruin_is_not_a_ghost(self):
        # Le pont d'Avignon n'a plus que quatre de ses vingt-deux arches, et
        # c'est l'un des lieux les plus visités de France. Un filet large le
        # ramènerait, avec toutes les ruines du pays.
        self.assertEqual(self._cherche(
            "Il ne reste aujourd'hui que quatre arches sur les vingt-deux "
            "que comptait le pont.", "Pont d'Avignon"), [])

    def test_a_destruction_that_happened_elsewhere_is_not_a_ghost(self):
        # La chartreuse de Molsheim existe et abrite un musée ; c'est celle de
        # Koenigshoffen qui fut détruite, mentionnée en passant.
        self.assertEqual(self._cherche(
            "La chartreuse de Molsheim est un ancien monastère situé au cœur "
            "de la ville. La destruction de la chartreuse de Koenigshoffen "
            "conduisit la communauté à s'y réfugier.", "Chartreuse"), [])

    def test_a_place_without_a_summary_is_silent(self):
        place = make_place("Sans résumé", "chateaux", wikidata_id="Q1")
        self.assertEqual(fantomes([place]), [])

    def test_the_loudest_comes_first(self):
        # Un fantôme notoire siège haut dans les collections : c'est celui qu'il
        # faut voir en premier.
        petit = make_place("Petit", "chateaux", wikidata_id="Q1", score=10,
                           summary="Il fut détruit en 1900.")
        grand = make_place("Grand", "chateaux", wikidata_id="Q2", score=200,
                           summary="Il fut démoli en 1808.")
        self.assertEqual([p.name for p, _ in fantomes([petit, grand])],
                         ["Grand", "Petit"])


class TestExclusionSentinel(unittest.TestCase):
    """« Vérifié, rien à redire » et « jamais vérifié » ne sont pas la même
    chose, et rien ne les distinguait.

    Les deux sont fausses pour qui lit le drapeau, donc les deux laissent
    passer. Mais la première doit survivre au report d'une collecte à l'autre,
    et la seconde doit pouvoir être complétée par ce que le dépôt sait déjà.
    """

    def test_a_clean_place_is_marked_as_checked_not_as_unknown(self):
        from roam_pipeline.fetch import enrich_exclusions

        class _Muet:
            def query(self, _q):
                return []

        place = make_place("Cathédrale d'Amiens", "cathedrales", wikidata_id="Q1")
        self.assertIsNone(place.excluded_class)
        with _capture():
            enrich_exclusions(_Muet(), [place], ["Q194195"])
        self.assertEqual(place.excluded_class, "")
        # Et le drapeau reste faux : le lieu n'est pas écarté.
        self.assertFalse(place.excluded_class)

    def test_an_empty_class_list_leaves_everything_untouched(self):
        from roam_pipeline.fetch import enrich_exclusions

        place = make_place("Gordes", "villages", wikidata_id="Q1",
                           excluded_class="parc animalier")
        with _capture():
            self.assertEqual(enrich_exclusions(None, [place], []), 0)
        # La liste vide rend le catalogue à lui-même : plus aucune exclusion.
        self.assertEqual(place.excluded_class, "")


class TestVerdict(unittest.TestCase):
    """Écarter un lieu repéré au détour d'une carte ne doit pas demander nano.

    `decisions.csv` est la mémoire de la curation, et seule la page de revue
    savait y écrire. Portus Itius — un port de la Manche dont la localisation
    est inconnue, que Wikidata place à cent quatre-vingts kilomètres dans les
    terres — trônait au septième rang du niveau 1 du Val-d'Oise.
    """

    def _run(self, brut, qid, decision="drop", **extra):
        with tempfile.TemporaryDirectory() as tmp:
            racine = Path(tmp)
            (racine / "raw").mkdir()
            (racine / "manual").mkdir()
            write_raw(racine / "raw", brut, {p.theme_id for p in brut})
            args = argparse.Namespace(
                raw=racine / "raw", manual=racine / "manual", wikidata_id=qid,
                decision=decision, note=extra.get("note"),
                clear=extra.get("clear", False))
            sortie = StringIO()
            with contextlib.redirect_stdout(sortie):
                with _capture():
                    code = cmd_verdict(args, CONFIG)
            chemin = racine / "manual" / "decisions.csv"
            # Le dossier temporaire disparaît à la sortie du bloc : on relit
            # tout ici, sinon l'assertion porte sur un fichier effacé.
            brut_csv = chemin.read_text(encoding="utf-8") if chemin.exists() else ""
            return code, sortie.getvalue(), read_decisions(chemin), brut_csv

    def test_a_drop_is_written_with_its_reason(self):
        brut = [make_place("Portus Itius", theme="megalithes", wikidata_id="Q2611105")]
        code, _texte, decisions, _csv = self._run(
            brut, "Q2611105", note="localisation inconnue")
        self.assertEqual(code, 0)
        self.assertEqual(decisions["Q2611105"], ("drop", "localisation inconnue"))

    def test_the_name_travels_with_the_verdict(self):
        # Sans lui, revenir sur un verdict demande d'aller chercher ce que
        # « Q2611105 » désigne.
        brut = [make_place("Portus Itius", theme="megalithes", wikidata_id="Q2611105")]
        _code, _texte, _decisions, csv_brut = self._run(brut, "Q2611105")
        self.assertIn("Portus Itius", csv_brut)

    def test_an_unknown_place_is_refused(self):
        # Presque toujours une faute de frappe sur l'identifiant.
        brut = [make_place("Gordes", theme="villages", wikidata_id="Q1")]
        code, _texte, decisions, _csv = self._run(brut, "Q404")
        self.assertEqual(code, 1)
        self.assertEqual(decisions, {})

    def test_an_unknown_verdict_is_refused(self):
        brut = [make_place("Gordes", theme="villages", wikidata_id="Q1")]
        code, _texte, decisions, _csv = self._run(brut, "Q1", decision="supprime")
        self.assertEqual(code, 1)
        self.assertEqual(decisions, {})

    def test_clearing_gives_the_place_back_to_the_automatic_rules(self):
        brut = [make_place("Gordes", theme="villages", wikidata_id="Q1")]
        with tempfile.TemporaryDirectory() as tmp:
            racine = Path(tmp)
            (racine / "raw").mkdir()
            (racine / "manual").mkdir()
            write_raw(racine / "raw", brut, {"villages"})
            base = dict(raw=racine / "raw", manual=racine / "manual",
                        wikidata_id="Q1", note=None)
            with contextlib.redirect_stdout(StringIO()), _capture():
                cmd_verdict(argparse.Namespace(**base, decision="drop", clear=False), CONFIG)
                cmd_verdict(argparse.Namespace(**base, decision="", clear=True), CONFIG)
            self.assertEqual(read_decisions(racine / "manual" / "decisions.csv"), {})

    def test_the_other_verdicts_pass_too(self):
        brut = [make_place("Gordes", theme="villages", wikidata_id="Q1")]
        for verdict in DECISIONS:
            with self.subTest(verdict):
                _code, _t, decisions, _csv = self._run(brut, "Q1", decision=verdict)
                self.assertEqual(decisions["Q1"][0], verdict)


class TestRethemeLosses(unittest.TestCase):
    """Ranger un lieu ailleurs peut le faire DISPARAÎTRE.

    Le nouveau thème a son plancher et ses voisins. Les arènes d'Arles,
    passées de `monuments` à `megalithes`, se sont retrouvées à vingt-deux
    mètres de « Monuments romains et romans d'Arles » — une inscription
    UNESCO, pas une visite — qui score plus haut et les a évincées. C'est le
    seul geste de la revue dont l'effet peut être destructeur sans être
    visible.
    """

    def test_a_retheme_can_remove_a_place_from_the_catalogue(self):
        from roam_pipeline.collections import build_all
        arenes = make_place("Arènes d'Arles", theme="monuments", sitelinks=20,
                            lat=43.6777, lon=4.6310, wikidata_id="Q181189")
        # Sur le catalogue réel la fiche UNESCO l'emportait à 126 contre 107,
        # sur la longueur de l'article et non sur les langues (19 contre 20).
        # Ici on lui donne l'avantage par les langues : ce qu'on verrouille est
        # le mécanisme, pas la pondération.
        unesco = make_place("Monuments romains et romans d'Arles",
                            theme="megalithes", sitelinks=30,
                            lat=43.6779, lon=4.6310, wikidata_id="Q1279597")
        autres = [make_place(f"Menhir {i}", theme="megalithes", sitelinks=15,
                             lat=44 + i * 0.1, lon=3.0, wikidata_id=f"Q90{i}")
                  for i in range(10)]
        assemblee = [arenes, unesco, *autres]
        score_all(assemblee, CONFIG)

        with _capture():
            avant, _ = build_all(assemblee, CONFIG)
        self.assertIn("Q181189", {p.wikidata_id for p in avant})

        # Le même catalogue, les arènes rangées en mégalithes.
        arenes.theme_id = "megalithes"
        with _capture():
            apres, _ = build_all(assemblee, CONFIG)
        self.assertNotIn("Q181189", {p.wikidata_id for p in apres})
        self.assertIn("Q1279597", {p.wikidata_id for p in apres})


class TestFloorAgainstOfficialLists(unittest.TestCase):
    """Le plancher mesure la documentation ; une liste d'État est une curation.

    Quand les deux se contredisent — une Maison des Illustres à deux langues —
    c'est un arbitrage éditorial. Il doit se voir plutôt que se subir.
    """

    @staticmethod
    def _config():
        return replace(CONFIG, themes=[
            replace(t, from_labels=["maisons-des-illustres"], min_sitelinks=4)
            if t.id == "maisons" else t
            for t in CONFIG.themes])

    def test_the_official_list_passes_the_floor(self):
        # 147 des 231 Maisons des Illustres étaient écartées sur un décompte de
        # versions linguistiques de Wikipédia.
        sur_liste = make_place("Maison obscure", theme="maisons", sitelinks=2,
                               labels=["maisons-des-illustres"])
        hors_liste = make_place("Maison quelconque", theme="maisons", sitelinks=2)
        with _capture():
            gardes = apply_notoriety_floor([sur_liste, hors_liste], self._config())
        self.assertEqual([p.name for p in gardes], ["Maison obscure"])

    def test_any_finite_official_list_passes_the_floor(self):
        # Un Grand Site de France rangé en « gorges » ne profitait d'aucune
        # dispense — le thème n'est alimenté par aucune liste. Or la curation
        # de l'État ne dépend pas du thème où le lieu atterrit.
        grand_site = make_place("Gorge labellisée", theme="gorges", sitelinks=2,
                                labels=["grand-site-de-france"])
        with _capture():
            gardes = apply_notoriety_floor([grand_site], self._config())
        self.assertEqual([p.name for p in gardes], ["Gorge labellisée"])

    def test_a_list_too_large_to_be_a_collection_counts_for_nothing(self):
        # « Monument historique inscrit » compte quarante mille membres : ce
        # n'est pas une sélection, et il ne doit dispenser de rien. C'est
        # `makes_collection: false` qui le dit.
        autre = make_place("Maison classée", theme="maisons", sitelinks=2,
                           labels=["monument-historique-inscrit"])
        with _capture():
            gardes = apply_notoriety_floor([autre], self._config())
        self.assertEqual(gardes, [])

    def test_a_well_documented_listed_place_is_not_counted_as_saved(self):
        # Douze langues : elle franchissait le plancher toute seule, la liste
        # n'y est pour rien et le compte ne doit pas la revendiquer.
        sur_liste = make_place("Maison connue", theme="maisons", sitelinks=12,
                               labels=["maisons-des-illustres"])
        with self.assertNoLogs("roam_pipeline.collections", level="INFO"):
            apply_notoriety_floor([sur_liste], self._config())


class TestRetention(unittest.TestCase):
    """Deux causes opposées produisent le même symptôme : un thème maigre.

    Un thème qui garde neuf dixièmes de sa collecte n'est pas trié, il est
    affamé : la requête ne lui a rien apporté de plus. Un thème qui en garde un
    dixième est richement pourvu, et ses absents ont été écartés.
    """

    @staticmethod
    def _run(brut, catalogue, **extra):
        with tempfile.TemporaryDirectory() as tmp:
            racine = Path(tmp)
            (racine / "raw").mkdir()
            (racine / "out").mkdir()
            write_raw(racine / "raw", brut, {p.theme_id for p in brut})
            (racine / "out" / "places.json").write_text(
                json.dumps([{"theme_id": p.theme_id} for p in catalogue]),
                encoding="utf-8")
            args = argparse.Namespace(
                raw=racine / "raw", out=racine / "out",
                seuil=extra.get("seuil", 0.6), rare=extra.get("rare", 120))
            sortie = StringIO()
            with contextlib.redirect_stdout(sortie):
                cmd_retention(args, CONFIG)
            return sortie.getvalue()

    def test_a_theme_the_query_starves_is_named(self):
        brut = [make_place(f"Cascade {i}", theme="cascades",
                           wikidata_id=f"Q{i}") for i in range(20)]
        texte = self._run(brut, brut[:18])  # 90 % gardés
        self.assertIn("affamé", texte)
        self.assertIn("Cascades", texte)

    def test_a_richly_supplied_theme_is_not_named(self):
        brut = [make_place(f"Château {i}", theme="chateaux",
                           wikidata_id=f"Q{i}") for i in range(200)]
        texte = self._run(brut, brut[:20])  # 10 % gardés
        self.assertNotIn("affamé", texte)

    def test_a_collection_made_above_the_configured_floor_is_named(self):
        # Le plancher des gorges avait baissé de 3 à 2 sans recollecte : le
        # thème restait amputé de tout ce qui vit entre les deux — vingt-huit
        # gorges sur soixante-deux — et rien ne le disait.
        brut = [make_place(f"Gorge {i}", theme="gorges", sitelinks=3 + i,
                           wikidata_id=f"Q{i}") for i in range(10)]
        texte = self._run(brut, brut[:3])
        self.assertIn("plus haute que le réglage actuel", texte)
        self.assertIn("fetch --only", texte)

    def test_a_collection_at_the_configured_floor_is_silent(self):
        brut = [make_place(f"Gorge {i}", theme="gorges", sitelinks=2 + i,
                           wikidata_id=f"Q{i}") for i in range(10)]
        texte = self._run(brut, brut[:3])
        self.assertNotIn("plus haute que le réglage actuel", texte)

    def test_a_theme_fed_by_curated_lists_is_never_starved(self):
        # Les Plus Beaux Villages gardent 99 % : leur source est déjà une
        # curation humaine, finie et triée. Ce n'est pas une famine.
        brut = [make_place(f"Village {i}", theme="villages",
                           wikidata_id=f"Q{i}") for i in range(20)]
        texte = self._run(brut, brut[:20])
        self.assertNotIn("affamé", texte)
        self.assertIn("(listes)", texte)


class TestNatureCandidates(unittest.TestCase):
    """`discover` ne pouvait structurellement pas trouver une cascade.

    Son premier filtre exige un site « géré » — horaires, tarif ou site web —
    et rien de tout cela ne se pose sur une chute d'eau. Résultat : zéro des
    quatre-vingt-six cascades du catalogue ne vient d'OpenStreetMap, alors que
    `natural=waterfall` est demandé à Overpass depuis le début.
    """

    SANS_PORTES = {"cascades", "sommets", "lacs"}

    @staticmethod
    def _site(**kwargs):
        defaults = dict(osm_id="node/1", name="Cascade du Test",
                        lat=45.0, lon=2.0, tags={"natural": "waterfall"})
        defaults.update(kwargs)
        return OsmPlace(**defaults)

    def test_a_managed_site_still_qualifies(self):
        musee = self._site(tags={"tourism": "museum"}, opening_hours="Mo-Su 10:00-18:00")
        self.assertTrue(_atteste(musee, self.SANS_PORTES))

    def test_a_waterfall_with_a_wikidata_item_qualifies(self):
        self.assertTrue(_atteste(self._site(wikidata_id="Q12345"), self.SANS_PORTES))

    def test_a_waterfall_without_any_source_is_refused(self):
        # Sinon tout ruisseau cartographié entrerait dans la feuille.
        self.assertFalse(_atteste(self._site(), self.SANS_PORTES))

    def test_a_waterfall_is_a_confident_candidate(self):
        # Sans cela, une collecte restreinte aux cascades rendrait une feuille
        # VIDE : `is_confident` exigeait des horaires, et vingt minutes de
        # requêtes n'auraient rien produit.
        self.assertTrue(is_confident(self._site(wikidata_id="Q1"), self.SANS_PORTES))
        self.assertFalse(is_confident(self._site(), self.SANS_PORTES))

    def test_the_query_can_be_narrowed_to_one_theme(self):
        filtres = tag_filters_for({"cascades"})
        # Les deux étiquettes d'une chute d'eau, et rien d'autre.
        self.assertEqual(sorted(filtres),
                         ['natural~"^(waterfall)$"', 'waterway~"^(waterfall)$"'])
        requete = cell_query((45.0, 2.0, 45.5, 2.5), tags=filtres)
        clauses = [l for l in requete.splitlines() if "nwr" in l]
        self.assertEqual(len(clauses), 2)
        self.assertTrue(all("waterfall" in c for c in clauses))
        # Sans restriction, toutes les catégories sont demandées.
        self.assertGreater(
            len([l for l in cell_query((45.0, 2.0, 45.5, 2.5)).splitlines()
                 if "nwr" in l]), len(clauses))

    def test_the_real_waterfall_tag_is_asked_for(self):
        # `natural=waterfall` seul a rendu CINQ objets pour toute la France :
        # une chute d'eau se pose sur le cours d'eau, pas sur le relief.
        self.assertEqual(guess_theme({"waterway": "waterfall"}), "cascades")
        self.assertEqual(guess_theme({"natural": "waterfall"}), "cascades")

    def test_a_narrowed_run_writes_its_own_sheet(self):
        # La feuille complète coûte vingt minutes de requêtes Overpass et porte
        # les seuls faits de terrain du catalogue. `discover --only cascades`
        # l'a ramenée à sa seule ligne d'en-tête.
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            complete = out / "candidates.csv"
            complete.write_text("wikidata_id,theme_id\nQ1,musees\n", encoding="utf-8")
            args = argparse.Namespace(out=out, only="cascades")
            vises = {t.strip() for t in (args.only or "").split(",") if t.strip()}
            chemin = out / (f"candidates-{'-'.join(sorted(vises))}.csv"
                            if vises else "candidates.csv")
            self.assertNotEqual(chemin, complete)
            self.assertEqual(chemin.name, "candidates-cascades.csv")
            self.assertIn("Q1", complete.read_text(encoding="utf-8"))

    def test_a_theme_with_no_osm_tag_yields_nothing(self):
        # Les sommets sont mieux servis par Wikidata et ne sont pas demandés à
        # Overpass. La commande doit le dire plutôt que rendre zéro résultat.
        self.assertEqual(tag_filters_for({"sommets"}), [])

    def test_a_gated_theme_still_needs_to_be_managed(self):
        # Un musée sans horaires ni site web reste un point d'intérêt : la
        # porte encyclopédique ne vaut que là où « géré » ne veut rien dire.
        musee = self._site(tags={"tourism": "museum"}, wikidata_id="Q12345")
        self.assertFalse(_atteste(musee, self.SANS_PORTES))


class TestGatedThemes(unittest.TestCase):
    """Le bonus « ouvert au public » ne peut pas s'appliquer partout.

    Il vaut dix points, et OpenStreetMap ne peut l'attester que là où quelqu'un
    ouvre et ferme. Mesuré sur le catalogue : musées 90 %, châteaux 61 % — mais
    volcans 0 %, cascades 1 %, sommets 3 %. C'étaient dix points offerts à la
    culture et zéro à la nature.
    """

    def test_the_bonus_applies_to_a_gated_theme(self):
        avec = make_place("Château ouvert", theme="chateaux", visitable=True)
        sans = make_place("Château muet", theme="chateaux")
        ecart = (score_breakdown(avec, CONFIG)["acces"]
                 - score_breakdown(sans, CONFIG)["acces"])
        self.assertEqual(ecart, CONFIG.scoring.visitable_bonus)

    def test_the_bonus_is_dropped_where_there_are_no_gates(self):
        avec = make_place("Cascade balisée", theme="cascades", visitable=True)
        sans = make_place("Cascade muette", theme="cascades")
        self.assertEqual(score_breakdown(avec, CONFIG)["acces"], 0.0)
        self.assertEqual(score_breakdown(sans, CONFIG)["acces"], 0.0)

    def test_the_malus_survives_everywhere(self):
        # `access=private` sur un sommet est un fait de terrain : le sentier est
        # fermé. Il vaut pour tous les thèmes.
        ferme = make_place("Sommet interdit", theme="sommets", visitable=False)
        self.assertEqual(score_breakdown(ferme, CONFIG)["acces"],
                         -CONFIG.scoring.not_visitable_malus)


class TestThemeShareInGeoCollections(unittest.TestCase):
    """« Le meilleur de Paris » comptait 41 musées sur 80.

    Le quota par département ne peut rien pour ces collections : par
    construction tous leurs lieux sont du même territoire. C'est son symétrique
    qui manquait.
    """

    @staticmethod
    def _lot(compte: dict[str, int]):
        lieux, i = [], 0
        for theme, combien in compte.items():
            for n in range(combien):
                lieux.append(make_place(
                    f"{theme} {n}", theme=theme, sitelinks=40 - n,
                    lat=45 + i * 0.05, lon=2.0, wikidata_id=f"Q{i}"))
                i += 1
        score_all(lieux, CONFIG)
        return sorted(lieux, key=lambda p: (-p.score, p.name))

    def test_no_theme_takes_more_than_its_share(self):
        # Quatre thèmes bien pourvus : le quart de quatre-vingts suffit à
        # remplir la collection, donc le plafond de vingt tient. Avec trois
        # thèmes seulement il monterait — c'est la garantie « jamais plus
        # court », vérifiée par le test suivant.
        lot = self._lot({"musees": 60, "jardins": 30, "ponts": 30,
                         "cathedrales": 30})
        retenus = _mix_themes(lot, 80, 0.25)
        self.assertEqual(len(retenus), 80)
        self.assertEqual(Counter(p.theme_id for p in retenus)["musees"], 20)

    def test_the_share_never_shrinks_a_collection(self):
        # Le Centre-Val de Loire n'a pas soixante lieux hors châteaux : son
        # plafond monte jusqu'à ce que la collection soit pleine.
        lot = self._lot({"chateaux": 70, "abbayes": 10, "musees": 8})
        retenus = _mix_themes(lot, 80, 0.25)
        self.assertEqual(len(retenus), 80)
        self.assertGreater(Counter(p.theme_id for p in retenus)["chateaux"], 20)

    def test_a_thin_collection_is_untouched(self):
        # La Creuse a douze lieux : elle n'a rien à sélectionner. Une part
        # calculée sur les lieux PRÉSENTS la ramenait à huit.
        lot = self._lot({"chateaux": 5, "megalithes": 5, "ponts": 1, "forets": 1})
        retenus = _mix_themes(lot, 80, 0.25)
        self.assertEqual(len(retenus), 12)

    def test_a_mixed_collection_ranks_by_rank_not_by_score(self):
        # La MEILLEURE cascade de France score 74 ; le château MÉDIAN, 86. Au
        # score brut, « Le meilleur de France » ne comptait que trois lieux
        # naturels sur quatre-vingts. Le rang, lui, se compare : le premier des
        # cascades vaut le premier des cathédrales.
        lot = self._lot({"chateaux": 40, "cascades": 40})
        for place in lot:
            if place.theme_id == "cascades":
                place.score = 40 - int(place.name.split()[-1])  # tous très bas
        rangs = _rank_within_theme(lot)
        ordonne = sorted(lot, key=lambda p: (rangs[p.wikidata_id], -p.score))
        self.assertEqual(
            {ordonne[0].theme_id, ordonne[1].theme_id}, {"chateaux", "cascades"})

    def test_the_tiers_follow_the_same_order_as_the_selection(self):
        # Sélectionner par le rang puis classer par le score mettait les
        # vingt-cinq lieux naturels du « meilleur de France » au niveau 3, Puy
        # de Dôme et gorges du Verdon compris.
        lot = self._lot({"chateaux": 20, "cascades": 20})
        for place in lot:
            if place.theme_id == "cascades":
                place.score = 50 - int(place.name.split()[-1])
        rangs = _rank_within_theme(lot)
        ordre = lambda p: (rangs[p.wikidata_id], -p.score, p.name)  # noqa: E731
        niveaux = assign_tiers(sorted(lot, key=ordre), CONFIG.tiers, ordre)
        premiers = {place.theme_id for place, tier, _rang in niveaux if tier == 1}
        self.assertIn("cascades", premiers)

    def test_cross_collections_keep_their_single_theme(self):
        # « Châteaux de Bretagne » est mono-thème par construction. Les deux
        # sortes portent le même `kind` ; c'est `theme_id` qui les distingue.
        with _capture():
            _retenus, cols = build_all(
                self._lot({"chateaux": 40, "abbayes": 12}), _sans_lift())
        croises = [c for c in cols if c.kind == "geo" and c.theme_id]
        self.assertTrue(croises)
        for collection in croises:
            self.assertGreater(len(collection.places), 0)
        chateaux = [c for c in croises if c.theme_id == "chateaux"]
        self.assertTrue(any(len(c.places) > 20 for c in chateaux))


class TestPromoteAgainstTheCap(unittest.TestCase):
    """L'appartenance se décidait avant que le niveau n'existe.

    Le plafond coupait au score, et le verdict du curateur n'arrivait qu'ensuite
    pour ranger ce qui restait. Un `promote` sur un lieu hors collection ne
    faisait donc rien de ce qu'on lui demandait : Camon était 81e sur 154 pour
    un plafond de 80, et le promouvoir le laissait dehors.
    """

    @staticmethod
    def _collection(places, cap, kind="theme"):
        collection = Collection(slug="essai", name="Essai", kind=kind,
                                theme_id="chateaux")
        with _capture():
            return _finalize(collection, places, CONFIG, cap=cap)

    def test_a_promoted_place_enters_despite_the_cap(self):
        lieux = [make_place(f"Château {i}", sitelinks=40 - i, lat=45 + i * 0.1,
                            wikidata_id=f"Q{i}") for i in range(12)]
        score_all(lieux, CONFIG)
        dernier = lieux[-1]  # le moins bien noté, coupé par un plafond de 10
        self.assertNotIn(
            dernier.wikidata_id,
            {cp.place_id for cp in self._collection(lieux, 10).places},
        )
        dernier.tier_shift = -1
        dedans = {cp.place_id for cp in self._collection(lieux, 10).places}
        self.assertIn(dernier.wikidata_id, dedans)
        self.assertEqual(len(dedans), 11)  # onze pour un plafond de dix, assumé

    def test_only_theme_collections_are_forced(self):
        # La revue annonce « HORS COLLECTION NATIONALE » : c'est de la
        # collection THÉMATIQUE qu'elle parle. Forcer partout gonflait « Le
        # meilleur de France » à 125 lieux pour un plafond de 80.
        lieux = [make_place(f"Château {i}", sitelinks=40 - i, lat=45 + i * 0.1,
                            wikidata_id=f"Q{i}") for i in range(12)]
        score_all(lieux, CONFIG)
        lieux[-1].tier_shift = -1
        geo = {cp.place_id for cp in self._collection(lieux, 10, kind="geo").places}
        self.assertNotIn(lieux[-1].wikidata_id, geo)
        self.assertEqual(len(geo), 10)

    def test_a_demoted_place_is_not_forced_in(self):
        # Descendre un lieu n'est pas demander qu'il entre.
        lieux = [make_place(f"Château {i}", sitelinks=40 - i, lat=45 + i * 0.1,
                            wikidata_id=f"Q{i}") for i in range(12)]
        score_all(lieux, CONFIG)
        lieux[-1].tier_shift = 1
        dedans = {cp.place_id for cp in self._collection(lieux, 10).places}
        self.assertNotIn(lieux[-1].wikidata_id, dedans)
        self.assertEqual(len(dedans), 10)


class TestTwins(unittest.TestCase):
    """Ce que le dédoublonnage ne peut pas voir.

    `dedupe` ne compare qu'à l'intérieur d'un thème, et il a raison : un musée
    et la cathédrale d'en face sont deux visites. Mais la même règle laisse
    « palais du Louvre » et « musée du Louvre » cohabiter à dix mètres.
    """

    @staticmethod
    def _lieu(nom, theme, lat, lon, commune):
        return make_place(nom, theme=theme, lat=lat, lon=lon, commune_name=commune,
                          wikidata_id=f"Q{abs(hash(nom)) % 999999}")

    def _paires(self, lieux):
        with _capture():
            jumeaux = twins(lieux)
        return jumeaux

    def test_two_entries_for_the_same_monument_are_flagged(self):
        palais = self._lieu("Palais du Louvre", "chateaux", 48.8606, 2.3376, "Paris")
        musee = self._lieu("Musée du Louvre", "musees", 48.8607, 2.3376, "Paris")
        jumeaux = self._paires([palais, musee])
        # Les DEUX membres sont signalés : on ne tranche qu'en voyant les deux.
        self.assertIn(palais.wikidata_id, jumeaux)
        self.assertIn(musee.wikidata_id, jumeaux)
        autre, distance, motif = jumeaux[palais.wikidata_id][0]
        self.assertEqual(autre.wikidata_id, musee.wikidata_id)
        self.assertLess(distance, 30)
        self.assertIn("louvre", motif)

    def test_the_commune_name_is_not_a_shared_name(self):
        # « Musée des Beaux-Arts de Tours » et « cathédrale Saint-Gatien de
        # Tours » partagent un mot, et ce mot est la ville. La paire reste
        # signalée — elles sont à cinquante mètres — mais le motif ne doit pas
        # prétendre qu'elles portent le même nom, sinon tous les musées de
        # France remontent avec leur cathédrale.
        musee = self._lieu("Musée des Beaux-Arts de Tours", "musees",
                           47.3947, 0.6944, "Tours")
        cathedrale = self._lieu("Cathédrale Saint-Gatien de Tours", "cathedrales",
                                47.3951, 0.6947, "Tours")
        jumeaux = self._paires([musee, cathedrale])
        _autre, _distance, motif = jumeaux[musee.wikidata_id][0]
        self.assertEqual(motif, "à quelques pas")

    def test_same_theme_pairs_are_left_to_dedupe(self):
        a = make_place("Dolmen A", theme="megalithes", lat=45.0, lon=2.0)
        b = make_place("Dolmen B", theme="megalithes", lat=45.0001, lon=2.0)
        self.assertEqual(self._paires([a, b]), {})

    def test_a_shared_name_reaches_further_than_proximity_alone(self):
        # « Château du Louvre » et « musée du Louvre » sont à 188 m : trente-huit
        # de trop pour le seuil ordinaire, et une seule visite pour qui s'y rend.
        chateau = self._lieu("Château du Louvre", "chateaux", 48.8602, 2.338, "Paris")
        musee = self._lieu("Musée du Louvre", "musees", 48.861111, 2.335833, "Paris")
        jumeaux = self._paires([chateau, musee])
        self.assertIn(chateau.wikidata_id, jumeaux)
        _autre, distance, motif = jumeaux[chateau.wikidata_id][0]
        self.assertGreater(distance, DUPLICATE_DISTANCE_M)
        self.assertIn("louvre", motif)

    def test_a_shared_name_also_speaks_inside_one_theme(self):
        # `dedupe` s'arrête à 150 m. L'abbaye de Lérins et sa tour-monastère
        # sont à 160 : deux fiches pour un même rocher, que personne ne voyait.
        abbaye = self._lieu("Abbaye de Lérins", "abbayes",
                            43.5060, 7.0470, "Cannes")
        tour = self._lieu("Tour-monastère de l'abbaye de Lérins", "abbayes",
                          43.5046, 7.0473, "Cannes")
        self.assertIn(abbaye.wikidata_id, self._paires([abbaye, tour]))

    def test_a_shared_name_stops_at_three_hundred_metres(self):
        # Au-delà, le rendement s'effondre : les calanques de Sugiton et de
        # Morgiou partagent « calanque » et sont deux calanques.
        a = self._lieu("Calanque de Sugiton", "plages", 43.2100, 5.4600, "Marseille")
        b = self._lieu("Calanque de Morgiou", "plages", 43.2150, 5.4600, "Marseille")
        self.assertEqual(self._paires([a, b]), {})

    def test_proximity_without_a_shared_name_keeps_the_old_reach(self):
        # Élargir SANS le nom rapprocherait trois cents paires de voisins qui
        # n'ont rien à voir. À 200 m et sans mot commun, on ne dit rien.
        musee = self._lieu("Musée Machin", "musees", 45.0, 2.0, "Ici")
        pont = self._lieu("Pont Truc", "ponts", 45.0018, 2.0, "Ici")
        self.assertEqual(self._paires([musee, pont]), {})

    def test_distant_pairs_are_not_flagged(self):
        musee = self._lieu("Musée Machin", "musees", 45.0, 2.0, "Ici")
        chateau = self._lieu("Château Machin", "chateaux", 45.02, 2.0, "Ici")
        self.assertEqual(self._paires([musee, chateau]), {})

    def test_a_place_can_have_several_twins_closest_first(self):
        # Saint-Remi à Reims : le musée, l'abbaye et la basilique.
        musee = self._lieu("Musée Saint-Remi", "musees", 49.2408, 4.0397, "Reims")
        abbaye = self._lieu("Abbaye Royale de Saint-Remi", "abbayes",
                            49.2408, 4.0397, "Reims")
        basilique = self._lieu("Basilique Saint-Remi", "cathedrales",
                               49.2413, 4.0400, "Reims")
        jumeaux = self._paires([musee, abbaye, basilique])
        lot = jumeaux[musee.wikidata_id]
        self.assertEqual(len(lot), 2)
        self.assertLessEqual(lot[0][1], lot[1][1])


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestCollectionDiameter(unittest.TestCase):
    """Un croisement thème × territoire doit être un voyage, pas un inventaire."""

    @staticmethod
    def _places(count: int, spread_km: float, theme: str = "ponts") -> list[Place]:
        # Un degré de latitude ≈ 111 km : on étale les lieux sur la distance
        # voulue en gardant la même longitude.
        pas = (spread_km / 111.0) / max(count - 1, 1)
        return [
            make_place(
                f"{theme} {i}", theme,
                wikidata_id=f"Q90{i:04d}",
                lat=48.85 + i * pas, lon=2.35,
                sitelinks=12, departement_code="75", region_code="11",
            )
            for i in range(count)
        ]

    @staticmethod
    def _config(km: float) -> Config:
        # Le rapport de caractérisation est neutralisé : ces fixtures n'ont
        # qu'un thème, il vaut donc ×1,0 et écarterait tout.
        return replace(CONFIG, collections=replace(
            CONFIG.collections, min_diameter_km=km, min_theme_lift=0.0,
            cross_theme_levels=["departement"],
        ))

    def test_a_diameter_is_the_distance_between_the_two_farthest(self):
        places = self._places(3, spread_km=100.0)
        self.assertAlmostEqual(diameter_km(places), 100.0, delta=1.0)

    def test_a_single_place_spans_nothing(self):
        self.assertEqual(diameter_km(self._places(1, 0.0)), 0.0)

    def test_a_place_without_coordinates_is_ignored(self):
        places = self._places(2, spread_km=100.0)
        places.append(make_place("sans point", "ponts", lat=None, lon=None))
        self.assertAlmostEqual(diameter_km(places), 100.0, delta=1.0)

    def test_a_local_inventory_makes_no_collection(self):
        # Trente et un ponts dans neuf kilomètres : le cas de Paris.
        built = build_cross_collections(self._places(31, 9.0), self._config(25.0))
        self.assertEqual(built, [])

    def test_a_journey_still_makes_one(self):
        # Carnac : huit mégalithes sur trente et un kilomètres.
        built = build_cross_collections(self._places(8, 31.0), self._config(25.0))
        self.assertEqual(len(built), 1)
        self.assertEqual(len(built[0].places), 8)

    def test_zero_disables_the_rule(self):
        built = build_cross_collections(self._places(31, 9.0), self._config(0.0))
        self.assertEqual(len(built), 1)

    def test_the_rule_spares_the_national_theme_collection(self):
        # Les volcans sont vraiment tous en Auvergne : une collection
        # nationale resserrée reste légitime.
        places = self._places(12, 9.0, theme="volcans")
        built = build_theme_collections(places, self._config(25.0))
        self.assertEqual([c.slug for c in built], ["theme-volcans"])


class TestCollectingLabels(unittest.TestCase):
    """Une liste d'État va chercher ses membres au lieu de les attendre.

    Wikidata rattache deux cent une entités françaises au patrimoine mondial ;
    vingt-quatre seulement tombaient dans un thème. Un label ne faisait que
    tamponner ce que les thèmes avaient déjà trouvé.
    """

    class _Client:
        """Répond aux deux requêtes de la collecte par label, dans l'ordre."""

        def __init__(self, classes: dict[str, str], items: list[dict]):
            self.classes = classes
            self.items = items
            self.appels = 0

        def query(self, requete):
            self.appels += 1
            if "?item ?class" in requete:
                return [
                    {"item": f"http://www.wikidata.org/entity/{qid}",
                     "class": f"http://www.wikidata.org/entity/{classe}"}
                    for qid, classe in self.classes.items()
                    if f"wd:{qid} " in requete or f"wd:{qid} }}" in requete
                ]
            return [row for row in self.items if f"wd:{row['_qid']} " in requete
                    or f"wd:{row['_qid']} }}" in requete]

    @staticmethod
    def _item(qid, name, sitelinks=3):
        return {
            "_qid": qid,
            "item": f"http://www.wikidata.org/entity/{qid}",
            "itemLabel": name,
            "coord": "Point(2.0 45.0)",
            "sitelinks": str(sitelinks),
        }

    @staticmethod
    def _config(**over):
        base = dict(collects=True, query_kind="heritage", qid="Q9259")
        return replace(CONFIG, labels=[
            replace(label, **{**base, **over}) if label.id == "unesco" else
            replace(label, collects=False)
            for label in CONFIG.labels
        ])

    def _run(self, membres, classes, items, known=frozenset()):
        from roam_pipeline.fetch import fetch_labelled_places
        client = self._Client(classes, items)
        with _capture():
            return client, fetch_labelled_places(
                client, self._config(), {"unesco": set(membres)}, set(known)
            )

    def test_a_member_no_theme_collected_is_fetched(self):
        # Q23413 est « château fort » : le membre atterrit chez les châteaux.
        _, places = self._run(
            ["Q1"], {"Q1": "Q23413"}, [self._item("Q1", "Citadelle de Vauban")])
        self.assertEqual([(p.name, p.theme_id) for p in places],
                         [("Citadelle de Vauban", "chateaux")])

    def test_a_collected_member_is_left_alone(self):
        # Le thème l'a déjà pris pour lui-même : son rattachement fait foi.
        client, places = self._run(
            ["Q1"], {"Q1": "Q23413"}, [self._item("Q1", "Déjà là")], known={"Q1"})
        self.assertEqual(places, [])
        self.assertEqual(client.appels, 0)

    def test_a_member_no_theme_claims_is_dropped(self):
        # Une vallée inscrite au patrimoine mondial n'est pas un point.
        _, places = self._run(
            ["Q1"], {"Q1": "Q99999999"}, [self._item("Q1", "Val de Loire")])
        self.assertEqual(places, [])

    def test_a_fetched_member_yields_to_a_theme_that_claims_it(self):
        # Marqué comme une entrée générique : `dedupe_across_themes` le fait
        # céder devant n'importe quel rattachement spécifique.
        _, places = self._run(
            ["Q1"], {"Q1": "Q23413"}, [self._item("Q1", "Citadelle")])
        self.assertTrue(places[0].via_broad_class)
        self.assertEqual(places[0].source, "label")

    def test_a_fetched_member_lives_in_the_extra_shard(self):
        # Sinon `fetch --only chateaux` effacerait les membres des autres
        # thèmes, qu'il n'a pas recollectés.
        from roam_pipeline.raw import EXTRA_SHARD, shard_of
        _, places = self._run(
            ["Q1"], {"Q1": "Q23413"}, [self._item("Q1", "Citadelle")])
        self.assertEqual(shard_of(places[0]), EXTRA_SHARD)

    def test_a_label_that_does_not_collect_asks_nothing(self):
        from roam_pipeline.fetch import fetch_labelled_places
        client = self._Client({}, [])
        places = fetch_labelled_places(
            client, replace(CONFIG, labels=[replace(label, collects=False)
                                            for label in CONFIG.labels]),
            {"unesco": {"Q1"}}, set())
        self.assertEqual(places, [])
        self.assertEqual(client.appels, 0)

    def test_the_theme_order_settles_a_member_with_several_classes(self):
        # Q160742 est « abbaye », Q23413 « château fort » ; `themes.yaml`
        # déclare les abbayes avant les châteaux, et cet ordre est la priorité
        # éditoriale.
        from roam_pipeline.fetch import _theme_of_classes
        theme = _theme_of_classes({"Q23413", "Q160742"}, CONFIG)
        self.assertEqual(theme.id, "abbayes")


class TestResolveList(unittest.TestCase):
    """Retrouver les Q-ids d'une liste officielle dans la collecte.

    Les Grands Sites de France sont dix-neuf chez Wikidata et bien plus au
    ministère : la différence se saisit à la main, donc se résout par le nom.
    """

    def _run(self, noms, places, into=None, classe=None):
        import argparse
        from roam_pipeline.cli import cmd_resolve_list

        with tempfile.TemporaryDirectory() as dossier:
            base = Path(dossier)
            (base / "out").mkdir()
            (base / "manual").mkdir()
            (base / "out" / "places_raw.json").write_text(
                json.dumps([p.to_dict() for p in places], ensure_ascii=False),
                encoding="utf-8")
            liste = base / "noms.txt"
            liste.write_text("\n".join(noms), encoding="utf-8")
            args = argparse.Namespace(
                file=liste, out=base / "out", manual=base / "manual",
                seuil=0.6, into=into, classe=classe)
            sortie = io.StringIO()
            with contextlib.redirect_stdout(sortie):
                code = cmd_resolve_list(args, CONFIG)
            csv_path = base / "manual" / f"{into}.csv"
            ecrit = csv_path.read_text(encoding="utf-8") if csv_path.exists() else ""
        return code, sortie.getvalue(), ecrit

    def test_an_exact_name_resolves(self):
        _, texte, _ = self._run(
            ["Pointe du Raz"], [make_place("Pointe du Raz", "plages")])
        self.assertIn("1 nom(s) retrouvés mot pour mot", texte)

    def test_a_longer_collected_name_is_only_a_proposal(self):
        # « Baie de Somme » couvre entièrement « chemin de fer de la baie de
        # Somme » : couvrir n'est pas désigner.
        _, texte, _ = self._run(
            ["Baie de Somme"],
            [make_place("Chemin de fer de la baie de Somme", "ponts")])
        self.assertIn("à trancher", texte)
        self.assertNotIn("mot pour mot", texte)

    def test_the_exact_match_beats_the_longer_one(self):
        _, texte, _ = self._run(
            ["Gorges du Verdon"],
            [make_place("Basses gorges du Verdon", "gorges"),
             make_place("Gorges du Verdon", "gorges")])
        self.assertIn("mot pour mot", texte)
        self.assertNotIn("Basses", texte)

    def test_an_unknown_name_is_named_not_guessed(self):
        _, texte, _ = self._run(
            ["Cirque de Mafate"], [make_place("Pointe du Raz", "plages")])
        self.assertIn("sans correspondance", texte)
        self.assertIn("suggest-qids", texte)

    def test_only_the_sure_matches_are_written(self):
        _, _, ecrit = self._run(
            ["Pointe du Raz", "Baie de Somme"],
            [make_place("Pointe du Raz", "plages"),
             make_place("Chemin de fer de la baie de Somme", "ponts")],
            into="grand-site-de-france")
        self.assertIn("Pointe du Raz", ecrit)
        self.assertNotIn("Chemin de fer", ecrit)
        self.assertNotIn("Baie de Somme", ecrit)

    def test_articles_do_not_count_as_matching_words(self):
        from roam_pipeline.cli import _mots
        self.assertEqual(_mots("Le Marais de la Somme"), {"marais", "somme"})


class TestLabelFetchScope(unittest.TestCase):
    """Une collecte partielle ne doit pas faire recollecter des lieux acquis.

    Après `fetch --only cascades`, les châteaux ne sont pas dans la collecte du
    jour. Le label irait alors rechercher des lieux qu'un thème possède déjà,
    et les ferait entrer une seconde fois comme entrées génériques.
    """

    def test_a_place_held_by_a_theme_shard_counts_as_known(self):
        from roam_pipeline.raw import EXTRA_SHARD, shard_of
        tenu = make_place("Château tenu", "chateaux")
        self.assertNotEqual(shard_of(tenu), EXTRA_SHARD)

    def test_a_label_place_never_counts_as_known(self):
        # Il vit dans `ajouts`, réécrit à chaque passage : s'il comptait comme
        # acquis, il ne serait plus recollecté et disparaîtrait.
        from roam_pipeline.raw import EXTRA_SHARD, shard_of
        venu = make_place("Citadelle inscrite", "chateaux")
        venu.source = "label"
        self.assertEqual(shard_of(venu), EXTRA_SHARD)


class TestAlreadyHeld(unittest.TestCase):
    """Ce qu'une collecte partielle doit considérer comme déjà acquis.

    Après `fetch --only cascades`, les châteaux ne sont pas dans la collecte du
    jour. Sans ce garde-fou, les candidats adoptés et les membres de listes
    d'État rentraient une seconde fois : le fichier `ajouts` gonflait de
    quatre-vingt-treize lieux selon la façon dont on avait lancé la collecte.
    """

    def _raw(self, dossier, places):
        from roam_pipeline.raw import write_raw, shard_of
        write_raw(Path(dossier), places, {shard_of(p) for p in places})
        return Path(dossier)

    def test_a_theme_not_refetched_still_holds_its_places(self):
        from roam_pipeline.fetch import already_held
        with tempfile.TemporaryDirectory() as dossier:
            raw = self._raw(dossier, [make_place("Château tenu", "chateaux",
                                                 wikidata_id="Q1")])
            self.assertEqual(already_held(raw, {"cascades", "ajouts"}), {"Q1"})

    def test_a_theme_being_refetched_holds_nothing(self):
        # Son fichier va être réécrit : un lieu que la nouvelle requête ne rend
        # plus ne doit pas passer pour acquis, sinon il disparaît sans recours.
        from roam_pipeline.fetch import already_held
        with tempfile.TemporaryDirectory() as dossier:
            raw = self._raw(dossier, [make_place("Cascade", "cascades",
                                                 wikidata_id="Q2")])
            self.assertEqual(already_held(raw, {"cascades", "ajouts"}), set())

    def test_the_extra_shard_never_holds_anything(self):
        # Les ajouts sont recollectés à chaque passage ; les compter comme
        # acquis les empêcherait de l'être et les ferait disparaître.
        from roam_pipeline.fetch import already_held
        from roam_pipeline.raw import EXTRA_SHARD
        with tempfile.TemporaryDirectory() as dossier:
            venu = make_place("Citadelle inscrite", "chateaux", wikidata_id="Q3")
            venu.source = "label"
            raw = self._raw(dossier, [venu])
            self.assertEqual(already_held(raw, {"cascades", EXTRA_SHARD}), set())


class TestLabelOrphansFile(unittest.TestCase):
    """Les membres écartés, sur disque plutôt que dans un journal qui défile.

    Les cent trente-neuf sites funéraires de la Première Guerre mondiale,
    inscrits d'un bloc, sont un choix éditorial à eux seuls : on les prend tous
    ou aucun, et ça se regarde sur une liste.
    """

    class _Client:
        def query(self, requete):
            if "?item ?class" in requete:
                return []          # aucune classe de thème ne les revendique
            if "?itemDescription" in requete:
                return [{"item": "http://www.wikidata.org/entity/Q1",
                         "itemLabel": "cimetière militaire Germania"}]
            return []

    def test_the_discarded_members_are_written_with_their_label(self):
        from roam_pipeline.fetch import LABEL_ORPHANS, fetch_labelled_places
        config = replace(CONFIG, labels=[
            replace(label, collects=(label.id == "unesco")) for label in CONFIG.labels
        ])
        with tempfile.TemporaryDirectory() as dossier:
            out = Path(dossier)
            with _capture():
                places = fetch_labelled_places(
                    self._Client(), config, {"unesco": {"Q1"}}, set(), out_dir=out)
            self.assertEqual(places, [])
            ecrit = (out / LABEL_ORPHANS).read_text(encoding="utf-8")
        self.assertIn("Q1", ecrit)
        self.assertIn("cimetière militaire Germania", ecrit)
        self.assertIn("unesco", ecrit)


class TestCompoundOfficialNames(unittest.TestCase):
    """Une liste officielle nomme le périmètre, pas le lieu.

    « Cap d'Erquy - Cap Fréhel » désigne deux caps, « Chaînes des Puys - Puy de
    Dôme » un massif et son sommet. Cherchés entiers, aucun ne se retrouve.
    """

    def test_a_dash_separates_two_places(self):
        from roam_pipeline.cli import _variantes
        self.assertEqual(
            _variantes("Bibracte - Morvan des Sommets"),
            ["Bibracte - Morvan des Sommets", "Bibracte", "Morvan des Sommets"])

    def test_a_comma_and_an_and_separate_too(self):
        from roam_pipeline.cli import _variantes
        self.assertIn("Côte d'Albâtre", _variantes("Falaises d'Etretat, Côte d'Albâtre"))
        self.assertIn("Vallées de Gavarnie", _variantes("Cirques et Vallées de Gavarnie"))

    def test_a_hyphen_inside_a_name_is_not_a_separator(self):
        # « Concors-Sainte-Victoire » est un nom, pas une énumération : découper
        # sur le tiret collé casserait « Sainte-Victoire » en deux.
        from roam_pipeline.cli import _variantes
        self.assertEqual(_variantes("Concors-Sainte-Victoire"),
                         ["Concors-Sainte-Victoire"])


class TestNaturalClassGaps(unittest.TestCase):
    """Trois classes que `probe` a désignées comme des trous de collecte.

    Sainte-Victoire (23 langues), l'Estérel (11), les gorges de l'Ardèche (12)
    et la Camargue (50) n'étaient dans aucun thème : Wikidata les range en
    « chaîne de montagnes », « vallée » et « zone humide », qu'aucun thème ne
    déclarait. Ce ne sont pas des lieux mal notés, ce sont des lieux invisibles.
    """

    def test_the_new_classes_are_collected_generically(self):
        for theme_id, qid in (("sommets", "Q46831"),
                              ("gorges", "Q39816"),
                              ("dunes-marais", "Q170321")):
            theme = CONFIG.theme(theme_id)
            with self.subTest(theme_id):
                self.assertIn(qid, {b.qid for b in theme.broad_classes})
                # Générique veut dire : plancher de collecte plus haut que
                # celui du thème, sinon on ramène toute la classe.
                floor = dict(theme.collected_classes)[qid]
                self.assertGreater(floor, theme.fetch_min_sitelinks)

    def test_sainte_victoire_and_the_camargue_would_pass_their_floor(self):
        # Vingt-trois et cinquante versions linguistiques, d'après `probe`.
        self.assertLessEqual(dict(CONFIG.theme("sommets").collected_classes)["Q46831"], 23)
        self.assertLessEqual(
            dict(CONFIG.theme("dunes-marais").collected_classes)["Q170321"], 50)

    def test_the_ardeche_gorges_would_pass_theirs(self):
        self.assertLessEqual(dict(CONFIG.theme("gorges").collected_classes)["Q39816"], 12)


class TestAlignDepartements(unittest.TestCase):
    """Un code INSEE de commune contient son département : la vérification est
    gratuite, et elle n'était pas faite.

    Trente-sept lieux se contredisaient eux-mêmes et se rangeaient dans la
    mauvaise collection départementale : le château d'Écouen, commune 95205,
    donc Val-d'Oise, figurait dans « Châteaux des Yvelines ».
    """

    def _cale(self, place):
        from roam_pipeline.fetch import align_departements
        with _capture():
            align_departements([place])
        return place

    def test_the_commune_wins_over_wikidata(self):
        ecouen = make_place("Château d'Écouen", "chateaux", wikidata_id="Q1817122",
                            commune_code="95205", commune_name="Écouen",
                            departement_code="78", region_code="11")
        self._cale(ecouen)
        self.assertEqual(ecouen.departement_code, "95")

    def test_the_region_follows_the_departement(self):
        # Le lac Blanc est dans le Haut-Rhin, pas dans les Vosges : Wikidata
        # remonte la chaîne P131 d'un massif, elle change de région au passage.
        lac = make_place("Lac Blanc", "lacs", wikidata_id="Q267332",
                         commune_code="68249", departement_code="88",
                         region_code="44")
        self._cale(lac)
        self.assertEqual((lac.departement_code, lac.region_code), ("68", "44"))

    def test_a_place_that_already_agrees_is_left_alone(self):
        from roam_pipeline.fetch import align_departements
        gordes = make_place("Gordes", "villages", wikidata_id="Q2",
                            commune_code="84091", departement_code="84")
        with _capture():
            self.assertEqual(align_departements([gordes]), 0)

    def test_overseas_codes_are_three_digits(self):
        # 97411 est Saint-Denis de La Réunion : le département est 974, pas 97.
        piton = make_place("Piton de la Fournaise", "sommets", wikidata_id="Q3",
                           commune_code="97414", departement_code=None)
        self._cale(piton)
        self.assertEqual(piton.departement_code, "974")

    def test_the_overseas_collectivities_stay_out(self):
        # 98817 est Lifou, en Nouvelle-Calédonie : une COM, hors périmètre v1.
        # Lui donner « 988 » comme département la faisait entrer par la porte du
        # filtre, qui n'écarte que ce qu'il ne sait pas situer.
        lifou = make_place("Lifou", "iles", wikidata_id="Q5",
                           commune_code="98817", departement_code=None)
        self._cale(lifou)
        self.assertIsNone(lifou.departement_code)

    def test_a_place_without_a_commune_is_untouched(self):
        # Un phare en mer n'a pas de commune : rien à recaler, et surtout rien
        # à effacer.
        phare = make_place("Phare de la Jument", "phares", wikidata_id="Q4",
                           commune_code=None, departement_code="29")
        self._cale(phare)
        self.assertEqual(phare.departement_code, "29")


class TestCarryEnrichment(unittest.TestCase):
    """Une collecte ne doit pas écraser ce qu'`enrich` a mis des heures à poser.

    Huit mille cent soixante-seize lieux ont perdu d'un coup la taille de leur
    article et leur fréquentation, cinq cent vingt-trois leur département. Le
    premier fausse tous les scores ; le second vide le catalogue, le filtre
    « périmètre français » écartant ce qu'il ne sait pas situer.
    """

    def _avec(self, precedent, neuf):
        from roam_pipeline.fetch import carry_enrichment
        from roam_pipeline.raw import shard_of, write_raw
        with tempfile.TemporaryDirectory() as dossier:
            raw = Path(dossier)
            write_raw(raw, precedent, {shard_of(p) for p in precedent})
            with _capture():
                carry_enrichment(neuf, raw, raw / "places_raw.json")
        return neuf

    def test_the_departement_survives_a_new_collection(self):
        ancien = make_place("Saint-Guilhem-le-Désert", "villages", wikidata_id="Q1",
                            departement_code="34", region_code="76")
        neuf = make_place("Saint-Guilhem-le-Désert", "villages", wikidata_id="Q1",
                          departement_code=None, region_code=None)
        self._avec([ancien], [neuf])
        self.assertEqual((neuf.departement_code, neuf.region_code), ("34", "76"))

    def test_the_disqualifying_class_survives_a_new_collection(self):
        # Le Parc Astérix, Nigloland et Marineland sont rentrés trois fois en
        # quatre jours : marqués le 30 août, blanchis le 1er septembre,
        # remarqués le 2, blanchis le 3. Le drapeau vient d'`enrich`, qui
        # interroge Wikidata ; une collecte reconstruit ses lieux sans lui.
        ancien = make_place("Parc Astérix", "musees", wikidata_id="Q377592",
                            excluded_class="parc d'attractions")
        neuf = make_place("Parc Astérix", "musees", wikidata_id="Q377592")
        self.assertIsNone(neuf.excluded_class)
        self._avec([ancien], [neuf])
        self.assertEqual(neuf.excluded_class, "parc d'attractions")

    def test_a_place_just_cleared_does_not_get_its_class_back(self):
        # `enrich_exclusions` écrit la chaîne VIDE pour dire « vérifié, rien à
        # redire ». Si le report la traitait comme une absence, retirer une
        # classe de la liste ne rendrait plus jamais son lieu au catalogue :
        # l'exclusion serait un aller sans retour.
        ancien = make_place("Cité de l'espace", "musees", wikidata_id="Q1",
                            excluded_class="parc d'attractions")
        neuf = make_place("Cité de l'espace", "musees", wikidata_id="Q1",
                          excluded_class="")
        self._avec([ancien], [neuf])
        self.assertEqual(neuf.excluded_class, "")

    def test_the_article_and_the_crowd_survive_too(self):
        ancien = make_place("Léman", "lacs", wikidata_id="Q2",
                            article_bytes=40_000, pageviews_per_month=9_000,
                            visitors_per_year=1_200_000)
        neuf = make_place("Léman", "lacs", wikidata_id="Q2")
        self._avec([ancien], [neuf])
        self.assertEqual(neuf.article_bytes, 40_000)
        self.assertEqual(neuf.pageviews_per_month, 9_000)
        self.assertEqual(neuf.visitors_per_year, 1_200_000)

    def test_a_fresher_value_wins(self):
        # Seules les valeurs ABSENTES sont reprises : une collecte qui apporte
        # mieux garde son apport, et `enrich` reste libre de tout rafraîchir.
        ancien = make_place("Château", "chateaux", wikidata_id="Q3", departement_code="34")
        neuf = make_place("Château", "chateaux", wikidata_id="Q3", departement_code="15")
        self._avec([ancien], [neuf])
        self.assertEqual(neuf.departement_code, "15")

    def test_an_unknown_place_carries_nothing(self):
        ancien = make_place("Ailleurs", "chateaux", wikidata_id="Q4",
                            departement_code="34", article_bytes=9_000)
        neuf = make_place("Nouveau", "chateaux", wikidata_id="Q5",
                          departement_code=None)
        self._avec([ancien], [neuf])
        self.assertIsNone(neuf.departement_code)
        self.assertEqual(neuf.article_bytes, 0)


class TestRelabel(unittest.TestCase):
    """Rapposer un label ne doit pas demander de recollecter les lieux.

    Les labels sont apposés pendant `fetch`, et sur les seuls thèmes qu'il a
    recollectés : ajouter un Grand Site à la liste manuelle n'avait aucun effet
    tant qu'on n'avait pas refait passer son thème — une demi-heure pour
    changer une ligne de CSV.
    """

    class _Client:
        """Wikidata ne connaît qu'un membre ; le reste vient du fichier."""

        def query(self, requete):
            if "wd:Q1154112" in requete:
                return [{"item": "http://www.wikidata.org/entity/Q607372"}]
            return []

    def _run(self, places, manuel=None):
        from unittest import mock
        from roam_pipeline.cli import cmd_relabel
        from roam_pipeline.raw import shard_of, write_raw

        with tempfile.TemporaryDirectory() as dossier:
            base = Path(dossier)
            (base / "out").mkdir()
            (base / "manual").mkdir()
            write_raw(base / "raw", places, {shard_of(p) for p in places})
            (base / "out" / "places_raw.json").write_text(
                json.dumps([p.to_dict() for p in places], ensure_ascii=False),
                encoding="utf-8")
            if manuel is not None:
                (base / "manual" / "grand-site-de-france.csv").write_text(
                    "wikidata_id,name\r\n" + "".join(f"{q},{n}\r\n" for q, n in manuel),
                    encoding="utf-8")
            args = argparse.Namespace(
                out=base / "out", raw=base / "raw", manual=base / "manual")
            with mock.patch("roam_pipeline.wikidata.SparqlClient", self._Client), \
                    _capture() as sortie:
                cmd_relabel(args, CONFIG)
            sortie = io.StringIO(sortie.getvalue())
            relu = json.loads(
                (base / "out" / "places_raw.json").read_text(encoding="utf-8"))
        return {p["wikidata_id"]: p.get("labels") or [] for p in relu}, sortie.getvalue()

    def test_a_manual_entry_gets_its_label_without_a_new_collection(self):
        sainte_victoire = make_place("Montagne Sainte-Victoire", "sommets",
                                     wikidata_id="Q1518970")
        etiquettes, texte = self._run(
            [sainte_victoire], manuel=[("Q1518970", "Concors-Sainte-Victoire")])
        self.assertIn("grand-site-de-france", etiquettes["Q1518970"])
        self.assertIn("gagnent un label", texte)

    def test_what_wikidata_says_is_kept_alongside(self):
        puy = make_place("Puy de Dôme", "volcans", wikidata_id="Q607372")
        etiquettes, _ = self._run([puy], manuel=[])
        self.assertIn("grand-site-de-france", etiquettes["Q607372"])

    def test_a_label_removed_from_the_list_is_removed_from_the_place(self):
        # Le recalcul repart de zéro : retirer une ligne doit retirer le label,
        # sans quoi une erreur de saisie serait un aller sans retour.
        ancien = make_place("Lieu déclassé", "sommets", wikidata_id="Q999",
                            labels=["grand-site-de-france"])
        etiquettes, texte = self._run([ancien], manuel=[])
        self.assertEqual(etiquettes["Q999"], [])
        self.assertIn("en perdent un", texte)


class TestSaveRawGuard(unittest.TestCase):
    """Le dépôt fait foi sur ce qu'`enrich` a posé.

    `places_raw.json` n'est pas versionné : après un `git pull`, il est en
    retard. Une commande qui le relit et le réécrit efface alors ce que le
    dépôt venait d'apporter — c'est ainsi qu'un `relabel` a annulé la
    réparation de huit mille lieux, sans un mot.
    """

    def _ecrit(self, depot, lot):
        from roam_pipeline.cli import _save_raw
        from roam_pipeline.raw import read_raw, shard_of, write_raw
        with tempfile.TemporaryDirectory() as dossier:
            base = Path(dossier)
            (base / "out").mkdir()
            write_raw(base / "raw", depot, {shard_of(p) for p in depot})
            args = argparse.Namespace(raw=base / "raw", out=base / "out")
            with _capture() as sortie:
                _save_raw(args, lot)
            return {p.wikidata_id: p for p in read_raw(base / "raw")}, sortie.getvalue()

    def test_a_stale_copy_cannot_erase_the_repository(self):
        enrichi = make_place("Léman", "lacs", wikidata_id="Q1",
                             departement_code="74", article_bytes=40_000)
        perime = make_place("Léman", "lacs", wikidata_id="Q1",
                            departement_code=None, article_bytes=0)
        depot, _ = self._ecrit([enrichi], [perime])
        self.assertEqual(depot["Q1"].departement_code, "74")
        self.assertEqual(depot["Q1"].article_bytes, 40_000)

    def test_the_change_being_written_is_kept(self):
        # Le garde-fou complète, il n'annule pas : un renommage passe.
        ancien = make_place("Porte d'Aval", "rochers", wikidata_id="Q2",
                            departement_code="76", article_bytes=9_000)
        neuf = make_place("Falaises d'Étretat", "rochers", wikidata_id="Q2",
                          departement_code=None, article_bytes=0)
        depot, _ = self._ecrit([ancien], [neuf])
        self.assertEqual(depot["Q2"].name, "Falaises d'Étretat")
        self.assertEqual(depot["Q2"].departement_code, "76")


class TestThemeLift(unittest.TestCase):
    """Un croisement doit dire quelque chose de son territoire.

    « Cathédrales et basiliques de Provence-Alpes-Côte d'Azur » vaut ×1,0 : la
    région n'a ni plus ni moins de cathédrales que la moyenne du pays, et cette
    collection n'est que le thème national redécoupé.
    """

    def test_an_average_territory_scores_one(self):
        from roam_pipeline.collections import theme_lift
        # 10 cathédrales sur 100 lieux ici, 100 sur 1000 dans le pays.
        self.assertAlmostEqual(theme_lift(10, 100, 100, 1000), 1.0)

    def test_a_concentration_scores_high(self):
        from roam_pipeline.collections import theme_lift
        # Les volcans du Puy-de-Dôme : le thème y est trente fois plus dense.
        self.assertAlmostEqual(theme_lift(30, 100, 10, 1000), 30.0)

    def test_an_empty_territory_scores_nothing(self):
        from roam_pipeline.collections import theme_lift
        self.assertEqual(theme_lift(0, 0, 10, 1000), 0.0)
        self.assertEqual(theme_lift(5, 100, 0, 1000), 0.0)

    def test_the_configured_threshold_spares_the_loire(self):
        # Les châteaux du Centre-Val de Loire valent ×3,0, les mégalithes du
        # Morbihan ×4,8 : le seuil doit passer sous les deux.
        self.assertLessEqual(CONFIG.collections.min_theme_lift, 3.0)
        self.assertGreater(CONFIG.collections.min_theme_lift, 1.0)


class TestTwinCollections(unittest.TestCase):
    """Un département d'outre-mer est AUSSI une région.

    La Réunion produisait « Le meilleur de La Réunion » deux fois, à
    l'identique, et l'utilisateur voyait les deux.
    """

    @staticmethod
    def _collection(slug, name, ids, level):
        c = Collection(slug=slug, name=name, kind="geo", geo_level=level, geo_code="974")
        c.places = [CollectionPlace(place_id=q, tier=1, rank=i + 1)
                    for i, q in enumerate(ids)]
        return c

    def test_the_same_places_under_the_same_name_appear_once(self):
        from roam_pipeline.collections import drop_twin_collections
        a = self._collection("geo-departement-974", "Le meilleur de La Réunion",
                             ["Q1", "Q2"], "departement")
        b = self._collection("geo-region-04", "Le meilleur de La Réunion",
                             ["Q2", "Q1"], "region")
        with _capture():
            gardees = drop_twin_collections([a, b])
        self.assertEqual([c.slug for c in gardees], ["geo-departement-974"])

    def test_the_same_name_over_different_places_is_kept(self):
        from roam_pipeline.collections import drop_twin_collections
        a = self._collection("a", "Le meilleur de La Réunion", ["Q1"], "departement")
        b = self._collection("b", "Le meilleur de La Réunion", ["Q2"], "region")
        self.assertEqual(len(drop_twin_collections([a, b])), 2)

    def test_the_same_places_under_another_name_is_kept(self):
        # « Le meilleur de la Dordogne » et « Grottes de la Dordogne » peuvent
        # coïncider sans être la même collection.
        from roam_pipeline.collections import drop_twin_collections
        a = self._collection("a", "Le meilleur de la Dordogne", ["Q1"], "departement")
        b = self._collection("b", "Grottes et gouffres de la Dordogne", ["Q1"], "departement")
        self.assertEqual(len(drop_twin_collections([a, b])), 2)


class TestResolveAgainstWikidata(unittest.TestCase):
    """Une liste officielle publie des noms, pas des identifiants.

    Le thème « Villages » n'a AUCUNE classe Wikidata : ses manquants ne sont
    jamais dans la collecte, et les chercher là n'y peut rien. Il faut aller
    les demander à Wikidata, bornés par une classe pour que « Rocamadour » ne
    ramène ni le fromage ni le canton québécois.
    """

    class _Client:
        def __init__(self, rows, descriptions=(), utiles=()):
            self.rows = rows
            self.descriptions = list(descriptions)
            self.utiles = list(utiles)
            self.vu = []

        def query(self, requete):
            self.vu.append(requete)
            if "?itemDescription" in requete:
                return self.descriptions
            if "?coord" in requete:
                return self.utiles
            return self.rows

    @staticmethod
    def _row(nom, qid, label=None):
        return {"nom": nom, "item": f"http://www.wikidata.org/entity/{qid}",
                "itemLabel": label or nom}

    def _run(self, noms, rows, descriptions=(), utiles=()):
        from unittest import mock
        from roam_pipeline.cli import _resolve_chez_wikidata
        client = self._Client(rows, descriptions, utiles)
        with mock.patch("roam_pipeline.wikidata.SparqlClient", lambda: client):
            return _resolve_chez_wikidata(noms, "Q484170"), client

    def test_a_single_match_resolves(self):
        (trouves, ambigus), _ = self._run(["Rocamadour"], [self._row("Rocamadour", "Q382628")])
        self.assertEqual([(n, p.wikidata_id) for n, p in trouves], [("Rocamadour", "Q382628")])
        self.assertEqual(ambigus, {})

    def test_several_matches_are_never_guessed(self):
        # « Saint-Martin » est une trentaine de communes : choisir au hasard
        # écrirait un faux identifiant dans une liste officielle.
        (trouves, ambigus), _ = self._run(
            ["Saint-Martin"],
            [self._row("Saint-Martin", "Q1"), self._row("Saint-Martin", "Q2")])
        self.assertEqual(trouves, [])
        self.assertEqual(len(ambigus["Saint-Martin"]), 2)

    def test_the_class_bounds_the_search(self):
        _, client = self._run(["Rocamadour"], [])
        self.assertIn("wd:Q484170", client.vu[0])
        self.assertIn('"Rocamadour"@fr', client.vu[0])

    def test_homonyms_carry_their_description(self):
        # Une douzaine de « Villeneuve » sans rien pour les distinguer ne se
        # tranchent pas. La description nomme le département, et la liste
        # officielle donne le même.
        (_trouves, ambigus), _ = self._run(
            ["Villeneuve"],
            [self._row("Villeneuve", "Q1"), self._row("Villeneuve", "Q2")],
            descriptions=[
                {"item": "http://www.wikidata.org/entity/Q1",
                 "itemDescription": "commune française du département de l'Aveyron"},
                {"item": "http://www.wikidata.org/entity/Q2",
                 "itemDescription": "commune française du département de l'Ain"},
            ])
        libelles = dict(ambigus["Villeneuve"])
        self.assertIn("Aveyron", libelles["Q1"])
        self.assertIn("Ain", libelles["Q2"])

    def test_an_entity_without_coordinates_says_so(self):
        # Entre une « ancienne commune » et la « commune nouvelle » qui l'a
        # absorbée, c'est le seul critère qui ne demande aucun jugement : sans
        # coordonnées, `items_query` ne rend rien et le lieu est incollectable.
        (_trouves, ambigus), _ = self._run(
            ["Villeneuve"],
            [self._row("Villeneuve", "Q1"), self._row("Villeneuve", "Q2")],
            utiles=[{"item": "http://www.wikidata.org/entity/Q1", "sitelinks": "12"}])
        libelles = dict(ambigus["Villeneuve"])
        self.assertIn("12 langues", libelles["Q1"])
        self.assertIn("incollectable", libelles["Q2"])

    def test_a_name_wikidata_ignores_stays_unresolved(self):
        (trouves, ambigus), _ = self._run(["Village imaginaire"], [])
        self.assertEqual((trouves, ambigus), ([], {}))


class TestResolveOrder(unittest.TestCase):
    """Avec une classe, Wikidata passe AVANT le rapprochement par les mots.

    Une classe est une contrainte exacte ; le rapprochement par les mots ne
    l'est pas, et il se trompe de façon crédible : « Fontevraud-l'Abbaye »
    désigne une commune, et la collecte n'en connaît que l'abbaye. Écrire ce
    Q-id-là dans une liste de villages serait une erreur muette.
    """

    class _Client:
        def query(self, requete):
            if "?nom ?item" not in requete:
                return []
            return [{"nom": "Fontevraud-l'Abbaye",
                     "item": "http://www.wikidata.org/entity/Q1111",
                     "itemLabel": "Fontevraud-l'Abbaye"}]

    def _run(self, classe):
        import argparse
        from unittest import mock
        from roam_pipeline.cli import cmd_resolve_list
        abbaye = make_place("Abbaye de Fontevraud", "abbayes", wikidata_id="Q9999")
        with tempfile.TemporaryDirectory() as dossier:
            base = Path(dossier)
            (base / "out").mkdir(); (base / "manual").mkdir()
            (base / "out" / "places_raw.json").write_text(
                json.dumps([abbaye.to_dict()], ensure_ascii=False), encoding="utf-8")
            liste = base / "noms.txt"
            liste.write_text("Fontevraud-l'Abbaye\n", encoding="utf-8")
            args = argparse.Namespace(
                file=liste, out=base / "out", manual=base / "manual",
                seuil=0.6, into="plus-beaux-villages", classe=classe)
            with mock.patch("roam_pipeline.wikidata.SparqlClient", self._Client), \
                    _capture() as sortie:
                cmd_resolve_list(args, CONFIG)
            ecrit = (base / "manual" / "plus-beaux-villages.csv").read_text(encoding="utf-8")
        return sortie.getvalue(), ecrit

    def test_the_commune_wins_over_the_abbey(self):
        _texte, ecrit = self._run("Q484170")
        self.assertIn("Q1111", ecrit)
        self.assertNotIn("Q9999", ecrit)

    def test_without_a_class_the_abbey_is_written_as_a_village(self):
        # La démonstration du danger : « Fontevraud-l'Abbaye » et « Abbaye de
        # Fontevraud » ont exactement les mêmes mots. Le rapprochement les tient
        # donc pour un accord parfait et écrit l'abbaye sans rien demander.
        # C'est ce que la classe empêche.
        _texte, ecrit = self._run(None)
        self.assertIn("Q9999", ecrit)
        self.assertNotIn("Q1111", ecrit)
