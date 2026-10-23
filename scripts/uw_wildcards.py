import sys
from pathlib import Path

import gradio as gr

from modules import script_callbacks, scripts, shared
from modules.paths import models_path
from modules.ui_components import InputAccordion

from forge_uw_wildcards.api_key import resolve_civitai_api_key
from forge_uw_wildcards.aspect import process_prompt_aspect_size
from forge_uw_wildcards.lora_fetch import ensure_prompt_loras, load_manifest, lora_directories, urllib_open

EXT_DIR = Path(scripts.basedir())
_MANIFEST = load_manifest(EXT_DIR / "forge_uw_wildcards" / "manifest.json")


def _reload_lora_networks():
    for module in list(sys.modules.values()):
        if not getattr(module, "__name__", "").endswith("networks"):
            continue
        refresh = getattr(module, "list_available_networks", None)
        if callable(refresh):
            refresh()
            return


class UWWildcards(scripts.Script):
    sorting_priority = 20

    def title(self):
        return "UW Wildcards"

    def show(self, is_img2img):
        return scripts.AlwaysVisible

    def ui(self, is_img2img):
        with InputAccordion(False, label=self.title(), elem_id=self.elem_id("enable")) as enable:
            gr.HTML(
                "<div>Quita un <code>[W:H]</code> final del prompt y, si faltan, "
                "descarga las LoRA del pack en la carpeta de LoRA de Forge, "
                "dentro de <code>UWModularWildcards</code>.</div>"
            )
            apply_aspect = gr.Checkbox(
                True, label="Aplicar marcador de aspecto", elem_id=self.elem_id("aspect")
            )
            megapixels = gr.Slider(
                0.25, 2.0, value=1.0, step=0.05, label="Megapíxeles", elem_id=self.elem_id("mp")
            )
            default_ar = gr.Textbox(
                value="3:4", label="Relación si no hay marcador", elem_id=self.elem_id("ar")
            )
            divisible = gr.Slider(
                8, 64, value=16, step=8, label="Múltiplo de ancho y alto", elem_id=self.elem_id("div")
            )
            fetch = gr.Checkbox(
                True, label="Descargar LoRA que falten", elem_id=self.elem_id("fetch")
            )
        return [enable, apply_aspect, megapixels, default_ar, divisible, fetch]

    def before_process(self, processing, enable, apply_aspect, megapixels, default_ar, divisible, fetch):
        if not enable:
            return
        directories = lora_directories(shared.cmd_opts, models_path)
        domain = "civitai.com" if getattr(shared.opts, "civitai_sfw_only", False) else "civitai.red"
        proxy = (getattr(shared.opts, "custom_civitai_proxy", "") or "").strip()

        def on_download(alias):
            shared.state.job = f"UW Wildcards: descargando {alias}"

        def rewrite(text):
            return ensure_prompt_loras(
                text,
                lora_dirs=directories,
                manifest=_MANIFEST,
                api_key=resolve_civitai_api_key(shared.opts),
                domain=domain,
                proxy=proxy,
                fetch_missing=bool(fetch),
                open_request=urllib_open,
                on_download=on_download,
            )

        processing.prompt = rewrite(processing.prompt or "")
        if getattr(processing, "all_prompts", None):
            processing.all_prompts = [rewrite(item) for item in processing.all_prompts]
        if getattr(processing, "negative_prompt", None):
            processing.negative_prompt = rewrite(processing.negative_prompt)
        if getattr(processing, "all_negative_prompts", None):
            processing.all_negative_prompts = [rewrite(item) for item in processing.all_negative_prompts]
        _reload_lora_networks()

        if not apply_aspect:
            return
        step = int(divisible)
        ratio = default_ar or "3:4"
        cleaned, width, height, _detected = process_prompt_aspect_size(
            processing.prompt or "", float(megapixels), ratio, step
        )
        processing.prompt = cleaned
        processing.width = int(width)
        processing.height = int(height)
        if getattr(processing, "all_prompts", None):
            processing.all_prompts = [
                process_prompt_aspect_size(item, float(megapixels), ratio, step)[0]
                for item in processing.all_prompts
            ]


def on_ui_settings():
    shared.opts.add_option(
        "uw_wildcards_civitai_api_key",
        shared.OptionInfo(
            default="",
            label="CivitAI API key",
            component=gr.Textbox,
            component_args={"type": "password"},
            section=("uw_wildcards", "UW Wildcards"),
        ).info(
            "Solo se usa si CivitAI Browser Neo no tiene ya Personal CivitAI API key."
        ),
    )


script_callbacks.on_ui_settings(on_ui_settings)
