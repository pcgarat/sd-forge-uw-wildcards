import json
import tempfile
import unittest
from pathlib import Path

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "wildcards"


class CatalogTests(unittest.TestCase):
    def test_fixture_lists_router_and_template_only(self):
        from forge_uw_wildcards.catalog import list_selectable_tags

        tags = list_selectable_tags(FIXTURE)
        self.assertEqual(
            tags,
            [
                "__uw-krea2-nsfw/router/portrait-sport-pics__",
                "__uw-krea2-nsfw/template/theme-sport-volleyball-gym-lookback__",
            ],
        )

    def test_empty_directory_is_an_empty_list(self):
        from forge_uw_wildcards.catalog import list_selectable_tags, load_catalog

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(list_selectable_tags(root), [])
            self.assertEqual(load_catalog(root), {})

    def test_missing_directory_is_an_empty_list(self):
        from forge_uw_wildcards.catalog import list_selectable_tags

        self.assertEqual(list_selectable_tags(FIXTURE / "no-such"), [])


class StateTests(unittest.TestCase):
    def test_pin_skip_and_regenerate_only_touch_that_slot(self):
        from forge_uw_wildcards.clauses import SKIP_OVERRIDE_SENTINEL
        from forge_uw_wildcards.state import pin, regenerate, skip

        raw = json.dumps(
            {"tag": "__uw-krea2-nsfw/router/portrait-sport-pics__", "overrides": {}, "counters": {}}
        )
        pinned = json.loads(pin(raw, "hair", "long silver hair"))
        self.assertEqual(pinned["overrides"], {"hair": "long silver hair"})
        self.assertEqual(pinned["counters"], {})

        skipped = json.loads(skip(pinned and json.dumps(pinned), "age"))
        self.assertEqual(skipped["overrides"]["hair"], "long silver hair")
        self.assertEqual(skipped["overrides"]["age"], SKIP_OVERRIDE_SENTINEL)

        rolled = json.loads(regenerate(json.dumps(skipped), "lighting"))
        self.assertEqual(rolled["counters"], {"lighting": 1})
        self.assertEqual(rolled["overrides"]["hair"], "long silver hair")
        self.assertNotIn("lighting", rolled["overrides"])
        again = json.loads(regenerate(json.dumps(rolled), "lighting"))
        self.assertEqual(again["counters"]["lighting"], 2)
        self.assertEqual(again["counters"].get("hair", 0), 0)

    def test_regenerate_clears_a_pin_on_that_slot_only(self):
        from forge_uw_wildcards.state import pin, regenerate

        raw = pin("{}", "lighting", "noon light")
        raw = pin(raw, "hair", "braid")
        rolled = json.loads(regenerate(raw, "lighting"))
        self.assertNotIn("lighting", rolled["overrides"])
        self.assertEqual(rolled["overrides"]["hair"], "braid")
        self.assertEqual(rolled["counters"]["lighting"], 1)


class RenderTests(unittest.TestCase):
    def test_selected_tag_becomes_prose_and_drops_the_aspect_marker(self):
        from forge_uw_wildcards.catalog import load_catalog
        from forge_uw_wildcards.render import render_prompts

        catalog = {
            "uw-krea2-nsfw/template/theme-sport-volleyball-gym-lookback": [
                "A candid selfie photograph of. [3:4]"
            ],
        }
        state = json.dumps(
            {
                "tag": "__uw-krea2-nsfw/template/theme-sport-volleyball-gym-lookback__",
                "overrides": {},
                "counters": {},
            }
        )
        prompts, size = render_prompts(
            ["keep this [3:4]"],
            state,
            catalog=catalog,
            seeds=[7],
            apply_aspect=True,
            megapixels=1.0,
            default_aspect_ratio="3:4",
            divisible_by=16,
        )
        self.assertEqual(len(prompts), 1)
        self.assertNotIn("__uw-krea2-nsfw/", prompts[0])
        self.assertNotRegex(prompts[0], r"\[\d+:\d+\]")
        self.assertIn("keep this", prompts[0])
        self.assertIn("candid selfie", prompts[0])
        self.assertEqual(size, (864, 1152))
        self.assertEqual(load_catalog(FIXTURE)["uw-krea2-nsfw/leaf/theme-sport-volleyball-gym-lookback/medium"], ["A candid selfie photograph of"])

    def test_disabled_prompt_is_unchanged(self):
        from forge_uw_wildcards.render import render_prompts

        prompts, size = render_prompts(
            ["a portrait [3:4]"],
            "{}",
            catalog={},
            seeds=[1],
            apply_aspect=True,
            megapixels=1.0,
            default_aspect_ratio="3:4",
            divisible_by=16,
            enabled=False,
        )
        self.assertEqual(prompts, ["a portrait [3:4]"])
        self.assertIsNone(size)

    def test_batch_keeps_its_length(self):
        from forge_uw_wildcards.render import render_prompts

        state = json.dumps(
            {
                "tag": "__uw-krea2-nsfw/leaf/demo/medium__",
                "overrides": {"medium": "an illustration of"},
                "counters": {},
            }
        )
        catalog = {"uw-krea2-nsfw/leaf/demo/medium": ["unused"]}
        prompts, _size = render_prompts(
            ["one", "two"],
            state,
            catalog=catalog,
            seeds=[1, 2],
            apply_aspect=False,
            megapixels=1.0,
            default_aspect_ratio="3:4",
            divisible_by=16,
        )
        self.assertEqual(len(prompts), 2)
        self.assertTrue(all("an illustration of" in item for item in prompts))
        self.assertTrue(all("__" not in item for item in prompts))


if __name__ == "__main__":
    unittest.main()
