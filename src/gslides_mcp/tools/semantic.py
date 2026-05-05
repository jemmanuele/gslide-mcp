"""Semantic-layer tools — first-leap operations that compose primitives.

Where the rest of the MCP exposes Slides API mechanics (shapes, text, geometry),
this module exposes operations that collapse common multi-step sequences into a
single call. These tools compose the primitives — they don't add new API
surface, just bundle frequently chained operations:

  - `swap_client(...)` — clone-then-rebrand for a new client.
"""

from __future__ import annotations

import ssl
import urllib.request
from typing import Any

import certifi

from ..app import mcp
from ..auth import slide_service, drive_service
from ..util import parse_pres_id, resolve_slide_ids, PT_TO_EMU


_SSL_CTX = ssl.create_default_context(cafile=certifi.where())


def _image_url_is_raster(url: str, timeout: float = 4.0) -> tuple[bool, str]:
    """HEAD the URL, return (ok, content_type). Slides API accepts PNG/JPEG/GIF/BMP
    but rejects SVG and other vector formats — pre-check before destructive ops."""
    for method in ("HEAD", "GET"):
        try:
            req = urllib.request.Request(url, method=method, headers={"User-Agent": "gslides-mcp/0.1"})
            with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as resp:
                if not (200 <= resp.status < 300):
                    continue
                ct = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
                if not ct.startswith("image/"):
                    return False, ct or "(none)"
                if ct in {"image/svg+xml", "image/svg"}:
                    return False, ct
                return True, ct
        except Exception:
            continue
    return False, "(unreachable)"


@mcp.tool()
def swap_client(
    presentation: str,
    old_name: str,
    new_name: str,
    new_logo_url: str | None = None,
    logo_slides: list[str] | None = None,
    rename_deck: str | None = None,
    extra_pairs: list[dict] | None = None,
) -> dict:
    """Rebrand a deck cloned from one client's proposal to another.

    Composes the canonical clone-and-rebrand sequence into one call:

        1. Bulk text replace ``old_name`` → ``new_name`` (whole deck).
        2. Run any ``extra_pairs`` (e.g. team-size swaps, industry vocab) in
           the same batchUpdate.
        3. If ``new_logo_url`` is provided, find the old client's logo on the
           cover (and any ``logo_slides`` you list), delete it, insert the
           new logo at the same geometry. Only acts on the FIRST image
           element on each target slide whose width/height match a
           "logo-shaped" footprint (small, near a corner) — the cover hero
           image and section-divider photography are left alone.
        4. If ``rename_deck`` is provided, rename the Drive file too.

    Returns: ``{text_swaps, logo_swaps, drive_renamed}`` summary.

    Args:
        old_name: client name to find (e.g. ``"Acme Corp"``). Match-case is
            on by default to avoid hitting lowercase occurrences inside a URL.
        new_name: replacement (e.g. ``"Globex"``).
        new_logo_url: optional URL to the new client's logo. Use
            ``fetch_logo_by_domain`` to resolve.
        logo_slides: slides to swap logos on. Defaults to ``["1"]`` (cover
            only). Pass ``["1", "-1"]`` for cover + closing, or specific
            objectIds if you know them. ``"-1"`` resolves to the last slide.
        rename_deck: optional new Drive title for the deck.
        extra_pairs: list of additional ``{find, replace, match_case?}`` to
            run in the same batchUpdate (e.g. ``[{"find": "200+ creatives",
            "replace": "10 designers"}]``).
    """
    pid = parse_pres_id(presentation)
    svc = slide_service()

    # 1 + 2: text swaps in one batch
    pairs = [{"find": old_name, "replace": new_name, "match_case": True}]
    if extra_pairs:
        for p in extra_pairs:
            if "find" not in p or "replace" not in p:
                raise ValueError(f"each extra pair needs find+replace: {p!r}")
            pairs.append({
                "find": p["find"],
                "replace": p["replace"],
                "match_case": bool(p.get("match_case", False)),
            })
    requests = [
        {"replaceAllText": {
            "containsText": {"text": p["find"], "matchCase": p["match_case"]},
            "replaceText": p["replace"],
        }}
        for p in pairs
    ]
    resp = svc.presentations().batchUpdate(presentationId=pid, body={"requests": requests}).execute()
    text_swaps = []
    for p, reply in zip(pairs, resp.get("replies", [])):
        text_swaps.append({
            "find": p["find"],
            "replace": p["replace"],
            "occurrences": reply.get("replaceAllText", {}).get("occurrencesChanged", 0),
        })

    # 3: optional logo swap
    logo_swaps: list[dict] = []
    if new_logo_url:
        # Pre-validate the URL — must be reachable, raster (no SVG). Slides
        # API rejects SVG, and a half-batched delete-then-failed-create
        # leaves the cover without a logo.
        ok, ct = _image_url_is_raster(new_logo_url)
        if not ok:
            raise ValueError(
                f"new_logo_url not usable: content-type={ct!r}. "
                f"Slides API requires PNG/JPEG/GIF/BMP (no SVG). "
                f"Tip: fetch_logo_by_domain(prefer='wordmark') returns "
                f"Wikipedia PNGs; Brandfetch CDN often serves SVG."
            )
        if logo_slides is None:
            logo_slides = ["1"]
        # Resolve "-1" before passing to resolve_slide_ids
        pres = svc.presentations().get(presentationId=pid).execute()
        last_idx = str(len(pres["slides"]))
        normalized = [last_idx if s == "-1" else s for s in logo_slides]
        target_sids = resolve_slide_ids(svc, pid, normalized)

        for sid in target_sids:
            slide = next(s for s in pres["slides"] if s["objectId"] == sid)
            logo_el = _find_logo_element(slide)
            if not logo_el:
                logo_swaps.append({"slide": sid, "swapped": False, "reason": "no logo-shaped image found"})
                continue
            geom = _element_geometry_pt(logo_el)
            # Delete old, insert new at same geometry (text/title preserved
            # only on shape elements; images don't carry alt-title here)
            svc.presentations().batchUpdate(
                presentationId=pid,
                body={"requests": [
                    {"deleteObject": {"objectId": logo_el["objectId"]}},
                    {"createImage": {
                        "url": new_logo_url,
                        "elementProperties": {
                            "pageObjectId": sid,
                            "size": {
                                "width": {"magnitude": geom["w_emu"], "unit": "EMU"},
                                "height": {"magnitude": geom["h_emu"], "unit": "EMU"},
                            },
                            "transform": {
                                "scaleX": 1, "scaleY": 1,
                                "translateX": geom["x_emu"], "translateY": geom["y_emu"],
                                "unit": "EMU",
                            },
                        },
                    }},
                ]},
            ).execute()
            logo_swaps.append({
                "slide": sid,
                "swapped": True,
                "deleted_id": logo_el["objectId"],
                "geometry_pt": {
                    "x": round(geom["x_emu"] / PT_TO_EMU, 1),
                    "y": round(geom["y_emu"] / PT_TO_EMU, 1),
                    "w": round(geom["w_emu"] / PT_TO_EMU, 1),
                    "h": round(geom["h_emu"] / PT_TO_EMU, 1),
                },
            })

    # 4: optional Drive rename
    drive_renamed = False
    if rename_deck:
        drive_service().files().update(
            fileId=pid,
            body={"name": rename_deck},
            supportsAllDrives=True,
        ).execute()
        drive_renamed = True

    return {
        "text_swaps": text_swaps,
        "logo_swaps": logo_swaps,
        "drive_renamed": drive_renamed,
    }


def _element_geometry_pt(el: dict) -> dict:
    """Return composed (translate × scale × size) geometry in EMU."""
    t = el.get("transform", {})
    s = el.get("size", {})
    sx = t.get("scaleX", 1)
    sy = t.get("scaleY", 1)
    return {
        "x_emu": int(t.get("translateX", 0)),
        "y_emu": int(t.get("translateY", 0)),
        "w_emu": int(s.get("width", {}).get("magnitude", 0) * sx),
        "h_emu": int(s.get("height", {}).get("magnitude", 0) * sy),
    }


def _find_logo_element(slide: dict) -> dict | None:
    """Pick the most likely client-logo image on a slide.

    Heuristic: smallest image whose width is < 200pt and whose top-left is in
    the bottom-left quadrant of the slide — a common wordmark placement on
    cover/closing slides. Falls back to "smallest image overall" if no
    quadrant match.

    Skips full-bleed images (≥ 600pt wide) which are always backgrounds /
    hero photography.
    """
    candidates: list[tuple[float, dict]] = []
    fallback: list[tuple[float, dict]] = []
    for el in slide.get("pageElements", []):
        if "image" not in el:
            continue
        geom = _element_geometry_pt(el)
        w_pt = geom["w_emu"] / PT_TO_EMU
        h_pt = geom["h_emu"] / PT_TO_EMU
        x_pt = geom["x_emu"] / PT_TO_EMU
        y_pt = geom["y_emu"] / PT_TO_EMU
        if w_pt >= 600:  # background / hero
            continue
        if w_pt > 250 or h_pt > 80:  # too big to be a wordmark
            continue
        # Prefer bottom-left quadrant — a common wordmark placement on cover/closing slides
        if x_pt < 360 and y_pt > 200:
            candidates.append((w_pt * h_pt, el))
        else:
            fallback.append((w_pt * h_pt, el))
    pool = candidates or fallback
    if not pool:
        return None
    pool.sort(key=lambda t: t[0])
    return pool[0][1]
