"""Asset-fetching tools — pull logos / images from external sources by domain.

These are pure-HTTP, no Slides API involvement. They exist so the MCP
doesn't have to detour through WebSearch + WebFetch + manual URL hunts
for every client logo.
"""

from __future__ import annotations

import json
import os
import ssl
import urllib.parse
import urllib.request

import certifi

from ..app import mcp


_USER_AGENT = "gslides-mcp/0.1 (+https://github.com/jan-emmanuele/gslide-mcp)"
_SSL_CTX = ssl.create_default_context(cafile=certifi.where())


def _open(url: str, *, method: str = "GET", timeout: float = 5.0):
    """urlopen with the certifi CA bundle — sidesteps macOS framework Python's
    missing system CA certs (the same reason qa.py uses curl for thumbnails)."""
    req = urllib.request.Request(url, method=method, headers={"User-Agent": _USER_AGENT})
    return urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX)


def _head_ok(url: str, timeout: float = 4.0, *, raster_only: bool = True) -> bool:
    """Reachability check, optionally requiring a raster image content-type.

    Slides API rejects SVG via ``insert_image``, so when ``raster_only=True``
    (default) we treat SVG-serving sources as unreachable — they fall
    through to the next candidate. PNG/JPEG/GIF/BMP/WEBP are accepted.
    """
    for method in ("HEAD", "GET"):
        try:
            with _open(url, method=method, timeout=timeout) as resp:
                if not (200 <= resp.status < 300):
                    continue
                if not raster_only:
                    return True
                ct = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
                if ct in {"image/svg+xml", "image/svg"}:
                    return False
                if ct.startswith("image/"):
                    return True
                # Some CDNs respond without a content-type on HEAD; retry GET
                if method == "HEAD":
                    continue
                # Final GET also lacks content-type → treat as unverified
                return False
        except Exception:
            continue
    return False


@mcp.tool()
def fetch_logo_by_domain(domain: str, prefer: str = "wordmark") -> dict:
    """Resolve a public logo URL for a brand by domain.

    Tries multiple sources in order, returns the first that's reachable:

        1. **Wikipedia Commons** — best for well-known brands (nike.com,
           github.com, stripe.com). Wordmark-quality SVG/PNG. Slow lookup
           but high quality.
        2. **Brandfetch CDN** — `https://cdn.brandfetch.io/{domain}` —
           public CDN, broad coverage, no API key needed for basic icon URL.
        3. **Logo.dev** — `https://img.logo.dev/{domain}?token=<token>` —
           only attempted if ``GSLIDES_MCP_LOGODEV_TOKEN`` is set in the
           environment; otherwise this source is skipped and the chain falls
           back to favicon.
        4. **Google s2 favicon** — `https://www.google.com/s2/favicons?...` —
           always works, but tiny (32×32 typical). Last-resort fallback.

    Args:
        domain: bare domain (e.g. ``"stripe.com"``) or full URL — the host is
            extracted either way.
        prefer: ``"wordmark"`` (default; Wikipedia first) or ``"icon"``
            (Brandfetch CDN first; better when you need a square mark).

    Returns: ``{url, source, domain}``. The URL is suitable for direct use in
    ``insert_image(url=...)``.
    """
    # Normalize input: full URL → host; trailing/leading whitespace; lower
    parsed = urllib.parse.urlparse(domain.strip() if "://" in domain else f"//{domain.strip()}")
    # removeprefix (not lstrip) — lstrip("www.") strips any leading {w,.} char,
    # which mangles hosts like "w.gov" or "wwwww.foo.com".
    host = (parsed.hostname or domain.strip()).lower().removeprefix("www.")
    if not host or "." not in host:
        raise ValueError(f"could not extract a domain from {domain!r}")

    # Build attempt list per preference
    wikipedia = _wikipedia_logo_url(host)
    brandfetch = f"https://cdn.brandfetch.io/{host}"
    favicon = f"https://www.google.com/s2/favicons?domain={host}&sz=128"

    # logo.dev is only attempted if GSLIDES_MCP_LOGODEV_TOKEN is set
    logodev_token = os.environ.get("GSLIDES_MCP_LOGODEV_TOKEN")
    logodev = ("logodev", f"https://img.logo.dev/{host}?token={logodev_token}") if logodev_token else None

    if prefer == "icon":
        attempts = [
            ("brandfetch", brandfetch),
            ("wikipedia", wikipedia),
        ]
        if logodev:
            attempts.append(logodev)
        attempts.append(("favicon", favicon))
    else:
        attempts = [
            ("wikipedia", wikipedia),
            ("brandfetch", brandfetch),
        ]
        if logodev:
            attempts.append(logodev)
        attempts.append(("favicon", favicon))

    for source, url in attempts:
        if url and _head_ok(url):
            return {"url": url, "source": source, "domain": host}

    # Favicon practically always works; if everything failed, surface that
    return {"url": favicon, "source": "favicon", "domain": host, "warning": "all preferred sources unreachable; using favicon"}


def _wikipedia_logo_url(host: str) -> str | None:
    """Look up a Wikipedia Commons logo file for the given brand host.

    Heuristic: search Commons for ``"{brand} logo.svg"`` where {brand} is the
    second-level domain (stripe.com → "stripe"). Returns the rendered PNG
    thumbnail URL (640px wide) if a matching file exists.
    """
    brand = host.split(".")[0]
    if not brand:
        return None
    # Wikipedia API: search files by title
    api = (
        "https://commons.wikimedia.org/w/api.php"
        f"?action=query&format=json&prop=imageinfo&iiprop=url"
        f"&titles=File:{urllib.parse.quote(brand.title())}_logo.svg"
    )
    try:
        with _open(api, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        pages = data.get("query", {}).get("pages", {})
        for _pid, page in pages.items():
            ii = page.get("imageinfo")
            if ii:
                # Build the canonical thumb URL pattern: /commons/thumb/<a>/<ab>/<File>/640px-<File>.png
                full_url = ii[0].get("url", "")
                # Convert the source URL to a 640px PNG thumbnail
                if "/commons/" in full_url and full_url.endswith(".svg"):
                    fname = full_url.rsplit("/", 1)[-1]
                    md5_part = full_url.split("/commons/")[1].rsplit("/", 1)[0]
                    return f"https://upload.wikimedia.org/wikipedia/commons/thumb/{md5_part}/{fname}/640px-{fname}.png"
    except Exception:
        return None
    return None
