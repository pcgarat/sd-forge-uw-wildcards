"""Expansión de routers y plantillas uw-* con overrides de texto.

El catálogo es el dict que Impact arma al leer el YAML: clave con barras
y valor lista de opciones. Un tag que no empieza por uw- no se toca,
aunque el catálogo lo tenga.
"""

from __future__ import annotations

import hashlib
import random
import re

_TAG_RE = re.compile(r"__([\w.\-+/*\\]+?)__")
_BRACE_RE = re.compile(r"(?<!\\)\{((?:[^{}]|(?<=\\)[{}])*?)(?<!\\)\}")
_WEIGHT_RE = re.compile(r"^\s*(-?(?:\d+\.?\d*|\d*\.\d+))::(.*)$", re.DOTALL)
_PUNCT_ONLY_COMMA_GAP_RE = re.compile(r",\s*[.;:,!?\-–—]+\s*,")
_DOUBLE_COMMA_RE = re.compile(r",\s*,")
_DANGLING_COMMA_PERIOD_RE = re.compile(r",\s*\.(?=\s|$)")
_PERIOD_COMMA_RE = re.compile(r"\.\s*,")
_INLINE_SPACE_RE = re.compile(r"[^\S\n]+")

# Mismo centinela que contract.py del motor 3.1.0.
SKIP_OVERRIDE_SENTINEL = "\uE002"

LEAF_OVERRIDE_KINDS = (
    "subject",
    "wardrobe",
    "environment",
    "medium",
    "lighting",
    "treatment",
)

OVERRIDE_PARAM_TO_KIND = {
    "wardrobe_override": "wardrobe",
    "environment_override": "environment",
    "medium_override": "medium",
    "lighting_override": "lighting",
    "treatment_override": "treatment",
    "hair_override": "hair",
    "body_override": "body",
    "age_override": "age",
    "eye_color_override": "eye_color",
    "nationality_override": "nationality",
    "skin_override": "skin",
    "face_override": "face",
    "jewelry_override": "jewelry",
    "skin_tone_override": "skin_tone",
    "hair_color_override": "hair_color",
    "breast_size_override": "breast_size",
    "butt_size_override": "butt_size",
}

OVERRIDE_KIND_ORDER = (
    "wardrobe",
    "environment",
    "medium",
    "lighting",
    "treatment",
    "hair",
    "body",
    "age",
    "eye_color",
    "nationality",
    "skin",
    "face",
    "jewelry",
    "skin_tone",
    "hair_color",
    "breast_size",
    "butt_size",
)


def _normalize_key(key: str) -> str:
    return key.replace("\\", "/").replace(" ", "-").lower()


def _is_leaf_override_key(key: str, kind: str) -> bool:
    if "/leaf/" not in key or kind not in LEAF_OVERRIDE_KINDS:
        return False
    return key.endswith(f"/{kind}")


def _is_atom_override_key(key: str, kind: str) -> bool:
    if kind == "hair":
        return "/common/hair/" in key and "/hair-color/" not in key
    if kind == "body":
        return "/body-archetype/" in key
    if kind == "age":
        return "/common/age/" in key
    if kind == "eye_color":
        return "/eye-color/" in key
    if kind == "nationality":
        return "/nationality/" in key
    if kind == "skin":
        return "/common/skin/" in key and "/skin-tone/" not in key
    if kind == "face":
        return "/face-features/" in key
    if kind == "jewelry":
        return "/piercing/" in key or "/accessories/" in key
    if kind == "skin_tone":
        return "/skin-tone/" in key
    if kind == "hair_color":
        return "/hair-color/" in key
    if kind == "breast_size":
        return "/breast-size/" in key
    if kind == "butt_size":
        return "/butt-size/" in key
    return False


def _is_override_key(key: str, kind: str) -> bool:
    if kind in LEAF_OVERRIDE_KINDS:
        return _is_leaf_override_key(key, kind)
    return _is_atom_override_key(key, kind)


def _classify_overrides(overrides: dict[str, str]) -> tuple[dict[str, str], set[str]]:
    active: dict[str, str] = {}
    skipped: set[str] = set()
    for param, kind in OVERRIDE_PARAM_TO_KIND.items():
        raw = overrides.get(param) or ""
        if raw == SKIP_OVERRIDE_SENTINEL:
            skipped.add(kind)
            continue
        value = raw.strip()
        if value:
            active[kind] = value
    return active, skipped


def _lookup(key: str, catalog: dict, active: dict[str, str], skipped: set[str]):
    normalized = _normalize_key(key)
    for kind in OVERRIDE_KIND_ORDER:
        if kind in skipped and _is_override_key(normalized, kind):
            return [""]
        value = active.get(kind)
        if value and _is_override_key(normalized, kind):
            return [value]
    if not normalized.startswith("uw-"):
        return None
    return catalog.get(normalized)


def _slot_id(key: str) -> str:
    normalized = _normalize_key(key)
    for kind in OVERRIDE_KIND_ORDER:
        if _is_override_key(normalized, kind):
            return kind
    return normalized


_INNERMOST_MARKER_RE = re.compile(
    r"@@WC_START:(\w+)@@((?:(?!@@WC_START:).)*?)@@WC_END:\1@@", re.DOTALL
)


def _marker_start(kind: str) -> str:
    return f"@@WC_START:{kind}@@"


def _marker_end(kind: str) -> str:
    return f"@@WC_END:{kind}@@"


def _unwrap_markers(text: str) -> str:
    previous = None
    while previous != text:
        previous = text
        text = _INNERMOST_MARKER_RE.sub(r"\2", text)
    return text


def _collect_markers(text: str, into: dict[str, str]) -> None:
    current = text
    previous = None
    while previous != current:
        previous = current
        for kind, inner in _INNERMOST_MARKER_RE.findall(current):
            body = inner.strip()
            if body:
                into[kind] = body
        current = _INNERMOST_MARKER_RE.sub(r"\2", current)


def _clean_expand_artifacts(text: str) -> str:
    if text is None:
        return ""
    out = text
    previous = None
    while previous != out:
        previous = out
        out = _PUNCT_ONLY_COMMA_GAP_RE.sub(",", out)
        out = _DOUBLE_COMMA_RE.sub(",", out)
        out = _DANGLING_COMMA_PERIOD_RE.sub(".", out)
        out = _PERIOD_COMMA_RE.sub(",", out)
        out = _INLINE_SPACE_RE.sub(" ", out)
    return out


def _parse_weighted(option: str) -> tuple[float, str]:
    match = _WEIGHT_RE.match(option)
    if not match:
        return 1.0, option
    return float(match.group(1)), match.group(2)


def _draw(seed: int | None, slot: str, counter: int) -> int:
    payload = f"{0 if seed is None else int(seed)}:{slot}:{counter}".encode()
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")


def _weighted_choice(parsed: list[tuple[float, str]], rng: random.Random) -> str:
    total = sum(weight for weight, _body in parsed)
    if total <= 0:
        return parsed[-1][1]
    point = rng.random() * total
    covered = 0.0
    for weight, body in parsed:
        covered += weight
        if point < covered:
            return body
    return parsed[-1][1]


def _resolve_braces(text: str, seed: int | None) -> tuple[str, bool]:
    current = text
    replaced_any = False
    for _ in range(20):
        occurrence = 0
        replaced = False

        def replacer(match):
            nonlocal replaced, occurrence
            options = match.group(1).split("|")
            parsed = [_parse_weighted(part) for part in options]
            total = sum(weight for weight, _body in parsed)
            if len(parsed) == 1 or total <= 1:
                chosen = " ".join(body for _weight, body in parsed)
            else:
                rng = random.Random(_draw(seed, f"brace:{occurrence}:{match.group(1)}", 0))
                chosen = _weighted_choice(parsed, rng)
            occurrence += 1
            replaced = True
            return chosen

        updated = _BRACE_RE.sub(replacer, current)
        if not replaced:
            break
        replaced_any = True
        current = updated
    return current, replaced_any


def _pick(
    options: list,
    key: str,
    seed: int | None,
    counters: dict | None,
    trace: dict | None = None,
) -> str:
    parsed = [_parse_weighted(str(item)) for item in options]
    if len(parsed) == 1:
        chosen = parsed[0][1]
    else:
        slot = _slot_id(key)
        counter = int((counters or {}).get(slot, 0))
        rng = random.Random(_draw(seed, slot, counter))
        chosen = _weighted_choice(parsed, rng)
    if trace is not None and chosen:
        slot = _slot_id(key)
        if slot in OVERRIDE_KIND_ORDER:
            return f"{_marker_start(slot)}{chosen}{_marker_end(slot)}"
    return chosen


def expand_with_overrides(
    text: str,
    seed: int | None,
    *,
    catalog: dict,
    counters: dict | None = None,
    trace: dict | None = None,
    **overrides: str,
) -> str:
    source = "" if text is None else str(text)
    if trace is None:
        return _clean_expand_artifacts(_expand(source, seed, catalog, counters, None, overrides))
    marked = _expand(source, seed, catalog, counters, trace, overrides)
    _collect_markers(marked, trace)
    return _clean_expand_artifacts(_unwrap_markers(marked))


def _expand(
    source: str,
    seed: int | None,
    catalog: dict,
    counters: dict | None,
    trace: dict | None,
    overrides: dict[str, str],
) -> str:
    active, skipped = _classify_overrides(overrides)
    if not active and not skipped and "__" not in source and "{" not in source:
        return source

    current = source
    for _ in range(100):
        current, braces_replaced = _resolve_braces(current, seed)
        pieces: list[str] = []
        pos = 0
        replaced = False
        for match in _TAG_RE.finditer(current):
            pieces.append(current[pos : match.start()])
            options = _lookup(match.group(1), catalog, active, skipped)
            if options is None:
                pieces.append(match.group(0))
            else:
                pieces.append(_pick(options, match.group(1), seed, counters, trace))
                replaced = True
            pos = match.end()
        pieces.append(current[pos:])
        current = "".join(pieces)
        if not braces_replaced and not replaced:
            break
    return current
