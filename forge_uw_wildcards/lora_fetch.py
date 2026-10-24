"""Descarga perezosa de las LoRA del manifiesto.

El fichero queda en la carpeta de LoRA de Forge, bajo UWModularWildcards/,
y el tag del prompt se reescribe para que apunte ahí.
"""

from __future__ import annotations

import http.client
import inspect
import json
import os
import re
import socket
import threading
import time
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
_IDLE_TIMEOUT = 120
_TRANSFER_TIMEOUT = 30 * 60
_READ_SIZE = 256 * 1024


class LoraFetchError(RuntimeError):
    pass


class HttpResult:
    def __init__(self, status: int, headers: dict, body: bytes, stored: bool = False):
        self.status = status
        self.headers = {str(key).lower(): value for key, value in headers.items()}
        self.body = body
        self.stored = stored


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


def _content_length(headers: dict) -> int | None:
    raw = headers.get("Content-Length") or headers.get("content-length")
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _read_bounded(response, deadline: float) -> bytes:
    chunks = []
    while True:
        if time.monotonic() > deadline:
            raise TimeoutError("transfer")
        chunk = response.read(_READ_SIZE)
        if not chunk:
            break
        chunks.append(chunk)
    return b"".join(chunks)


def _stream_to(response, dest: Path, deadline: float, first: bytes, expected: int | None) -> None:
    total = 0
    with dest.open("wb") as handle:
        if first:
            handle.write(first)
            total += len(first)
        while True:
            if time.monotonic() > deadline:
                raise TimeoutError("transfer")
            chunk = response.read(_READ_SIZE)
            if not chunk:
                break
            handle.write(chunk)
            total += len(chunk)
    if expected is not None and total != expected:
        raise http.client.IncompleteRead(b"", expected)


def urllib_open(url: str, headers: dict, proxy: str, timeout: int = _IDLE_TIMEOUT, dest: Path | None = None) -> HttpResult:
    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, hdrs, newurl):
            return None

    handlers = []
    if proxy:
        handlers.append(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    handlers.append(_NoRedirect())
    opener = urllib.request.build_opener(*handlers)
    request = urllib.request.Request(url, headers=headers, method="GET")
    deadline = time.monotonic() + _TRANSFER_TIMEOUT
    try:
        with opener.open(request, timeout=timeout) as response:
            status = getattr(response, "status", 200)
            response_headers = dict(response.headers)
            content_type = str(response_headers.get("Content-Type") or response_headers.get("content-type") or "")
            if dest is not None and status == 200 and "text/html" not in content_type.lower():
                first = response.read(1)
                if first in (b"", b"<"):
                    rest = _read_bounded(response, deadline) if first else b""
                    return HttpResult(status, response_headers, first + rest)
                _stream_to(response, dest, deadline, first, _content_length(response_headers))
                return HttpResult(status, response_headers, b"", stored=True)
            return HttpResult(status, response_headers, _read_bounded(response, deadline))
    except urllib.error.HTTPError as exc:
        body = exc.read() if exc.fp else b""
        return HttpResult(exc.code, dict(exc.headers or {}), body)


def _host(url: str) -> str:
    return urllib.parse.urlparse(url).netloc.lower().split(":")[0]


def _same_civitai_origin(url: str, domain: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        return False
    host = _host(url)
    domain = (domain or "").lower()
    return host == domain or host.endswith("." + domain)


def _request_headers(url: str, api_key: str, domain: str) -> dict:
    headers = {"User-Agent": "sd-forge-uw-wildcards"}
    if _same_civitai_origin(url, domain):
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def classify_location(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        return "invalid"
    host = _host(url)
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


def _accepts_dest(open_request) -> bool:
    try:
        return "dest" in inspect.signature(open_request).parameters
    except (TypeError, ValueError):
        return False


def _network_reason(exc: BaseException) -> str:
    reason = getattr(exc, "reason", None)
    if isinstance(exc, (TimeoutError, socket.timeout)) or isinstance(reason, (TimeoutError, socket.timeout)):
        return "la descarga ha superado el tiempo de espera"
    if isinstance(exc, http.client.IncompleteRead):
        return "la descarga se ha cortado"
    return "no se ha podido conectar con Civitai"


def _fail(alias: str, reason: str, domain: str) -> None:
    sfw = ""
    if domain == "civitai.com":
        sfw = " CivitAI Browser está en SFW only (civitai.com)."
    raise LoraFetchError(f"{alias}: {reason}.{sfw}")


def _download(alias: str, version_id: int, dest: Path, api_key: str, domain: str, proxy: str, open_request) -> None:
    partial = dest.with_suffix(dest.suffix + ".partial")
    dest.parent.mkdir(parents=True, exist_ok=True)
    url = f"https://{domain}/api/download/models/{version_id}"
    deadline = time.monotonic() + _TRANSFER_TIMEOUT
    try:
        for _ in range(5):
            if time.monotonic() > deadline:
                _fail(alias, "la descarga ha superado el tiempo de espera", domain)
            try:
                if _accepts_dest(open_request):
                    result = open_request(url, _request_headers(url, api_key, domain), proxy, dest=partial)
                else:
                    result = open_request(url, _request_headers(url, api_key, domain), proxy)
            except LoraFetchError:
                raise
            except Exception as exc:
                _fail(alias, _network_reason(exc), domain)
            if result.status == 401:
                _fail(alias, "Civitai pide una clave de API válida", domain)
            if 300 <= result.status < 400:
                location = result.headers.get("location")
                if not location:
                    _fail(alias, f"redirect {result.status} sin destino", domain)
                url = urllib.parse.urljoin(url, location)
                kind = classify_location(url)
                if kind == "invalid":
                    _fail(alias, "el destino de la descarga no es https", domain)
                if kind == "no_api":
                    _fail(alias, "Civitai pide una clave de API válida", domain)
                if kind != "file":
                    _fail(alias, "Civitai ha devuelto una página en lugar del fichero", domain)
                continue
            if result.status != 200:
                _fail(alias, f"Civitai ha respondido {result.status}", domain)
            content_type = (result.headers.get("content-type") or "").lower()
            if getattr(result, "stored", False):
                if not partial.is_file() or partial.stat().st_size == 0:
                    _fail(alias, "Civitai ha devuelto un fichero vacío", domain)
            else:
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
