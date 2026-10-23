"""JSON de cláusulas. Pin, skip y regenerar editan ese objeto y nada más."""

from __future__ import annotations

import json

from forge_uw_wildcards.clauses import OVERRIDE_PARAM_TO_KIND, SKIP_OVERRIDE_SENTINEL

SLOT_LABELS = (
    ("wardrobe", "Ropa"),
    ("environment", "Entorno"),
    ("medium", "Medio"),
    ("lighting", "Luz"),
    ("treatment", "Tratamiento"),
    ("hair", "Pelo"),
    ("body", "Cuerpo"),
    ("age", "Edad"),
    ("eye_color", "Color de ojos"),
    ("nationality", "Nacionalidad"),
    ("skin", "Piel"),
    ("face", "Rostro"),
    ("jewelry", "Joyas"),
    ("skin_tone", "Tono de piel"),
    ("hair_color", "Color de pelo"),
    ("breast_size", "Pecho"),
    ("butt_size", "Cadera"),
)


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
    overrides = data.get("overrides")
    counters = data.get("counters")
    return {
        "tag": data.get("tag") or "",
        "overrides": dict(overrides) if isinstance(overrides, dict) else {},
        "counters": dict(counters) if isinstance(counters, dict) else {},
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
