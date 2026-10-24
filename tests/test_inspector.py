import json
import unittest

from forge_uw_wildcards.clauses import SKIP_OVERRIDE_SENTINEL, expand_with_overrides
from forge_uw_wildcards.inspector import (
    SOURCE_FIELD,
    SOURCE_LAST,
    collect_slots,
    resolve_seed,
    seed_choice,
    status_line,
)
from forge_uw_wildcards.state import SLOT_LABELS, parse_state, pin, skip

TAG = "__uw-krea2-nsfw/template/inspector-demo__"

LEAVES = {
    "wardrobe": ("LEAF-WARDROBE-A", "LEAF-WARDROBE-B"),
    "environment": ("LEAF-ENV-A", "LEAF-ENV-B"),
    "medium": ("LEAF-MEDIUM-A", "LEAF-MEDIUM-B"),
    "lighting": ("LEAF-LIGHT-A", "LEAF-LIGHT-B"),
    "treatment": ("LEAF-TREAT-A", "LEAF-TREAT-B"),
}

ATOMS = {
    "hair": "common/hair/grp1",
    "body": "body-archetype/natural",
    "age": "common/age/nsfw-default",
    "eye_color": "eye-color/hazel",
    "nationality": "nationality/irish",
    "skin": "common/skin/freckled",
    "face": "face-features/oval",
    "jewelry": "piercing/ear",
    "skin_tone": "skin-tone/honey",
    "hair_color": "hair-color/auburn",
    "breast_size": "breast-size/medium",
    "butt_size": "butt-size/round",
}

OPTIONS = {kind: (f"{kind.upper()}-A", f"{kind.upper()}-B") for kind in ATOMS}


def _catalog():
    references = [f"__uw-krea2-nsfw/leaf/inspector-demo/{kind}__" for kind in LEAVES]
    references += [f"__uw-shared/{key}__" for key in ATOMS.values()]
    catalog = {"uw-krea2-nsfw/template/inspector-demo": [", ".join(references) + "."]}
    for kind, lines in LEAVES.items():
        catalog[f"uw-krea2-nsfw/leaf/inspector-demo/{kind}"] = list(lines)
    for kind, key in ATOMS.items():
        catalog[f"uw-shared/{key}"] = list(OPTIONS[kind])
    return catalog


def _state(**overrides):
    return {
        "tag": TAG,
        "overrides": dict(overrides),
        "counters": {},
    }


class CollectSlotsTests(unittest.TestCase):
    def setUp(self):
        self.catalog = _catalog()

    def test_every_label_gets_text_for_a_seed(self):
        slots = collect_slots(self.catalog, _state(), 7)
        self.assertEqual(
            sorted(slots),
            sorted(kind for kind, _label in SLOT_LABELS),
        )
        self.assertEqual(len(SLOT_LABELS), 17)
        self.assertTrue(all(text for text in slots.values()))

    def test_the_same_seed_gives_the_same_dictionary(self):
        self.assertEqual(
            collect_slots(self.catalog, _state(), 11),
            collect_slots(self.catalog, _state(), 11),
        )

    def test_a_pinned_slot_returns_the_pinned_text(self):
        state = parse_state(pin(json.dumps(_state()), "hair", "long silver hair"))
        slots = collect_slots(self.catalog, state, 3)
        self.assertEqual(slots["hair"], "long silver hair")
        self.assertIn(slots["age"], OPTIONS["age"])

    def test_a_skipped_slot_is_absent_and_the_sentinel_never_shows(self):
        state = parse_state(skip(json.dumps(_state()), "lighting"))
        slots = collect_slots(self.catalog, state, 3)
        self.assertNotIn("lighting", slots)
        for text in slots.values():
            self.assertNotIn(SKIP_OVERRIDE_SENTINEL, text)
        self.assertNotIn("LEAF-LIGHT", json.dumps(slots))

    def test_the_counter_moves_the_hair_and_not_the_age(self):
        base = collect_slots(self.catalog, _state(), 5)
        for counter in range(1, 5):
            state = _state()
            state["counters"] = {"hair": counter}
            moved = collect_slots(self.catalog, state, 5)
            self.assertEqual(moved["age"], base["age"])
            self.assertEqual(moved["lighting"], base["lighting"])
            if moved["hair"] != base["hair"]:
                break
        else:
            self.fail("ningún contador de pelo cambió el pelo")

    def test_an_empty_tag_collects_nothing(self):
        self.assertEqual(collect_slots(self.catalog, {"tag": "", "overrides": {}}, 1), {})


class TraceTests(unittest.TestCase):
    def test_trace_does_not_change_the_text(self):
        catalog = _catalog()
        trace = {}
        with_trace = expand_with_overrides(TAG, 42, catalog=catalog, trace=trace)
        without = expand_with_overrides(TAG, 42, catalog=catalog)
        self.assertEqual(with_trace, without)
        self.assertEqual(
            {kind: trace[kind] for kind, _label in SLOT_LABELS if kind in trace},
            collect_slots(catalog, _state(), 42),
        )

    def test_a_traced_value_is_the_final_text(self):
        catalog = {
            "uw-krea2-nsfw/leaf/inspector-demo/medium": ["eyes {blue|green|brown}"],
        }
        trace = {}
        text = expand_with_overrides(
            "__uw-krea2-nsfw/leaf/inspector-demo/medium__",
            3,
            catalog=catalog,
            trace=trace,
        )
        self.assertEqual(text, trace["medium"])
        self.assertIn(trace["medium"], {"eyes blue", "eyes green", "eyes brown"})

    def test_an_empty_pick_is_not_traced(self):
        catalog = {
            "uw-krea2-nsfw/leaf/inspector-demo/medium": ["BODY", "BODY"],
        }
        trace = {}
        expand_with_overrides(
            "__uw-krea2-nsfw/leaf/inspector-demo/medium__",
            1,
            catalog=catalog,
            trace=trace,
        )
        self.assertEqual(trace, {"medium": "BODY"})


class SeedTests(unittest.TestCase):
    def test_a_number_in_the_field_wins_over_the_last_generation(self):
        choice = seed_choice("1234", 3196705980)
        self.assertEqual(choice.seed, 1234)
        self.assertEqual(choice.source, SOURCE_FIELD)
        self.assertEqual(resolve_seed("1234", 3196705980), 1234)

    def test_minus_one_falls_back_to_the_last_generation(self):
        choice = seed_choice("-1", 3196705980)
        self.assertEqual(choice.seed, 3196705980)
        self.assertEqual(choice.source, SOURCE_LAST)
        self.assertEqual(resolve_seed("-1", 3196705980), 3196705980)

    def test_without_sources_there_is_no_seed(self):
        self.assertIsNone(resolve_seed("-1", None))
        self.assertIsNone(resolve_seed("", None))
        self.assertIsNone(resolve_seed("not a number", None))
        self.assertIsNone(seed_choice("-1", None))

    def test_zero_is_a_valid_seed_from_the_field(self):
        choice = seed_choice(0, 9)
        self.assertEqual(choice.seed, 0)
        self.assertEqual(choice.source, SOURCE_FIELD)

    def test_the_status_line_names_the_source(self):
        self.assertIn("última generación", status_line(seed_choice("-1", 7)))
        self.assertIn("imagen 1 de 3", status_line(seed_choice("-1", 7), 3))
        self.assertIn("campo Seed", status_line(seed_choice("77", 7)))
        self.assertTrue(status_line(None))


if __name__ == "__main__":
    unittest.main()
