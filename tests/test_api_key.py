import unittest
from types import SimpleNamespace

from forge_uw_wildcards.api_key import resolve_civitai_api_key


class ResolveApiKeyTests(unittest.TestCase):
    def test_browser_key_wins_when_both_are_set(self):
        opts = SimpleNamespace(
            data={"custom_api_key": "  browser  "},
            custom_api_key="browser",
            uw_wildcards_civitai_api_key="propia",
        )
        self.assertEqual(resolve_civitai_api_key(opts), "browser")

    def test_data_dict_is_enough_when_attribute_is_missing(self):
        opts = SimpleNamespace(
            data={"custom_api_key": "desde-config"},
            uw_wildcards_civitai_api_key="propia",
        )
        self.assertEqual(resolve_civitai_api_key(opts), "desde-config")

    def test_empty_browser_key_falls_back_to_ours(self):
        opts = SimpleNamespace(
            data={"custom_api_key": "   "},
            custom_api_key="",
            uw_wildcards_civitai_api_key="  propia  ",
        )
        self.assertEqual(resolve_civitai_api_key(opts), "propia")

    def test_both_empty_returns_blank(self):
        opts = SimpleNamespace(data={}, custom_api_key="", uw_wildcards_civitai_api_key="")
        self.assertEqual(resolve_civitai_api_key(opts), "")


if __name__ == "__main__":
    unittest.main()
