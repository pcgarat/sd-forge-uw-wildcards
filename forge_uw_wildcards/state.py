"""JSON de cláusulas. Pin, skip y regenerar editan ese objeto y nada más."""

from __future__ import annotations

import json
import re

from forge_uw_wildcards.clauses import OVERRIDE_PARAM_TO_KIND, SKIP_OVERRIDE_SENTINEL, SLOT_LABELS

_LORA_TAG_RE = re.compile(r"<lora:[^>]*>", re.IGNORECASE)


def _as_counter(value) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value.strip())
    return None


def _clean_override(value) -> str | None:
    if value == SKIP_OVERRIDE_SENTINEL:
        return value
    if not isinstance(value, str):
        return None
    text = _LORA_TAG_RE.sub("", value).strip()
    return text or None


def parse_state(raw: str | None) -> dict:
    if not raw or not str(raw).strip():
        data = {}
    else:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = {}
    if not isinstance(data, dict):
        data = {}
    raw_tag = data.get("tag")
    overrides = data.get("overrides")
    counters = data.get("counters")
    cleaned_overrides = {}
    if isinstance(overrides, dict):
        for key, value in overrides.items():
            if not isinstance(key, str):
                continue
            text = _clean_override(value)
            if text is not None:
                cleaned_overrides[key] = text
    cleaned_counters = {}
    if isinstance(counters, dict):
        for key, value in counters.items():
            if not isinstance(key, str):
                continue
            parsed = _as_counter(value)
            if parsed is not None:
                cleaned_counters[key] = parsed
    return {
        "tag": raw_tag.strip() if isinstance(raw_tag, str) else "",
        "overrides": cleaned_overrides,
        "counters": cleaned_counters,
    }


def dump_state(state: dict) -> str:
    return json.dumps(parse_state(json.dumps(state)), ensure_ascii=False, separators=(",", ":"))


def set_tag(raw: str, tag: str) -> str:
    state = parse_state(raw)
    state["tag"] = tag or ""
    return dump_state(state)


def pin(raw: str, kind: str, text: str) -> str:
    state = parse_state(raw)
    value = (text or "").strip()
    if value:
        state["overrides"][kind] = value
    else:
        state["overrides"].pop(kind, None)
    return dump_state(state)


def skip(raw: str, kind: str) -> str:
    state = parse_state(raw)
    state["overrides"][kind] = SKIP_OVERRIDE_SENTINEL
    return dump_state(state)


def regenerate(raw: str, kind: str) -> str:
    state = parse_state(raw)
    state["overrides"].pop(kind, None)
    state["counters"][kind] = int(state["counters"].get(kind) or 0) + 1
    return dump_state(state)


def override_kwargs(state: dict) -> dict[str, str]:
    overrides = state.get("overrides") or {}
    kwargs = {}
    for param, kind in OVERRIDE_PARAM_TO_KIND.items():
        if kind in overrides and overrides[kind] is not None:
            kwargs[param] = str(overrides[kind])
    return kwargs
