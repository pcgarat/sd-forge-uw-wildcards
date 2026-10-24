import sys
from pathlib import Path

import gradio as gr

from modules import script_callbacks, scripts, shared
from modules.paths import models_path
from modules.ui_components import InputAccordion

from forge_uw_wildcards.api_key import resolve_civitai_api_key
from forge_uw_wildcards.catalog import list_selectable_tags, load_catalog, wildcard_root
from forge_uw_wildcards.inspector import collect_slots, seed_choice, status_line
from forge_uw_wildcards.lora_fetch import ensure_prompt_loras, load_manifest, lora_directories, urllib_open
from forge_uw_wildcards.render import render_prompts
from forge_uw_wildcards.state import SLOT_LABELS, parse_state, pin, regenerate, set_tag, skip

EXT_DIR = Path(scripts.basedir())
_MANIFEST = load_manifest(EXT_DIR / "forge_uw_wildcards" / "manifest.json")

def _seed_read_js(elem_id):
    """Lee el campo Seed del tab al pulsar; el espejo oculto lo transporta al backend."""
    selector = f"#{elem_id} input, #{elem_id} textarea"
    return (
        "(enable, raw, probe) => [enable, raw, "
        f"(gradioApp().querySelector('{selector}') || {{}}).value ?? '']"
    )


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

    def __init__(self):
        self.last_seed = None
        self.last_total = 1
        self._per_image: list[str] = []

    def title(self):
        return "UW Wildcards"

    def show(self, is_img2img):
        return scripts.AlwaysVisible

    def _wildcard_root(self):
        return wildcard_root(getattr(shared, "data_path", None), EXT_DIR)

    def ui(self, is_img2img):
        with InputAccordion(False, label=self.title(), elem_id=self.elem_id("enable")) as enable:
            gr.HTML(
                "<div>Elige un router o una plantilla. Al generar, el prompt queda en prosa, "
                "sin <code>__uw-krea2-nsfw/</code> ni un <code>[W:H]</code> final. "
                "Fijar, omitir y regenerar solo cambian el JSON de cláusulas.</div>"
            )
            clause_state = gr.Textbox(
                value="{}",
                visible=False,
                elem_id=self.elem_id("state"),
                label="UW cláusulas",
            )
            seed_probe = gr.Textbox(
                value="",
                visible=False,
                elem_id=self.elem_id("seed_probe"),
                label="UW semilla del tab",
            )

            with gr.Row():
                preview = gr.Button("Ver lo generado", elem_id=self.elem_id("preview"))
                clear = gr.Button("Vaciar", elem_id=self.elem_id("clear"))
            status = gr.Markdown("", elem_id=self.elem_id("preview_status"))

            tag = gr.Dropdown(
                label="Router o plantilla",
                choices=list_selectable_tags(self._wildcard_root()),
                elem_id=self.elem_id("tag"),
            )
            refresh = gr.Button("Recargar lista", elem_id=self.elem_id("reload"))
            refresh.click(
                lambda: gr.update(choices=list_selectable_tags(self._wildcard_root())),
                outputs=[tag],
            )
            tag.change(set_tag, inputs=[clause_state, tag], outputs=[clause_state])
            boxes = []
            for kind, label in SLOT_LABELS:
                box = gr.Textbox(label=label, lines=2, elem_id=self.elem_id(kind))
                boxes.append(box)
                with gr.Row():
                    pin_button = gr.Button("Fijar")
                    skip_button = gr.Button("Omitir")
                    roll_button = gr.Button("Regenerar")
                kind_state = gr.State(kind)
                pin_button.click(pin, inputs=[clause_state, kind_state, box], outputs=[clause_state])
                skip_button.click(skip, inputs=[clause_state, kind_state], outputs=[clause_state])
                roll_button.click(
                    lambda raw, slot: (regenerate(raw, slot), ""),
                    inputs=[clause_state, kind_state],
                    outputs=[clause_state, box],
                )

            def on_preview(enabled, raw, mirror):
                if not enabled:
                    return [gr.skip()] * len(boxes) + [""]
                choice = seed_choice(mirror, self.last_seed)
                if choice is None:
                    return [gr.skip()] * len(boxes) + [status_line(None)]
                slots = collect_slots(
                    load_catalog(self._wildcard_root()), parse_state(raw), choice.seed
                )
                values = [slots.get(kind, "") for kind, _label in SLOT_LABELS]
                return values + [status_line(choice, self.last_total)]

            preview.click(
                on_preview,
                inputs=[enable, clause_state, seed_probe],
                outputs=[*boxes, status],
                _js=_seed_read_js(f"{self.tabname}_seed"),
                show_progress=False,
            )
            clear.click(
                lambda: [""] * len(boxes) + [""],
                outputs=[*boxes, status],
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
        self.infotext_fields = [(clause_state, "UW Wildcards")]
        self.paste_field_names = ["UW Wildcards"]
        return [enable, apply_aspect, megapixels, default_ar, divisible, fetch, clause_state]

    def process(
        self,
        processing,
        enable,
        apply_aspect,
        megapixels,
        default_ar,
        divisible,
        fetch,
        clause_state,
    ):
        if not enable:
            self._per_image = []
            return
        prompts = list(processing.all_prompts)
        seeds = [int(seed) for seed in processing.all_seeds]
        rewritten, size = render_prompts(
            prompts,
            clause_state or "{}",
            catalog=load_catalog(self._wildcard_root()),
            seeds=seeds,
            apply_aspect=bool(apply_aspect),
            megapixels=float(megapixels),
            default_aspect_ratio=default_ar or "3:4",
            divisible_by=int(divisible),
        )

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

        rewritten = [rewrite(item) for item in rewritten]
        processing.all_prompts = rewritten
        processing.prompt = rewritten[0] if rewritten else ""
        if getattr(processing, "main_prompt", None) is not None:
            processing.main_prompt = processing.prompt
        self._inherit_hires_prompts(processing, prompts, rewritten)
        self._per_image = list(rewritten)
        if getattr(processing, "negative_prompt", None):
            processing.negative_prompt = rewrite(processing.negative_prompt)
        if getattr(processing, "all_negative_prompts", None):
            processing.all_negative_prompts = [rewrite(item) for item in processing.all_negative_prompts]
        if size is not None:
            processing.width = size[0]
            processing.height = size[1]
        extra = getattr(processing, "extra_generation_params", None)
        if not isinstance(extra, dict):
            processing.extra_generation_params = {}
        processing.extra_generation_params["UW Wildcards"] = clause_state or "{}"
        self.last_seed = seeds[0] if seeds else None
        self.last_total = len(rewritten) or 1
        _reload_lora_networks()

    def before_process_batch(self, p, *args, **kwargs):
        """Dynamic Prompts, que corre después, rehace all_prompts desde el primero.

        Si no cambió el texto, se recupera la variación por semilla; si lo cambió,
        manda su versión y no se pisa.
        """
        per_image = self._per_image
        if not per_image or len(per_image) != len(p.all_prompts):
            return
        if not p.all_prompts or p.all_prompts[0] != per_image[0]:
            return
        p.all_prompts = list(per_image)
        if len(p.prompts) == len(per_image):
            p.prompts = list(per_image)

    @staticmethod
    def _inherit_hires_prompts(processing, originals, rewritten):
        """setup_prompts copió el prompt sin expandir al de hires; solo se hereda el propio."""
        hires = getattr(processing, "all_hr_prompts", None)
        if not isinstance(hires, list) or len(hires) != len(originals):
            return
        processing.all_hr_prompts = [
            new if old == original else old
            for old, original, new in zip(hires, originals, rewritten)
        ]
        if getattr(processing, "hr_prompt", None) in originals:
            processing.hr_prompt = processing.all_hr_prompts[0]


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
