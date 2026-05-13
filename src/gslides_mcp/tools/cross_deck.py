"""Cross-deck slide copy via a deployed Apps Script web app.

The Slides REST API has NO cross-presentation copy. Apps Script does
(``SlidesApp.appendSlide(slide)``) — it carries layout, theme, fonts,
images, styles. We expose that as an HTTP endpoint and call it here.

Setup is one-time and manual: see ``appscript/cross_deck_copy.gs`` for the
deployment steps. The MCP reads the deployed URL from either:

    - env var ``GSLIDES_MCP_APPSCRIPT_URL``
    - file ``~/.gslides-mcp/appscript_url`` (one-line text)

If neither is set, the tool raises with deployment instructions.
"""

from __future__ import annotations

import json
import os
import ssl
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import certifi

from ..app import mcp
from ..util import parse_pres_id


_SSL_CTX = ssl.create_default_context(cafile=certifi.where())


_APPSCRIPT_URL_FILE = Path.home() / ".gslides-mcp" / "appscript_url"

# Apps Script web apps always serve from this host. We refuse to send an OAuth
# bearer token to anything else, even if the URL file or env var was mis-set.
_APPSCRIPT_HOST = "script.google.com"


# A urllib opener that does NOT follow redirects. Apps Script /exec endpoints
# respond 200 with a JSON body on success and don't redirect in normal use;
# allowing redirects would risk replaying the Authorization header across hosts.
class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, hdrs, newurl):  # noqa: ARG002
        return None


_NO_REDIRECT_OPENER = urllib.request.build_opener(
    _NoRedirect(),
    urllib.request.HTTPSHandler(context=_SSL_CTX),
)


def _appscript_url() -> str:
    """Resolve the deployed web-app URL or raise with setup help."""
    url = os.environ.get("GSLIDES_MCP_APPSCRIPT_URL")
    if url:
        return url.strip()
    if _APPSCRIPT_URL_FILE.exists():
        return _APPSCRIPT_URL_FILE.read_text().strip()
    raise RuntimeError(
        "cross-deck copy requires a deployed Apps Script web app. "
        "See appscript/cross_deck_copy.gs for setup steps. "
        f"Once deployed, save the URL to {_APPSCRIPT_URL_FILE} or "
        "set GSLIDES_MCP_APPSCRIPT_URL=<url>."
    )


def _post_json(url: str, payload: dict, timeout: float = 180.0) -> dict:
    """POST a JSON payload to the Apps Script web app and return parsed JSON.

    Security: the OAuth bearer token is attached ONLY when the destination
    host is script.google.com. A misconfigured ``GSLIDES_MCP_APPSCRIPT_URL``
    (typo, hostile takeover of the URL file, swap to a dev tunnel) would
    otherwise leak a usable Google access token to an arbitrary endpoint.
    Redirects are also disabled — Apps Script doesn't issue them, and we
    don't want a same-scheme cross-host redirect to replay the token.
    """
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "gslides-mcp/0.1",
    }
    host = urllib.parse.urlparse(url).hostname or ""
    if host == _APPSCRIPT_HOST:
        try:
            token = _maybe_token()
            if token:
                headers["Authorization"] = f"Bearer {token}"
        except Exception:
            pass
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with _NO_REDIRECT_OPENER.open(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        # Truncate aggressively — Apps Script error bodies can be large and
        # we don't want any echoed request headers ending up in user output.
        msg = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"appscript HTTP {e.code}: {msg[:500]}") from None


def _maybe_token() -> str | None:
    """Load a fresh OAuth access token for outbound Apps Script calls.

    The MCP's GoogleAPIClient doesn't expose its credentials attribute, so we
    re-read the token.json directly and refresh if expired. Same creds that
    were OAuth'd for Slides + Drive — Apps Script Workspace-scoped
    deployments accept them as identity proof.
    """
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request as GAuthRequest

    from ..auth import cred_dir
    token_path = cred_dir() / "token.json"
    if not token_path.exists():
        return None
    creds = Credentials.from_authorized_user_file(str(token_path))
    if not creds.valid:
        try:
            creds.refresh(GAuthRequest())
        except Exception:
            return None
    return creds.token


@mcp.tool()
def copy_slide_cross_deck(
    src_presentation: str,
    src_slide: str,
    dst_presentation: str,
    insertion_index: int | None = None,
) -> dict:
    """Copy ONE slide from src to dst, preserving layout/theme/fonts/styles.

    Routes through a deployed Apps Script web app (``SlidesApp.appendSlide``)
    because the Slides REST API has no cross-presentation copy. Setup is
    one-time and manual — see ``appscript/cross_deck_copy.gs`` and the
    error message thrown when the URL isn't configured.

    Args:
        src_presentation: source deck ID or full URL.
        src_slide: 1-based index OR objectId of the slide to copy.
        dst_presentation: destination deck ID or full URL.
        insertion_index: optional 0-based insertion index in dst (default
            appends to the end).

    Returns: ``{newSlideId, dstIndex}`` — the new slide's objectId in dst,
    and its 0-based final position. Use the objectId to address it in
    follow-up replace_text / write_text_markdown calls.

    First call after server start: ~2-4s (Apps Script cold-start). Steady
    state: ~700ms-1.5s per slide.
    """
    url = _appscript_url()
    payload: dict = {
        "op": "copy",
        "srcId": parse_pres_id(src_presentation),
        "dstId": parse_pres_id(dst_presentation),
        "srcSlide": src_slide,
    }
    if insertion_index is not None:
        payload["insertionIndex"] = insertion_index
    result = _post_json(url, payload)
    if "error" in result:
        raise RuntimeError(f"appscript error: {result['error']}")
    return result


@mcp.tool()
def cross_deck_ping() -> dict:
    """Health-check the deployed Apps Script web app.

    Verifies the URL is configured, reachable, and the script is the right
    version. Use this to debug deployment before relying on
    ``copy_slide_cross_deck``.

    Returns: ``{ok: True, version: "0.3", url: "..."}`` on success.
    """
    url = _appscript_url()
    result = _post_json(url, {"op": "ping"})
    return {"url": url, **result}
