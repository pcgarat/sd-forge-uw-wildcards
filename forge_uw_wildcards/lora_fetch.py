"""Descarga perezosa de las LoRA del manifiesto.

El fichero queda en la carpeta de LoRA de Forge, bajo UWModularWildcards/,
y el tag del prompt se reescribe para que apunte ahí.
"""

from __future__ import annotations

import json
import os
import re
import threading
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

LORA_SUBFOLDER = "UWModularWildcards"
_WEIGHT_SUFFIXES = (".safetensors", ".pt", ".ckpt", ".pth")
_LORA_RE = re.compile(r"<lora:([^:>]+):([^:>]+)(?::([^:>]+))?>", re.IGNORECASE)
_PAGE_HOSTS = ("civitai.com", "civitai.red")
_PAGE_PATHS = ("/login", "/models/", "/model-versions/", "/purchase", "/checkout", "/buzz", "/user/")
_LOCKS: dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()


class LoraFetchError(RuntimeError):
    pass


class HttpResult:
    def __init__(self, status: int, headers: dict, body: bytes):
        self.status = status
        self.headers = {str(key).lower(): value for key, value in headers.items()}
        self.body = body


def lora_directories(cmd_opts, models_path: str | os.PathLike) -> list[Path]:
    found: list[Path] = []

    def add(value):
        if not value:
            return
        path = Path(value)
        if path not in found:
            found.append(path)

    add(getattr(cmd_opts, "lora_dir", None))
    extra = getattr(cmd_opts, "lora_dirs", None) or []
    if isinstance(extra, (str, Path)):
        extra = [extra]
    for value in extra:
        add(value)
    if not found:
        add(Path(models_path) / "Lora")
    return found


def load_manifest(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def urllib_open(url: str, headers: dict, proxy: str, timeout: int = 120) -> HttpResult:
    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, hdrs, newurl):
            return None

    handlers = []
    if proxy:
        handlers.append(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    handlers.append(_NoRedirect())
    opener = urllib.request.build_opener(*handlers)
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with opener.open(request, timeout=timeout) as response:
            return HttpResult(getattr(response, "status", 200), dict(response.headers), response.read())
    except urllib.error.HTTPError as exc:
        body = exc.read() if exc.fp else b""
        return HttpResult(exc.code, dict(exc.headers or {}), body)


def classify_location(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return "invalid"
    host = parsed.netloc.lower().split(":")[0]
    if not any(host == item or host.endswith("." + item) for item in _PAGE_HOSTS):
        return "file"
    path = (parsed.path or "/").lower()
    query = (parsed.query or "").lower()
    if path.startswith("/login") or "returnurl" in query:
        return "no_api"
    if any(path.startswith(item) for item in _PAGE_PATHS):
        return "page"
    return "file"


def _alias_of(name: str, manifest: dict) -> str | None:
    cleaned = name.strip().strip("/")
    prefix = LORA_SUBFOLDER + "/"
    if cleaned.startswith(prefix):
        cleaned = cleaned[len(prefix):]
    if cleaned in manifest:
        return cleaned
    return None


def _existing_weight(directories: list[Path], relative_stem: str) -> Path | None:
    for folder in directories:
        for suffix in _WEIGHT_SUFFIXES:
            candidate = folder / f"{relative_stem}{suffix}"
            if candidate.is_file():
                return candidate
    return None


def _lock_for(key: str) -> threading.Lock:
    with _LOCKS_GUARD:
        lock = _LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _LOCKS[key] = lock
        return lock


def _format_tag(name: str, weight: str, clip: str | None) -> str:
    if clip:
        return f"<lora:{name}:{weight}:{clip}>"
    return f"<lora:{name}:{weight}>"


def _fail(alias: str, reason: str, domain: str) -> None:
    sfw = ""
    if domain == "civitai.com":
        sfw = " CivitAI Browser está en SFW only (civitai.com)."
    raise LoraFetchError(f"{alias}: {reason}.{sfw}")


def _download(alias: str, version_id: int, dest: Path, api_key: str, domain: str, proxy: str, open_request) -> None:
    partial = dest.with_suffix(dest.suffix + ".partial")
    dest.parent.mkdir(parents=True, exist_ok=True)
    url = f"https://{domain}/api/download/models/{version_id}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "User-Agent": "sd-forge-uw-wildcards",
    }
    try:
        for _ in range(5):
            result = open_request(url, headers, proxy)
            if result.status == 401:
                _fail(alias, "Civitai pide una clave de API válida", domain)
            if 300 <= result.status < 400:
                location = result.headers.get("location")
                if not location:
                    _fail(alias, f"redirect {result.status} sin destino", domain)
                url = urllib.parse.urljoin(url, location)
                kind = classify_location(url)
                if kind == "no_api":
                    _fail(alias, "Civitai pide una clave de API válida", domain)
                if kind != "file":
                    _fail(alias, "Civitai ha devuelto una página en lugar del fichero", domain)
                continue
            if result.status != 200:
                _fail(alias, f"Civitai ha respondido {result.status}", domain)
            content_type = (result.headers.get("content-type") or "").lower()
            if "text/html" in content_type or result.body.lstrip()[:1] == b"<":
                _fail(alias, "Civitai ha devuelto una página en lugar del fichero", domain)
            if not result.body:
                _fail(alias, "Civitai ha devuelto un fichero vacío", domain)
            partial.write_bytes(result.body)
            os.replace(partial, dest)
            return
        _fail(alias, "demasiados redirects", domain)
    finally:
        if partial.exists() and not dest.exists():
            partial.unlink()


def ensure_prompt_loras(
    text: str,
    *,
    lora_dirs: list[Path],
    manifest: dict,
    api_key: str,
    domain: str,
    proxy: str,
    fetch_missing: bool,
    open_request,
    on_download=None,
) -> str:
    def replace(match: re.Match) -> str:
        alias = _alias_of(match.group(1), manifest)
        if alias is None:
            return match.group(0)
        relative = f"{LORA_SUBFOLDER}/{alias}"
        placed = _format_tag(relative, match.group(2), match.group(3))
        with _lock_for(alias):
            if _existing_weight(lora_dirs, relative) is not None:
                return placed
            if not fetch_missing:
                return match.group(0)
            version_id = (manifest.get(alias) or {}).get("version_id")
            if not version_id:
                raise LoraFetchError(
                    f"{alias}: no hay modelVersionId en el manifiesto; no se descarga la última versión."
                )
            if not (api_key or "").strip():
                raise LoraFetchError(
                    f"{alias}: falta la clave de API de Civitai. "
                    "Está en Settings del browser (Personal CivitAI API key) o en UW Wildcards."
                )
            if not lora_dirs:
                raise LoraFetchError(f"{alias}: Forge no tiene carpeta de LoRA configurada.")
            if on_download is not None:
                on_download(alias)
            _download(
                alias,
                int(version_id),
                lora_dirs[0] / f"{relative}.safetensors",
                api_key.strip(),
                domain,
                proxy,
                open_request,
            )
        return placed

    return _LORA_RE.sub(replace, text or "")
