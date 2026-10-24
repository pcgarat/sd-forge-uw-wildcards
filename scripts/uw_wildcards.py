import logging
import sys
from pathlib import Path

import gradio as gr

from modules import script_callbacks, scripts, shared
from modules.paths import models_path
from modules.ui_components import InputAccordion

from forge_uw_wildcards.api_key import resolve_civitai_api_key
from forge_uw_wildcards.catalog import list_selectable_tags, load_catalog, wildcard_root
from forge_uw_wildcards.inspector import collect_slots, seed_choice, status_line
from forge_uw_wildcards.lora_fetch import (
    LoraFetchError,
    ensure_prompt_loras,
    load_manifest,
    lora_directories,
    urllib_open,
)
from forge_uw_wildcards.render import INFOTEXT_TEMPLATE, render_prompts, restore_pasted_prompt
from forge_uw_wildcards.state import SLOT_LABELS, parse_state, pin, regenerate, set_tag, skip

logger = logging.getLogger(__name__)

EXT_DIR = Path(scripts.basedir())
_MANIFEST = load_manifest(EXT_DIR / "forge_uw_wildcards" / "manifest.json")

def _seed_read_js(elem_id):
    """Lee el campo Seed del tab al pulsar; el espejo oculto lo transporta al backend."""
    selector = f"#{elem_id} input, #{elem_id} textarea"
    return (
        "(enable, raw, probe) => [enable, raw, "
        f"(gradioApp().querySelector('{selector}') || {{}}).value ?? '']"
    )


def _refresh_lora_listing():
    """Solo el registro de LoRA de Forge, y solo tras una descarga nueva."""
    for module in list(sys.modules.values()):
        refresh = getattr(module, "list_available_networks", None)
        aliases = getattr(module, "available_network_aliases", None)
        if callable(refresh) and isinstance(aliases, dict):
            refresh()
            return


def _restore_download_job(previous):
    job = getattr(shared.state, "job", "")
    if isinstance(job, str) and job.startswith("UW Wildcards: descargando"):
        shared.state.job = previous


def _is_img2img(processing) -> bool:
    return getattr(processing, "init_images", None) is not None


def _on_infotext_pasted(_infotext, parameters):
    if isinstance(parameters, dict):
        restore_pasted_prompt(parameters)


script_callbacks.on_infotext_pasted(_on_infotext_pasted, name="uw_template")


class UWWildcards(scripts.Script):
    sorting_priority = 20

    def __init__(self):
        self.last_seed = None
        self.last_total = 1
        self._per_image: list[str] = []
        self._per_image_hr: list[str] = []
        self._sources: list[str] = []
        self._seeds: list[int] = []
        self._hr_sources: list[str] | None = None
        self._draw = None

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
            self._clear_draw()
            return
        prompts = list(processing.all_prompts)
        seeds = [int(seed) for seed in processing.all_seeds]
        if seeds:
            processing.seed = seeds[0]
        subseeds = getattr(processing, "all_subseeds", None) or []
        if subseeds:
            processing.subseed = int(subseeds[0])
        self._hr_sources = None
        self._draw = {
            "apply_aspect": bool(apply_aspect),
            "megapixels": float(megapixels),
            "default_ar": default_ar or "3:4",
            "divisible": int(divisible),
            "fetch": bool(fetch),
            "clause_state": clause_state or "{}",
            "img2img": _is_img2img(processing),
        }
        previous_job = getattr(shared.state, "job", "")
        try:
            self._publish(processing, prompts, seeds, apply_size=True)
        except LoraFetchError as exc:
            self._fail_fetch(processing, exc)
        finally:
            _restore_download_job(previous_job)

    def _clear_draw(self):
        self._per_image = []
        self._per_image_hr = []
        self._sources = []
        self._seeds = []
        self._hr_sources = None
        self._draw = None

    def _fail_fetch(self, processing, exc: LoraFetchError):
        self._clear_draw()
        message = str(exc)
        logger.error("%s", message)
        shared.state.textinfo = message
        shared.state.interrupt()
        if getattr(processing, "prompts", None):
            processing.prompts = []

    def _publish(self, processing, prompts, seeds, apply_size: bool):
        draw = self._draw
        if self._hr_sources is None:
            current_hr = getattr(processing, "all_hr_prompts", None)
            self._hr_sources = list(current_hr) if isinstance(current_hr, list) else []
        self._sources = list(prompts)
        downloaded: list[str] = []
        rewritten, size = render_prompts(
            prompts,
            draw["clause_state"],
            catalog=load_catalog(self._wildcard_root()),
            seeds=seeds,
            apply_aspect=draw["apply_aspect"],
            megapixels=draw["megapixels"],
            default_aspect_ratio=draw["default_ar"],
            divisible_by=draw["divisible"],
            default_when_unmarked=not draw["img2img"],
        )

        directories = lora_directories(shared.cmd_opts, models_path)
        domain = "civitai.com" if getattr(shared.opts, "civitai_sfw_only", False) else "civitai.red"
        proxy = (getattr(shared.opts, "custom_civitai_proxy", "") or "").strip()

        def on_download(alias):
            downloaded.append(alias)
            shared.state.job = f"UW Wildcards: descargando {alias}"

        def rewrite(text):
            return ensure_prompt_loras(
                text,
                lora_dirs=directories,
                manifest=_MANIFEST,
                api_key=resolve_civitai_api_key(shared.opts),
                domain=domain,
                proxy=proxy,
                fetch_missing=draw["fetch"],
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
        self._seeds = [int(seed) for seed in seeds]
        if getattr(processing, "negative_prompt", None):
            processing.negative_prompt = rewrite(processing.negative_prompt)
        if getattr(processing, "all_negative_prompts", None):
            processing.all_negative_prompts = [rewrite(item) for item in processing.all_negative_prompts]
        if apply_size and size is not None:
            processing.width = size[0]
            processing.height = size[1]
        extra = getattr(processing, "extra_generation_params", None)
        if not isinstance(extra, dict):
            processing.extra_generation_params = {}
            extra = processing.extra_generation_params
        extra["UW Wildcards"] = draw["clause_state"]
        extra[INFOTEXT_TEMPLATE] = list(prompts)
        self.last_seed = self._seeds[0] if self._seeds else None
        self.last_total = len(rewritten) or 1
        if downloaded:
            _refresh_lora_listing()

    def _redraw_if_seeds_changed(self, processing):
        """Dynamic Prompts puede dejar la misma semilla en todas las imágenes después del sorteo."""
        if not self._draw or not self._sources or len(self._seeds) != len(self._sources):
            return
        try:
            current = [int(seed) for seed in processing.all_seeds]
        except (TypeError, ValueError):
            return
        if len(current) != len(self._seeds) or current == self._seeds:
            return
        previous_job = getattr(shared.state, "job", "")
        try:
            self._publish(processing, self._sources, current, apply_size=False)
        except LoraFetchError as exc:
            self._fail_fetch(processing, exc)
        finally:
            _restore_download_job(previous_job)

    def before_process_batch(self, p, *args, **kwargs):
        """Dynamic Prompts, que corre después en process, rehace all_prompts desde el primero.

        Si no cambió el texto, se recupera la variación por semilla, el slice de
        este lote y el pase hires. Si lo cambió, manda su versión y no se pisa.
        """
        self._redraw_if_seeds_changed(p)
        per_image = self._per_image
        all_prompts = getattr(p, "all_prompts", None) or []
        if not per_image or len(per_image) != len(all_prompts):
            return
        if not all_prompts or all_prompts[0] != per_image[0]:
            return
        p.all_prompts = list(per_image)
        batch_size = len(p.prompts) if getattr(p, "prompts", None) else int(getattr(p, "batch_size", 0) or 0)
        if batch_size > 0:
            batch_number = kwargs.get("batch_number", getattr(p, "iteration", 0))
            try:
                batch_number = int(batch_number)
            except (TypeError, ValueError):
                batch_number = 0
            start = batch_number * batch_size
            p.prompts = list(per_image[start : start + batch_size])
        per_hr = self._per_image_hr
        hires = getattr(p, "all_hr_prompts", None)
        if per_hr and isinstance(hires, list) and len(hires) == len(per_hr) and hires[0] == per_hr[0]:
            p.all_hr_prompts = list(per_hr)

    def _inherit_hires_prompts(self, processing, originals, rewritten):
        """setup_prompts copió el prompt sin expandir al de hires; solo se hereda el propio."""
        hires = self._hr_sources if self._hr_sources is not None else getattr(processing, "all_hr_prompts", None)
        if not isinstance(hires, list) or len(hires) != len(originals):
            self._per_image_hr = []
            return
        processing.all_hr_prompts = [
            new if old == original else old
            for old, original, new in zip(hires, originals, rewritten)
        ]
        self._per_image_hr = list(processing.all_hr_prompts)
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
