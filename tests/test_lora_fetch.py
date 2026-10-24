import http.client
import json
import time
import unittest
import urllib.error
from pathlib import Path
from tempfile import TemporaryDirectory

from forge_uw_wildcards.lora_fetch import (
    HttpResult,
    LoraFetchError,
    _stream_to,
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

    def test_redirect_to_a_foreign_host_drops_the_api_key(self):
        calls = []

        def open_request(url, headers, proxy):
            calls.append((url, dict(headers)))
            if "civitai.red" in url:
                return HttpResult(302, {"location": "https://cdn.example/weights.safetensors"}, b"")
            return HttpResult(200, {"content-type": "application/octet-stream"}, b"weights")

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            text = ensure_prompt_loras(
                TAG,
                lora_dirs=[root],
                manifest=MANIFEST,
                api_key="secret",
                domain="civitai.red",
                proxy="",
                fetch_missing=True,
                open_request=open_request,
            )
            dest = root / "UWModularWildcards" / f"{ALIAS}.safetensors"
            self.assertEqual(dest.read_bytes(), b"weights")
            self.assertIn(f"<lora:UWModularWildcards/{ALIAS}:0.6>", text)

        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0][1]["Authorization"], "Bearer secret")
        self.assertNotIn("Authorization", calls[1][1])
        self.assertEqual(calls[1][1]["User-Agent"], "sd-forge-uw-wildcards")
        self.assertTrue(calls[1][0].startswith("https://cdn.example/"))

    def test_http_redirect_is_rejected_without_a_second_request(self):
        calls = []

        def open_request(url, headers, proxy):
            calls.append((url, dict(headers)))
            return HttpResult(302, {"location": "http://cdn.example/weights.safetensors"}, b"")

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(LoraFetchError) as caught:
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
            self.assertIn("https", str(caught.exception))
            self.assertEqual(list(root.rglob("*.partial")), [])
            self.assertEqual(list(root.rglob("*.safetensors")), [])

        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][1]["Authorization"], "Bearer secret")

    def test_a_network_error_is_a_lora_fetch_error_and_leaves_no_partial(self):
        def open_request(url, headers, proxy):
            raise urllib.error.URLError("offline")

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(LoraFetchError) as caught:
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
            self.assertIn("conectar", str(caught.exception))
            self.assertEqual(list(root.rglob("*.partial")), [])

    def test_a_streamed_body_is_moved_into_place_without_using_the_buffer(self):
        def open_request(url, headers, proxy, dest=None):
            dest.write_bytes(b"weights")
            return HttpResult(200, {"content-type": "application/octet-stream"}, b"", stored=True)

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
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
            dest = root / "UWModularWildcards" / f"{ALIAS}.safetensors"
            self.assertEqual(dest.read_bytes(), b"weights")

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


class StreamTests(unittest.TestCase):
    def test_short_body_is_an_incomplete_read(self):
        class Reader:
            def __init__(self):
                self.parts = [b"ab"]

            def read(self, _size):
                if not self.parts:
                    return b""
                return self.parts.pop(0)

        with TemporaryDirectory() as tmp:
            dest = Path(tmp) / "weights.partial"
            with self.assertRaises(http.client.IncompleteRead):
                _stream_to(Reader(), dest, time.monotonic() + 5, b"a", 4)

    def test_past_deadline_stops_the_copy(self):
        class Reader:
            def read(self, _size):
                return b"more"

        with TemporaryDirectory() as tmp:
            dest = Path(tmp) / "weights.partial"
            with self.assertRaises(TimeoutError):
                _stream_to(Reader(), dest, time.monotonic() - 1, b"a", None)


class ShippedManifestTests(unittest.TestCase):
    def test_every_alias_pins_the_card_version(self):
        path = Path(__file__).resolve().parents[1] / "forge_uw_wildcards" / "manifest.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        expected = {
            "krea2/nsfw/snofs_krea_v1_3D": (1972981, 3220691),
            "krea2/sliders/slider-photo__Photo_Detail_Slider_for_SNOFS_Krea": (2823820, 3185533),
            "krea2/styles/photoreal/style-photoreal__Realism_Engine_Ideogram_4_Krea_2": (2688234, 3109006),
            "krea2/styles/photoreal/style-photoreal__Mrpopo_Photoreal_Enhanced": (2765038, 3214145),
            "krea2/face/face-expression__Snapchat_Face_Helper": (2853869, 3223062),
            "krea2/nsfw/acts/nsfw-act-masturbation__krea2_sex": (2801881, 3170098),
            "krea2/nsfw/acts/nsfw-act__krea2_sex_淫模_krea2_dildo_in_pussy": (2801881, 3170017),
        }
        self.assertEqual(set(data), set(expected))
        for alias, (model_id, version_id) in expected.items():
            self.assertEqual((data[alias]["model_id"], data[alias]["version_id"]), (model_id, version_id))


if __name__ == "__main__":
    unittest.main()
