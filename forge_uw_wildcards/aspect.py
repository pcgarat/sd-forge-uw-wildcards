"""Marcador final [W:H] y tamaño en megapíxeles.

Misma cuenta que ComfyUI-PromptAspectSize del pack: el área es
megapíxeles × 10^6 y cada lado se redondea al múltiplo pedido.
"""

from __future__ import annotations

import math
import re

_ASPECT_TRAILING_RE = re.compile(r"\[(\d+):(\d+)\]\s*$")
_ASPECT_PARSE_RE = re.compile(r"^\s*(\d+)\s*:\s*(\d+)\s*$")


def restore_json_braces(text: str) -> str:
    return text.replace("[[[", "{").replace("]]]", "}")


def strip_trailing_aspect_marker(text: str) -> tuple[str, tuple[int, int] | None]:
    if text is None:
        return "", None
    stripped = text.rstrip()
    match = _ASPECT_TRAILING_RE.search(stripped)
    if not match:
        return text, None
    cleaned = stripped[: match.start()].rstrip()
    return cleaned, (int(match.group(1)), int(match.group(2)))


def parse_aspect_ratio(value: str | None) -> tuple[int, int] | None:
    if value is None:
        return None
    match = _ASPECT_PARSE_RE.match(value)
    if not match:
        return None
    width, height = int(match.group(1)), int(match.group(2))
    if width <= 0 or height <= 0:
        return None
    return width, height


def compute_latent_size(
    megapixels: float,
    ratio_w: int,
    ratio_h: int,
    divisible_by: int = 16,
) -> tuple[int, int]:
    megapixels = megapixels if megapixels and megapixels > 0 else 0.01
    step = divisible_by if divisible_by and divisible_by >= 1 else 1
    ratio_w = ratio_w if ratio_w > 0 else 3
    ratio_h = ratio_h if ratio_h > 0 else 4
    area = megapixels * 1_000_000.0
    width_f = math.sqrt(area * (ratio_w / ratio_h))
    height_f = width_f * (ratio_h / ratio_w)

    def snap(value: float) -> int:
        return max(step, int(round(value / step)) * step)

    return snap(width_f), snap(height_f)


def process_prompt_aspect_size(
    text: str,
    megapixels: float,
    default_aspect_ratio: str = "3:4",
    divisible_by: int = 16,
    restore_json_braces_flag: bool = True,
) -> tuple[str, int, int, str]:
    body = text or ""
    if restore_json_braces_flag:
        body = restore_json_braces(body)
    cleaned, marker = strip_trailing_aspect_marker(body)
    ratio = marker if marker and marker[0] > 0 and marker[1] > 0 else None
    if ratio is None:
        ratio = parse_aspect_ratio(default_aspect_ratio) or (3, 4)
    width, height = compute_latent_size(megapixels, ratio[0], ratio[1], divisible_by)
    return cleaned, width, height, f"{ratio[0]}:{ratio[1]}"
