import unittest

from forge_uw_wildcards.aspect import process_prompt_aspect_size


class AspectTests(unittest.TestCase):
    def test_trailing_marker_sets_3_by_4_at_one_megapixel(self):
        text, width, height, detected = process_prompt_aspect_size(
            "a portrait [3:4]",
            megapixels=1.0,
            default_aspect_ratio="16:9",
            divisible_by=16,
        )
        self.assertEqual(text, "a portrait")
        self.assertEqual((width, height), (864, 1152))
        self.assertEqual(detected, "3:4")
        self.assertEqual(width % 16, 0)
        self.assertEqual(height % 16, 0)

    def test_missing_marker_uses_default_ratio(self):
        text, width, height, detected = process_prompt_aspect_size(
            "a portrait",
            megapixels=1.0,
            default_aspect_ratio="3:4",
            divisible_by=16,
        )
        self.assertEqual(text, "a portrait")
        self.assertEqual((width, height), (864, 1152))
        self.assertEqual(detected, "3:4")

    def test_marker_in_the_middle_is_kept(self):
        text, width, height, detected = process_prompt_aspect_size(
            "a [3:4] portrait",
            megapixels=1.0,
            default_aspect_ratio="16:9",
            divisible_by=16,
        )
        self.assertEqual(text, "a [3:4] portrait")
        self.assertEqual(detected, "16:9")
        self.assertNotEqual((width, height), (864, 1152))

    def test_json_braces_are_restored_before_the_marker_is_read(self):
        text, _, _, _ = process_prompt_aspect_size(
            "[[[subject]]]: a woman [9:16]",
            megapixels=1.0,
        )
        self.assertEqual(text, "{subject}: a woman")


if __name__ == "__main__":
    unittest.main()
