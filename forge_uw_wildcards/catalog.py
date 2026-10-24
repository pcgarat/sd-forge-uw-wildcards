"""Lee el YAML de wildcards del usuario. No abre .catalog/ ni imágenes."""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

_SELECTABLE = {"router", "template"}


def normalize_key(key: str) -> str:
    return key.replace("\\", "/").replace(" ", "-").lower()


def _flatten(key: str, value, into: dict) -> None:
    if isinstance(value, list):
        into[normalize_key(key)] = [str(item) for item in value]
    elif isinstance(value, dict):
        for child, inner in value.items():
            _flatten(f"{key}/{child}", inner, into)
    elif isinstance(value, str):
        into[normalize_key(key)] = [value]


def _yaml_files(root: Path):
    if not root.is_dir():
        return
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if ".catalog" in path.parts:
            continue
        if path.suffix.lower() not in {".yaml", ".yml"}:
            continue
        yield path


def load_catalog(root: Path) -> dict:
    catalog: dict = {}
    for path in _yaml_files(Path(root)):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError:
            logger.warning("UW Wildcards: se omite el YAML mal formado %s", path)
            continue
        if not isinstance(data, dict):
            continue
        for key, value in data.items():
            _flatten(str(key), value, catalog)
    return catalog


def list_selectable_tags(root: Path) -> list[str]:
    tags = []
    for key in load_catalog(root):
        parts = key.split("/")
        if len(parts) == 3 and parts[1] in _SELECTABLE:
            tags.append(f"__{key}__")
    return sorted(tags)


def wildcard_root(data_path, extension_dir) -> Path:
    if data_path:
        candidate = Path(data_path) / "wildcards"
        if candidate.is_dir():
            return candidate
    if extension_dir:
        sibling = Path(extension_dir).parent / "sd-dynamic-prompts" / "wildcards"
        if sibling.is_dir():
            return sibling
    return Path(data_path or ".") / "wildcards"
