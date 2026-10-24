"""Convierte el prompt y el JSON de cláusulas en prosa y, si toca, en tamaño."""

from __future__ import annotations

INFOTEXT_TEMPLATE = "UW Template"

from forge_uw_wildcards.aspect import process_prompt_aspect_size, strip_trailing_aspect_marker
from forge_uw_wildcards.clauses import expand_with_overrides
from forge_uw_wildcards.state import override_kwargs, parse_state


def render_prompts(
    prompts: list[str],
    state_json: str,
    *,
    catalog: dict,
    seeds: list[int],
    apply_aspect: bool,
    megapixels: float,
    default_aspect_ratio: str,
    divisible_by: int,
    enabled: bool = True,
    default_when_unmarked: bool = True,
) -> tuple[list[str], tuple[int, int] | None]:
    if not enabled:
        return list(prompts), None

    state = parse_state(state_json)
    tag = (state.get("tag") or "").strip()
    kwargs = override_kwargs(state)
    counters = state.get("counters") or {}
    rewritten = []
    for index, prompt in enumerate(prompts):
        text, user_marker = strip_trailing_aspect_marker(prompt or "")
        if tag and tag not in text:
            text = f"{text} {tag}".strip()
        seed = seeds[index] if index < len(seeds) else 0
        text = expand_with_overrides(text, seed, catalog=catalog, counters=counters, **kwargs)
        _body, expanded_marker = strip_trailing_aspect_marker(text)
        if user_marker and expanded_marker is None:
            text = f"{text} [{user_marker[0]}:{user_marker[1]}]"
        rewritten.append(text)

    if not apply_aspect or not rewritten:
        return rewritten, None

    sized = []
    width = height = None
    for text in rewritten:
        _body, marker = strip_trailing_aspect_marker(text)
        cleaned, item_width, item_height, _detected = process_prompt_aspect_size(
            text, float(megapixels), default_aspect_ratio or "3:4", int(divisible_by)
        )
        sized.append(cleaned)
        if width is None and (marker or default_when_unmarked):
            width, height = int(item_width), int(item_height)
    if width is None:
        return sized, None
    return sized, (width, height)


def restore_pasted_prompt(parameters: dict) -> None:
    """Al pegar, el prompt del PNG es la prosa. La plantilla guardada es la que hay que volver a sortear."""
    template = parameters.get(INFOTEXT_TEMPLATE)
    if isinstance(template, list):
        template = template[0] if template else None
    if isinstance(template, str):
        parameters["Prompt"] = template
