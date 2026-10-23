import os
import re
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

import yaml

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "sport-lookback.yaml"
TAG = "__uw-krea2-nsfw/router/portrait-sport-pics__"
_TAG_RE = re.compile(r"__([\w.\-+/*\\]+?)__")


def _normalize(key):
    return key.replace("\\", "/").replace(" ", "-").lower()


def _flatten(key, value, into):
    if isinstance(value, list):
        into[_normalize(key)] = [str(item) for item in value]
    elif isinstance(value, dict):
        for child, inner in value.items():
            _flatten(f"{key}/{child}", inner, into)
    elif isinstance(value, str):
        into[_normalize(key)] = [value]


def load_fixture_catalog():
    data = yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))
    catalog = {}
    for key, value in data.items():
        _flatten(key, value, catalog)
    return catalog


def _pack_zip():
    override = os.environ.get("UW_PACK_ZIP")
    if override:
        path = Path(override)
        if path.is_file():
            return path
    candidate = (
        Path.home()
        / "projects"
        / "extension-sd-neo"
        / "uwModularV3"
        / "uwModularNSFWWildcardsPhotoreal_v300_3143438.zip"
    )
    if candidate.is_file():
        return candidate
    raise unittest.SkipTest("no está el zip del pack; define UW_PACK_ZIP")


def _install_impact_stub(catalog):
    """Sustituye Impact para que el oráculo del zip pueda llamar a process.

    Solo resuelve __tag__ de izquierda a derecha. El fixture no tiene llaves
    ni pesos, que es la parte de Impact que este test no cubre.
    """
    import types

    impact = types.ModuleType("impact")
    wildcards = types.ModuleType("impact.wildcards")
    wildcards._catalog = catalog

    def get_wildcard_dict():
        return wildcards._catalog

    def get_wildcard_value(key):
        return wildcards._catalog.get(_normalize(str(key)))

    def wildcard_load():
        raise AssertionError("el oráculo no debe recargar el corpus")

    def process(text, seed=None):
        import random

        rng = random.Random(0 if seed is None else int(seed))
        current = "" if text is None else str(text)
        for _ in range(100):
            pieces = []
            pos = 0
            replaced = False
            for match in _TAG_RE.finditer(current):
                pieces.append(current[pos : match.start()])
                options = wildcards.get_wildcard_value(match.group(1))
                if options is None:
                    pieces.append(match.group(0))
                else:
                    pieces.append(rng.choice(list(options)))
                    replaced = True
                pos = match.end()
            pieces.append(current[pos:])
            current = "".join(pieces)
            if not replaced:
                break
        return current

    wildcards.get_wildcard_dict = get_wildcard_dict
    wildcards.get_wildcard_value = get_wildcard_value
    wildcards.wildcard_load = wildcard_load
    wildcards.process = process
    impact.wildcards = wildcards
    sys.modules["impact"] = impact
    sys.modules["impact.wildcards"] = wildcards
    return wildcards


def _oracle_expand(text, seed, **overrides):
    pack = _pack_zip()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        with zipfile.ZipFile(pack) as archive:
            for name in (
                "ComfyUI-WildcardClause/clause_expand.py",
                "ComfyUI-WildcardClause/contract.py",
            ):
                target = root / Path(name).name
                target.write_bytes(archive.read(name))
        sys.path.insert(0, str(root))
        try:
            for module_name in ("clause_expand", "contract"):
                sys.modules.pop(module_name, None)
            import clause_expand

            return clause_expand.expand_with_overrides(text, seed, **overrides)
        finally:
            sys.path.remove(str(root))


class ClauseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = load_fixture_catalog()
        _install_impact_stub(cls.catalog)

    def test_fixture_is_a_small_text_slice(self):
        self.assertLess(FIXTURE.stat().st_size, 4096)
        self.assertEqual(FIXTURE.suffix, ".yaml")
        keys = set(self.catalog)
        self.assertIn("uw-krea2-nsfw/router/portrait-sport-pics", keys)
        self.assertIn(
            "uw-krea2-nsfw/template/theme-sport-volleyball-gym-lookback", keys
        )
        self.assertIn(
            "uw-krea2-nsfw/leaf/theme-sport-volleyball-gym-lookback/medium", keys
        )
        self.assertIn(
            "uw-krea2-nsfw/leaf/theme-sport-volleyball-gym-lookback/treatment",
            keys,
        )

    def test_router_matches_zip_oracle(self):
        from forge_uw_wildcards.clauses import expand_with_overrides

        expected = _oracle_expand(TAG, 7)
        actual = expand_with_overrides(TAG, 7, catalog=self.catalog)
        self.assertEqual(actual, expected)
        self.assertNotIn("__", actual)

    def test_medium_override_matches_zip_oracle(self):
        from forge_uw_wildcards.clauses import expand_with_overrides

        override = "An anime-style illustration of"
        expected = _oracle_expand(TAG, 7, medium_override=override)
        actual = expand_with_overrides(
            TAG, 7, catalog=self.catalog, medium_override=override
        )
        self.assertEqual(actual, expected)
        self.assertIn(override, actual)

    def test_non_uw_tag_is_left_intact(self):
        from forge_uw_wildcards.clauses import expand_with_overrides

        catalog = dict(self.catalog)
        catalog["film/stock"] = ["kodak portra"]
        text = "shot on __film/stock__"
        self.assertEqual(
            expand_with_overrides(text, 1, catalog=catalog),
            text,
        )


LIGHTING = ("DAWN-LIGHT", "NOON-LIGHT", "DUSK-LIGHT", "NIGHT-LIGHT")
HAIR = ("BOB-HAIR", "BRAID-HAIR", "PIXIE-HAIR", "CURL-HAIR")
AGE = ("AGE-TWENTY", "AGE-THIRTY", "AGE-FORTY", "AGE-FIFTY")
SLOT_TAG = "__uw-krea2-nsfw/template/slot-demo__"


def _slot_catalog():
    return {
        "uw-krea2-nsfw/template/slot-demo": [
            "__uw-krea2-nsfw/leaf/demo/lighting__, __uw-shared/common/hair/grp1__, __uw-shared/common/age/nsfw-default__"
        ],
        "uw-krea2-nsfw/leaf/demo/lighting": list(LIGHTING),
        "uw-shared/common/hair/grp1": list(HAIR),
        "uw-shared/common/age/nsfw-default": list(AGE),
    }


def _only(text, options):
    found = [item for item in options if item in text]
    if len(found) != 1:
        raise AssertionError(f"esperaba una opción de {options} en {text!r}, hay {found}")
    return found[0]


class SlotTests(unittest.TestCase):
    def test_reroll_lighting_keeps_hair_and_age(self):
        from forge_uw_wildcards.clauses import expand_with_overrides

        catalog = _slot_catalog()
        base = expand_with_overrides(SLOT_TAG, 1, catalog=catalog)
        rerolled = expand_with_overrides(
            SLOT_TAG, 1, catalog=catalog, counters={"lighting": 1}
        )
        self.assertEqual(_only(base, HAIR), _only(rerolled, HAIR))
        self.assertEqual(_only(base, AGE), _only(rerolled, AGE))
        self.assertNotEqual(_only(base, LIGHTING), _only(rerolled, LIGHTING))

    def test_pin_survives_a_different_global_seed(self):
        from forge_uw_wildcards.clauses import expand_with_overrides

        catalog = _slot_catalog()
        pin = "long silver hair in a braid"
        seeds_for_hair = {}
        for seed in range(40):
            hair = _only(expand_with_overrides(SLOT_TAG, seed, catalog=catalog), HAIR)
            seeds_for_hair.setdefault(hair, seed)
            if len(seeds_for_hair) == 2:
                break
        self.assertEqual(len(seeds_for_hair), 2)
        first_seed, second_seed = list(seeds_for_hair.values())
        first = expand_with_overrides(
            SLOT_TAG, first_seed, catalog=catalog, hair_override=pin
        )
        second = expand_with_overrides(
            SLOT_TAG, second_seed, catalog=catalog, hair_override=pin
        )
        self.assertIn(pin, first)
        self.assertIn(pin, second)
        for line in HAIR:
            self.assertNotIn(line, first)
            self.assertNotIn(line, second)

    def test_skip_drops_the_clause(self):
        from forge_uw_wildcards.clauses import SKIP_OVERRIDE_SENTINEL, expand_with_overrides

        catalog = _slot_catalog()
        text = expand_with_overrides(
            SLOT_TAG,
            1,
            catalog=catalog,
            lighting_override=SKIP_OVERRIDE_SENTINEL,
        )
        for line in LIGHTING:
            self.assertNotIn(line, text)
        self.assertNotIn(SKIP_OVERRIDE_SENTINEL, text)
        _only(text, HAIR)
        _only(text, AGE)


PUNCT_TAG = "__uw-krea2-nsfw/template/punct__"


def _punct_catalog(template):
    return {
        "uw-krea2-nsfw/template/punct": [template],
        "uw-shared/common/body-archetype/natural": ["athletic"],
        "uw-shared/common/age/nsfw-default": ["around twenty"],
    }


class PunctuationTests(unittest.TestCase):
    def setUp(self):
        self.catalog = _punct_catalog(
            "start __uw-shared/common/body-archetype/natural__, "
            "__uw-shared/common/age/nsfw-default__, end."
        )
        previous = sys.modules.get("impact.wildcards")
        self._previous = getattr(previous, "_catalog", None)
        _install_impact_stub(self.catalog)

    def tearDown(self):
        if self._previous is not None:
            import impact.wildcards as wildcards

            wildcards._catalog = self._previous

    def test_skip_in_the_middle_matches_oracle_punctuation(self):
        from forge_uw_wildcards.clauses import SKIP_OVERRIDE_SENTINEL, expand_with_overrides

        expected = _oracle_expand(PUNCT_TAG, 1, age_override=SKIP_OVERRIDE_SENTINEL)
        actual = expand_with_overrides(
            PUNCT_TAG,
            1,
            catalog=self.catalog,
            age_override=SKIP_OVERRIDE_SENTINEL,
        )
        self.assertEqual(actual, expected)
        self.assertNotIn(",,", actual)
        self.assertNotIn(", .", actual)
        self.assertNotRegex(actual, r"\w\.,")
        self.assertNotIn("around twenty", actual)

    def test_skip_before_a_period_does_not_glue_it(self):
        from forge_uw_wildcards.clauses import SKIP_OVERRIDE_SENTINEL, expand_with_overrides

        import impact.wildcards as wildcards

        catalog = _punct_catalog("BODY, __uw-shared/common/age/nsfw-default__.")
        wildcards._catalog = catalog
        expected = _oracle_expand(PUNCT_TAG, 1, age_override=SKIP_OVERRIDE_SENTINEL)
        actual = expand_with_overrides(
            PUNCT_TAG,
            1,
            catalog=catalog,
            age_override=SKIP_OVERRIDE_SENTINEL,
        )
        self.assertEqual(actual, expected)
        self.assertNotIn(", .", actual)
        self.assertNotRegex(actual, r"\w\.,")
        self.assertEqual(actual, "BODY.")

    def test_without_skip_punctuation_matches_oracle(self):
        from forge_uw_wildcards.clauses import expand_with_overrides

        expected = _oracle_expand(PUNCT_TAG, 1)
        actual = expand_with_overrides(PUNCT_TAG, 1, catalog=self.catalog)
        self.assertEqual(actual, expected)
        self.assertIn("athletic, around twenty, end.", actual)


class SyntaxTests(unittest.TestCase):
    def test_weight_prefix_is_stripped_before_the_nested_tag(self):
        from forge_uw_wildcards.clauses import expand_with_overrides

        catalog = {
            "uw-krea2-nsfw/leaf/demo/medium": ["2::__uw-shared/common/treatment/natural__"],
            "uw-shared/common/treatment/natural": ["candid snapshot finish"],
        }
        text = expand_with_overrides(
            "__uw-krea2-nsfw/leaf/demo/medium__", 1, catalog=catalog
        )
        self.assertEqual(text, "candid snapshot finish")

    def test_brace_resolves_to_one_option_and_stays_put(self):
        from forge_uw_wildcards.clauses import expand_with_overrides

        catalog = {
            "uw-krea2-nsfw/leaf/demo/medium": ["eyes {blue|green|brown}"],
        }
        first = expand_with_overrides(
            "__uw-krea2-nsfw/leaf/demo/medium__", 3, catalog=catalog
        )
        second = expand_with_overrides(
            "__uw-krea2-nsfw/leaf/demo/medium__", 3, catalog=catalog
        )
        self.assertEqual(first, second)
        self.assertIn(first, {"eyes blue", "eyes green", "eyes brown"})

    def test_brace_changes_with_the_seed(self):
        from forge_uw_wildcards.clauses import expand_with_overrides

        catalog = {
            "uw-krea2-nsfw/leaf/demo/medium": ["eyes {blue|green|brown}"],
        }
        seen = {
            expand_with_overrides("__uw-krea2-nsfw/leaf/demo/medium__", seed, catalog=catalog)
            for seed in range(24)
        }
        self.assertGreater(len(seen), 1)

    def test_heavier_line_wins_more_often(self):
        from forge_uw_wildcards.clauses import expand_with_overrides

        catalog = {
            "uw-krea2-nsfw/leaf/demo/medium": ["9::HEAVY", "1::LIGHT"],
        }
        seen = [
            expand_with_overrides("__uw-krea2-nsfw/leaf/demo/medium__", seed, catalog=catalog)
            for seed in range(40)
        ]
        self.assertGreater(seen.count("HEAVY"), seen.count("LIGHT"))
        self.assertTrue(set(seen) <= {"HEAVY", "LIGHT"})

    def test_brace_expands_the_chosen_tag(self):
        from forge_uw_wildcards.clauses import expand_with_overrides

        catalog = {
            "uw-krea2-nsfw/leaf/demo/medium": [
                "{__uw-shared/common/eye-color/blue__|__uw-shared/common/eye-color/green__}"
            ],
            "uw-shared/common/eye-color/blue": ["blue eyes"],
            "uw-shared/common/eye-color/green": ["green eyes"],
        }
        text = expand_with_overrides(
            "__uw-krea2-nsfw/leaf/demo/medium__", 5, catalog=catalog
        )
        self.assertIn(text, {"blue eyes", "green eyes"})

    def test_reroll_does_not_change_a_brace_inside_another_slot(self):
        from forge_uw_wildcards.clauses import expand_with_overrides

        catalog = {
            "uw-krea2-nsfw/template/slot-demo": [
                "__uw-krea2-nsfw/leaf/demo/lighting__, __uw-shared/common/hair/grp1__"
            ],
            "uw-krea2-nsfw/leaf/demo/lighting": list(LIGHTING),
            "uw-shared/common/hair/grp1": ["hair {bob|braid|pixie|curl}"],
        }
        base = expand_with_overrides(SLOT_TAG, 4, catalog=catalog)
        rerolled = expand_with_overrides(
            SLOT_TAG, 4, catalog=catalog, counters={"lighting": 1}
        )
        self.assertNotIn("{", base)
        self.assertEqual(base.split(", ", 1)[1], rerolled.split(", ", 1)[1])
        self.assertNotEqual(base.split(", ", 1)[0], rerolled.split(", ", 1)[0])


if __name__ == "__main__":
    unittest.main()
