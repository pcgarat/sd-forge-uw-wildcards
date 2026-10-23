"""Resolución de la clave de Civitai.

La del browser (`custom_api_key` en config.json) gana. La de esta
extensión solo se usa cuando aquella está vacía.
"""

from __future__ import annotations


def resolve_civitai_api_key(opts) -> str:
    data = getattr(opts, "data", None)
    browser = ""
    if isinstance(data, dict):
        browser = (data.get("custom_api_key") or "").strip()
    if not browser:
        browser = (getattr(opts, "custom_api_key", "") or "").strip()
    if browser:
        return browser
    return (getattr(opts, "uw_wildcards_civitai_api_key", "") or "").strip()
