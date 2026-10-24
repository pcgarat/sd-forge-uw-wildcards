"""Qué texto sortea cada hueco para una semilla y de dónde sale esa semilla.

Funciones puras: la UI de Gradio se limita a traducir su resultado a campos.
"""

from __future__ import annotations

from dataclasses import dataclass

from forge_uw_wildcards.clauses import expand_with_overrides
from forge_uw_wildcards.state import SLOT_LABELS, override_kwargs

SOURCE_FIELD = "field"
SOURCE_LAST = "last"


@dataclass(frozen=True)
class SeedChoice:
    seed: int
    source: str


def _as_number(raw) -> int | None:
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return None


def seed_choice(mirror, last_seed: int | None) -> SeedChoice | None:
    """Número del campo Seed si es >= 0; si no, la semilla de la última generación."""
    value = _as_number(mirror)
    if value is not None and value >= 0:
        return SeedChoice(value, SOURCE_FIELD)
    if last_seed is not None and int(last_seed) >= 0:
        return SeedChoice(int(last_seed), SOURCE_LAST)
    return None


def resolve_seed(mirror, last_seed: int | None) -> int | None:
    choice = seed_choice(mirror, last_seed)
    return None if choice is None else choice.seed


def collect_slots(catalog: dict, state: dict, seed: int) -> dict[str, str]:
    """Texto que sortea cada hueco de ese router para esa semilla."""
    tag = (state.get("tag") or "").strip()
    if not tag:
        return {}
    trace: dict[str, str] = {}
    expand_with_overrides(
        tag,
        seed,
        catalog=catalog,
        counters=state.get("counters") or {},
        trace=trace,
        **override_kwargs(state),
    )
    return {kind: trace[kind] for kind, _label in SLOT_LABELS if kind in trace}


def status_line(choice: SeedChoice | None, total: int = 1) -> str:
    if choice is None:
        return "Sin semilla: escribe un número en Seed o genera una imagen."
    if choice.source == SOURCE_LAST:
        text = f"Semilla {choice.seed} · última generación"
        if total > 1:
            text += f" · imagen 1 de {total}"
        return text
    return f"Semilla {choice.seed} · campo Seed"
