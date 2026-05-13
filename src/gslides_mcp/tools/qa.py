"""QA tools: screenshot (returns inline image to Claude), overlap_check.

screenshot returns an MCP `Image` content type so Claude sees the rendered
slide directly — eliminates the manual download + Read PNG dance.
"""

from __future__ import annotations

import os
import ssl
import tempfile
import urllib.request

import certifi
from mcp.server.fastmcp import Image

from ..app import mcp
from ..auth import slide_service
from ..util import parse_pres_id, resolve_slide_ids, EMU_TO_PT


_SSL_CTX = ssl.create_default_context(cafile=certifi.where())


def _download_to(url: str, dst: str, timeout: float = 30.0) -> None:
    """Fetch ``url`` and write the response body to ``dst``.

    Uses the certifi CA bundle to sidestep macOS framework Python's missing
    system certs (the original reason this code shelled out to ``curl``).
    Cleans up the destination file if the download fails partway.
    """
    req = urllib.request.Request(url, headers={"User-Agent": "gslides-mcp/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as resp, \
                open(dst, "wb") as fh:
            while True:
                chunk = resp.read(64 * 1024)
                if not chunk:
                    break
                fh.write(chunk)
    except Exception:
        # Don't leave half-written PNGs lying in /tmp
        try:
            os.unlink(dst)
        except OSError:
            pass
        raise


def _render_thumbnail(svc, pid: str, slide_object_id: str, size: str) -> Image:
    """Fetch a single slide thumbnail and return as an inline Image."""
    t = svc.presentations().pages().getThumbnail(
        presentationId=pid,
        pageObjectId=slide_object_id,
        thumbnailProperties_thumbnailSize=size,
    ).execute()
    fd, path = tempfile.mkstemp(suffix=".png", prefix="gslides_thumb_")
    os.close(fd)
    _download_to(t["contentUrl"], path)
    return Image(path=path)


@mcp.tool()
def screenshot(presentation: str, slide: str, size: str = "LARGE") -> Image:
    """Render a slide thumbnail and return as an inline image.

    Args:
        slide: 1-based index or objectId.
        size: SMALL (~200w) | MEDIUM (~800w) | LARGE (~1600w). Default LARGE.

    Returns: inline PNG image — Claude sees it directly, no separate Read step.
    """
    pid = parse_pres_id(presentation)
    svc = slide_service()
    sid = resolve_slide_ids(svc, pid, [slide])[0]
    return _render_thumbnail(svc, pid, sid, size)


@mcp.tool()
def screenshot_range(presentation: str, slides: list[str], size: str = "MEDIUM") -> Image:
    """Render multiple slides in one call as a single vertical-strip image.

    Cuts QA round-trips for multi-slide review (e.g. validating a 15-slide
    deck after a build). All requested thumbnails composite into one tall PNG
    with a thin gap between each, captioned with the slide index. Default
    size is MEDIUM since LARGE × N gets heavy on transport.

    Args:
        slides: list of 1-based indexes or objectIds (any mix). Order
            preserved top-to-bottom in the strip.
        size: SMALL | MEDIUM | LARGE. Default MEDIUM (recommended for batch QA).

    Returns: a single inline PNG with all thumbnails stacked vertically,
    each labeled by its slide index. Claude sees the whole strip in one go.

    Note: returns a vertical strip (not a list of images) because FastMCP /
    pydantic doesn't auto-schema ``list[Image]``. Compositing also gives
    natural side-by-side comparison in a single visual.
    """
    from PIL import Image as PILImage
    from PIL import ImageDraw, ImageFont

    pid = parse_pres_id(presentation)
    svc = slide_service()
    sids = resolve_slide_ids(svc, pid, slides)

    # Map sid → 1-based index for labels
    pres = svc.presentations().get(presentationId=pid).execute()
    sid_to_idx = {s["objectId"]: i for i, s in enumerate(pres["slides"], 1)}

    # Render each thumbnail to disk, then composite
    fd, strip_path = tempfile.mkstemp(suffix=".png", prefix="gslides_strip_")
    os.close(fd)

    pil_thumbs: list[tuple[int, "PILImage.Image"]] = []
    thumb_paths: list[str] = []
    try:
        for sid in sids:
            thumb_fd, thumb_path = tempfile.mkstemp(suffix=".png", prefix="gslides_thumb_")
            os.close(thumb_fd)
            thumb_paths.append(thumb_path)
            t = svc.presentations().pages().getThumbnail(
                presentationId=pid,
                pageObjectId=sid,
                thumbnailProperties_thumbnailSize=size,
            ).execute()
            _download_to(t["contentUrl"], thumb_path)
            pil_thumbs.append((sid_to_idx.get(sid, 0), PILImage.open(thumb_path).convert("RGB")))
    except Exception:
        for p in thumb_paths:
            try:
                os.unlink(p)
            except OSError:
                pass
        raise

    # Vertical strip: width = max thumb width, height = sum + gaps + label bands
    label_h = 24
    gap = 8
    max_w = max(im.width for _, im in pil_thumbs)
    total_h = sum(im.height + label_h + gap for _, im in pil_thumbs) - gap
    strip = PILImage.new("RGB", (max_w, total_h), (240, 240, 240))
    draw = ImageDraw.Draw(strip)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 14)
    except Exception:
        font = ImageFont.load_default()

    y = 0
    for idx, im in pil_thumbs:
        draw.rectangle([(0, y), (max_w, y + label_h)], fill=(30, 50, 40))
        draw.text((8, y + 4), f"slide {idx}", fill=(220, 240, 220), font=font)
        y += label_h
        # Center thumb if narrower than strip
        x = (max_w - im.width) // 2
        strip.paste(im, (x, y))
        y += im.height + gap

    strip.save(strip_path, "PNG", optimize=True)

    # Per-thumb PNGs are now composited into the strip; drop them so /tmp
    # doesn't fill up over a long-running server.
    for _, im in pil_thumbs:
        im.close()
    for p in thumb_paths:
        try:
            os.unlink(p)
        except OSError:
            pass

    return Image(path=strip_path)


@mcp.tool()
def overlap_check(presentation: str, slide: str, gap_threshold_pt: float = 5.0) -> dict:
    """Programmatic overlap audit: warns when text-element bottoms get within
    gap_threshold_pt of the next element's top.

    Catches text-box overflow that visual inspection misses (text expands past
    declared height; API gives no warning). Uses same-column heuristic
    (x positions within 50pt of each other).

    Returns: {warnings: [...], element_count}
    """
    pid = parse_pres_id(presentation)
    svc = slide_service()
    sid = resolve_slide_ids(svc, pid, [slide])[0]
    pres = svc.presentations().get(presentationId=pid).execute()
    sl = next(s for s in pres["slides"] if s["objectId"] == sid)

    elements = []
    for el in sl.get("pageElements", []):
        t = el.get("transform", {})
        s = el.get("size", {})
        sx, sy = t.get("scaleX", 1), t.get("scaleY", 1)
        tx, ty = t.get("translateX", 0), t.get("translateY", 0)
        w = s.get("width", {}).get("magnitude", 0) * sx
        h = s.get("height", {}).get("magnitude", 0) * sy
        elements.append({"id": el["objectId"], "x": tx, "y": ty, "bottom": ty + h, "h": h})

    warnings = []
    for i, a in enumerate(elements):
        for b in elements[i + 1 :]:
            same_col = abs(a["x"] - b["x"]) * EMU_TO_PT < 50
            a_above_b = a["bottom"] > b["y"] and a["y"] < b["y"]
            if same_col and a_above_b:
                gap_pt = (b["y"] - a["bottom"]) * EMU_TO_PT
                if gap_pt < gap_threshold_pt:
                    warnings.append({
                        "upper": a["id"],
                        "upper_bottom_pt": round(a["bottom"] * EMU_TO_PT, 1),
                        "lower": b["id"],
                        "lower_top_pt": round(b["y"] * EMU_TO_PT, 1),
                        "gap_pt": round(gap_pt, 1),
                    })
    return {"slide_id": sid, "warnings": warnings, "element_count": len(elements)}
