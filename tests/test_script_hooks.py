import importlib.util
import sys
import types
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

EXT = Path(__file__).resolve().parents[1]
ALIAS = "krea2/nsfw/snofs_krea_v1_3D"


def _module(name):
    module = sys.modules.get(name)
    if module is None:
        module = types.ModuleType(name)
        sys.modules[name] = module
    return module


def _install_forge_stubs():
    modules = _module("modules")
    scripts = _module("modules.scripts")
    shared = _module("modules.shared")
    paths = _module("modules.paths")
    ui = _module("modules.ui_components")
    callbacks = _module("modules.script_callbacks")
    modules.scripts = scripts
    modules.shared = shared
    modules.paths = paths
    modules.ui_components = ui
    modules.script_callbacks = callbacks

    scripts.basedir = lambda: str(EXT)
    scripts.AlwaysVisible = object()
    scripts.Script = type("Script", (), {})
    paths.models_path = "/models"

    class _OptionInfo:
        def __init__(self, *args, **kwargs):
            pass

        def info(self, *args, **kwargs):
            return self

    class _State:
        def __init__(self):
            self.textinfo = None
            self.job = ""
            self.interrupted = False

        def interrupt(self):
            self.interrupted = True

    shared.OptionInfo = _OptionInfo
    shared.state = _State()
    shared.opts = types.SimpleNamespace(
        civitai_sfw_only=False,
        custom_civitai_proxy="",
        data={},
        custom_api_key="",
        uw_wildcards_civitai_api_key="",
        add_option=lambda *args, **kwargs: None,
    )
    shared.cmd_opts = types.SimpleNamespace(lora_dir=None, lora_dirs=None)
    shared.data_path = None
    callbacks.on_ui_settings = lambda fn: None
    callbacks.on_infotext_pasted = lambda *args, **kwargs: None

    class _InputAccordion:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    ui.InputAccordion = _InputAccordion
    if "gradio" not in sys.modules:
        try:
            importlib.import_module("gradio")
        except ImportError:
            gradio = _module("gradio")
            gradio.Textbox = object
            for name in ("HTML", "Row", "Button", "Dropdown", "Markdown", "Checkbox", "Slider", "State"):
                setattr(gradio, name, lambda *args, **kwargs: None)
            gradio.skip = lambda: None
            gradio.update = lambda **kwargs: kwargs


def _load_script():
    _install_forge_stubs()
    name = "uw_wildcards_under_test"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, EXT / "scripts" / "uw_wildcards.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _processing(prompts, seeds, hr=None):
    return types.SimpleNamespace(
        all_prompts=list(prompts),
        all_seeds=list(seeds),
        all_subseeds=[9] * len(prompts),
        seed=-1,
        subseed=-1,
        prompt=prompts[0],
        main_prompt=prompts[0],
        negative_prompt="",
        all_negative_prompts=[""] * len(prompts),
        extra_generation_params={},
        all_hr_prompts=list(prompts if hr is None else hr),
        hr_prompt=(prompts if hr is None else hr)[0],
        prompts=[],
        batch_size=1,
        width=512,
        height=512,
    )


class ScriptHookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = _load_script()

    def setUp(self):
        shared = sys.modules["modules.shared"]
        shared.state.interrupted = False
        shared.state.textinfo = None
        shared.state.job = ""
        self._wildcards = TemporaryDirectory()
        root = Path(self._wildcards.name) / "wildcards"
        root.mkdir()
        shared.data_path = self._wildcards.name
        shared.cmd_opts.lora_dir = self._wildcards.name

    def tearDown(self):
        self._wildcards.cleanup()

    def _run(self, processing, fetch=False, clause_state="{}", apply_aspect=False):
        script = self.mod.UWWildcards()
        script.process(processing, True, apply_aspect, 1.0, "3:4", 16, fetch, clause_state)
        return script

    def test_resolved_seed_is_written_back_before_dynamic_prompts(self):
        processing = _processing(["a cat", "a dog"], [4242, 4243])
        self._run(processing)
        self.assertEqual(processing.seed, 4242)
        self.assertEqual(processing.subseed, 9)

    def test_failed_lora_download_interrupts_and_leaves_the_prompt(self):
        original = f"<lora:{ALIAS}:0.6> a cat"
        processing = _processing([original], [7])
        with self.assertLogs(self.mod.__name__, level="ERROR"):
            self._run(processing, fetch=True)
        state = sys.modules["modules.shared"].state
        self.assertTrue(state.interrupted)
        self.assertIn(ALIAS, state.textinfo)
        self.assertEqual(processing.all_prompts, [original])

    def test_later_batch_keeps_its_own_prose_and_hires_prompt(self):
        prompts = ["scene-0", "scene-1", "scene-2", "scene-3"]
        processing = _processing(prompts, [1, 2, 3, 4])
        script = self._run(processing)
        processing.all_prompts = ["scene-0"] * 4
        processing.all_hr_prompts = ["scene-0"] * 4
        processing.prompts = ["scene-0", "scene-0"]
        processing.batch_size = 2

        script.before_process_batch(processing, batch_number=0)
        self.assertEqual(processing.prompts, ["scene-0", "scene-1"])
        self.assertEqual(processing.all_hr_prompts, prompts)

        processing.prompts = ["scene-0", "scene-0"]
        script.before_process_batch(processing, batch_number=1)
        self.assertEqual(processing.prompts, ["scene-2", "scene-3"])
        self.assertEqual(processing.all_prompts, prompts)

    def test_template_is_stored_and_paste_puts_it_back_in_the_prompt(self):
        from forge_uw_wildcards.render import restore_pasted_prompt

        processing = _processing(["keep this"], [1])
        self._run(processing)
        self.assertEqual(processing.extra_generation_params["UW Template"], ["keep this"])
        parameters = {"Prompt": "the expanded prose", "UW Template": "keep this"}
        restore_pasted_prompt(parameters)
        self.assertEqual(parameters["Prompt"], "keep this")

    def test_img2img_without_a_marker_keeps_its_size(self):
        plain = _processing(["a portrait"], [1])
        plain.init_images = ["canvas"]
        plain.width = 640
        plain.height = 480
        self._run(plain, apply_aspect=True)
        self.assertEqual((plain.width, plain.height), (640, 480))

        marked = _processing(["a portrait [3:4]"], [1])
        marked.init_images = ["canvas"]
        marked.width = 640
        marked.height = 480
        self._run(marked, apply_aspect=True)
        self.assertEqual((marked.width, marked.height), (864, 1152))
        self.assertNotIn("[3:4]", marked.all_prompts[0])

    def test_a_collapsed_fixed_seed_redraws_every_image_with_that_seed(self):
        from forge_uw_wildcards.catalog import load_catalog
        from forge_uw_wildcards.clauses import expand_with_overrides

        root = Path(self._wildcards.name) / "wildcards"
        (root / "demo.yaml").write_text(
            "uw-demo/leaf/medium:\n  - ONE\n  - TWO\n  - THREE\n  - FOUR\n",
            encoding="utf-8",
        )
        catalog = load_catalog(root)
        tag = "__uw-demo/leaf/medium__"
        state = '{"tag":"__uw-demo/leaf/medium__"}'
        first = second = None
        for seed in range(30):
            drawn = expand_with_overrides(tag, seed, catalog=catalog)
            if first is None:
                first = (seed, drawn)
                continue
            if drawn != first[1]:
                second = seed
                break
        self.assertIsNotNone(second)
        processing = _processing([tag, tag], [first[0], second])
        script = self._run(processing, clause_state=state)
        self.assertNotEqual(processing.all_prompts[0], processing.all_prompts[1])
        processing.all_seeds = [first[0], first[0]]
        processing.all_prompts = [processing.all_prompts[0], processing.all_prompts[0]]
        processing.prompts = [processing.all_prompts[0], processing.all_prompts[0]]
        script.before_process_batch(processing, batch_number=0)
        self.assertEqual(processing.prompts, [first[1], first[1]])

    def test_download_status_is_cleared_when_the_fetch_fails(self):
        shared = sys.modules["modules.shared"]
        shared.state.job = "idle"
        original = self.mod.ensure_prompt_loras

        def boom(*args, **kwargs):
            shared.state.job = "UW Wildcards: descargando foo"
            raise self.mod.LoraFetchError("foo: fallo")

        self.mod.ensure_prompt_loras = boom
        try:
            processing = _processing(["a cat"], [1])
            with self.assertLogs(self.mod.__name__, level="ERROR"):
                self._run(processing, fetch=True)
        finally:
            self.mod.ensure_prompt_loras = original
        self.assertEqual(shared.state.job, "idle")
        self.assertTrue(shared.state.interrupted)
        self.assertIn("foo", shared.state.textinfo)

    def test_a_changed_first_prompt_is_left_to_dynamic_prompts(self):
        processing = _processing(["scene-0", "scene-1"], [1, 2])
        script = self._run(processing)
        processing.all_prompts = ["edited", "edited"]
        processing.prompts = ["edited", "edited"]
        script.before_process_batch(processing, batch_number=0)
        self.assertEqual(processing.prompts, ["edited", "edited"])
        self.assertEqual(processing.all_prompts, ["edited", "edited"])


if __name__ == "__main__":
    unittest.main()
