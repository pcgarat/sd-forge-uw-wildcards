import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from forge_uw_wildcards.lora_fetch import (
    HttpResult,
    LoraFetchError,
    ensure_prompt_loras,
    lora_directories,
)


ALIAS = "krea2/nsfw/snofs_krea_v1_3D"
TAG = f"<lora:{ALIAS}:0.6>"
MANIFEST = {
    ALIAS: {"model_id": 1972981, "version_id": 3220691},
    "krea2/styles/photoreal/style-photoreal__Mrpopo_Photoreal_Enhanced": {
        "model_id": None,
        "version_id": None,
    },
}


class _Opts:
    def __init__(self, lora_dir=None, lora_dirs=None):
        self.lora_dir = lora_dir
        self.lora_dirs = lora_dirs


class LoraDirectoryTests(unittest.TestCase):
    def test_primary_is_lora_dir_then_lora_dirs_then_models(self):
        dirs = lora_directories(_Opts(lora_dir="/loras", lora_dirs=["/extra", "/loras"]), "/models")
        self.assertEqual(dirs, [Path("/loras"), Path("/extra")])

    def test_fallback_is_models_lora(self):
        dirs = lora_directories(_Opts(), "/models")
        self.assertEqual(dirs, [Path("/models") / "Lora"])


class EnsureLorasTests(unittest.TestCase):
    def test_downloads_into_subfolder_and_rewrites_the_tag(self):
        calls = []

        def open_request(url, headers, proxy):
            calls.append((url, headers, proxy))
            return HttpResult(200, {"content-type": "application/octet-stream"}, b"weights")

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            text = ensure_prompt_loras(
                f"{TAG} hello <lora:mine:1>",
                lora_dirs=[root],
                manifest=MANIFEST,
                api_key="secret",
                domain="civitai.red",
                proxy="",
                fetch_missing=True,
                open_request=open_request,
            )
            dest = root / "UWModularWildcards" / f"{ALIAS}.safetensors"
            self.assertTrue(dest.is_file())
            self.assertEqual(dest.read_bytes(), b"weights")
            self.assertIn(f"<lora:UWModularWildcards/{ALIAS}:0.6>", text)
            self.assertIn("<lora:mine:1>", text)
            self.assertEqual(len(calls), 1)
            self.assertIn("/api/download/models/3220691", calls[0][0])
            self.assertEqual(calls[0][1]["Authorization"], "Bearer secret")

            ensure_prompt_loras(
                TAG,
                lora_dirs=[root],
                manifest=MANIFEST,
                api_key="secret",
                domain="civitai.red",
                proxy="",
                fetch_missing=True,
                open_request=open_request,
            )
            self.assertEqual(len(calls), 1)

    def test_existing_file_in_a_secondary_dir_skips_download(self):
        def open_request(url, headers, proxy):
            raise AssertionError("no debía descargar")

        with TemporaryDirectory() as primary, TemporaryDirectory() as secondary:
            dest = Path(secondary) / "UWModularWildcards" / f"{ALIAS}.safetensors"
            dest.parent.mkdir(parents=True)
            dest.write_bytes(b"already")
            text = ensure_prompt_loras(
                TAG,
                lora_dirs=[Path(primary), Path(secondary)],
                manifest=MANIFEST,
                api_key="secret",
                domain="civitai.red",
                proxy="",
                fetch_missing=True,
                open_request=open_request,
            )
            self.assertIn(f"<lora:UWModularWildcards/{ALIAS}:0.6>", text)
            self.assertFalse((Path(primary) / "UWModularWildcards" / f"{ALIAS}.safetensors").exists())

    def test_missing_version_id_does_not_leave_a_partial(self):
        def open_request(url, headers, proxy):
            raise AssertionError("no debía llamar a Civitai")

        alias = "krea2/styles/photoreal/style-photoreal__Mrpopo_Photoreal_Enhanced"
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(LoraFetchError) as caught:
                ensure_prompt_loras(
                    f"<lora:{alias}:0.6>",
                    lora_dirs=[root],
                    manifest=MANIFEST,
                    api_key="secret",
                    domain="civitai.red",
                    proxy="",
                    fetch_missing=True,
                    open_request=open_request,
                )
            self.assertIn(alias, str(caught.exception))
            self.assertEqual(list(root.rglob("*")), [])

    def test_login_redirect_names_sfw_mode_and_removes_partial(self):
        def open_request(url, headers, proxy):
            if url.endswith("/3220691"):
                return HttpResult(302, {"location": "https://civitai.com/login?returnUrl=%2Fapi"}, b"")
            raise AssertionError(url)

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(LoraFetchError) as caught:
                ensure_prompt_loras(
                    TAG,
                    lora_dirs=[root],
                    manifest=MANIFEST,
                    api_key="secret",
                    domain="civitai.com",
                    proxy="",
                    fetch_missing=True,
                    open_request=open_request,
                )
            message = str(caught.exception)
            self.assertIn(ALIAS, message)
            self.assertIn("SFW only", message)
            self.assertEqual(list(root.rglob("*.partial")), [])

    def test_fetch_disabled_leaves_a_missing_tag_unchanged(self):
        def open_request(url, headers, proxy):
            raise AssertionError("no debía descargar")

        text = ensure_prompt_loras(
            TAG,
            lora_dirs=[Path("/no/such")],
            manifest=MANIFEST,
            api_key="secret",
            domain="civitai.red",
            proxy="",
            fetch_missing=False,
            open_request=open_request,
        )
        self.assertEqual(text, TAG)


if __name__ == "__main__":
    unittest.main()
