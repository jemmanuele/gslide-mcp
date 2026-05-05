"""Shared helpers: ID parsing, geometry, color, range parsing."""

from __future__ import annotations

import re
from typing import Iterable

PT_TO_EMU = 12700
EMU_TO_PT = 1 / 12700
INCH_TO_EMU = 914_400
SUBTLE_BASE_EMU = 100_000  # for ROUND_RECTANGLE subtle-radius trick (~5px visual)

_PRES_ID_RE = re.compile(r"/presentation/d/([a-zA-Z0-9_-]+)")


def parse_pres_id(value: str) -> str:
    """Accept a bare presentation ID or a full Google Slides URL."""
    m = _PRES_ID_RE.search(value)
    return m.group(1) if m else value


def hex_to_rgb01(hex_str: str) -> tuple[float, float, float]:
    """Convert 'F1EBE0' or '#F1EBE0' to a (r, g, b) 0-1 float tuple."""
    h = hex_str.lstrip("#")
    return tuple(int(h[i : i + 2], 16) / 255.0 for i in (0, 2, 4))  # type: ignore[return-value]


def rgb_color(hex_str: str) -> dict:
    """Build a Slides API rgbColor object from a hex string."""
    r, g, b = hex_to_rgb01(hex_str)
    return {"red": r, "green": g, "blue": b}


def resolve_slide_ids(svc, pres_id: str, refs: Iterable) -> list[str]:
    """Resolve slide refs (1-based int/string OR objectId) to objectIds."""
    pres = svc.presentations().get(presentationId=pres_id).execute()
    slides = pres["slides"]
    by_index = {str(i): s["objectId"] for i, s in enumerate(slides, 1)}
    by_id = {s["objectId"]: s["objectId"] for s in slides}
    out = []
    for ref in refs:
        ref = str(ref).strip()
        if ref in by_index:
            out.append(by_index[ref])
        elif ref in by_id:
            out.append(by_id[ref])
        else:
            raise ValueError(f"slide ref not found: {ref!r}")
    return out


def parse_range(s: str) -> dict:
    """ALL or 'START:END' → Slides textRange dict."""
    if s.upper() == "ALL":
        return {"type": "ALL"}
    start, end = s.split(":")
    return {"type": "FIXED_RANGE", "startIndex": int(start), "endIndex": int(end)}


def find_element(pres: dict, element_id: str) -> tuple[dict | None, dict | None]:
    """Walk slides + nested groups for element_id. Returns (element, slide)."""

    def _search(elements, slide):
        for el in elements:
            if el.get("objectId") == element_id:
                return el, slide
            children = el.get("elementGroup", {}).get("children", [])
            if children:
                result = _search(children, slide)
                if result[0] is not None:
                    return result
        return None, None

    for slide in pres.get("slides", []):
        el, s = _search(slide.get("pageElements", []), slide)
        if el is not None:
            return el, s
    return None, None


def emu_to_pt(emu: int | float) -> float:
    return emu * EMU_TO_PT


def pt_to_emu(pt: int | float) -> int:
    return int(pt * PT_TO_EMU)


_OBJECT_ID_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]{4,49}$")


def validate_object_id(value: str | None) -> None:
    """Pre-flight check for custom Slides API objectIds.

    Slides API rules:
        - Length 5–50 chars.
        - Allowed chars: ``[a-zA-Z0-9_-]``.
        - Must start with alpha or underscore (digit-leading rejected by API).

    Raises ValueError with a clear message if invalid. No-op when ``value`` is
    None — None means "let the server pick one."
    """
    if value is None:
        return
    if not _OBJECT_ID_RE.match(value):
        raise ValueError(
            f"invalid object_id {value!r}: must be 5–50 chars, "
            f"start with [A-Za-z_], and use only [A-Za-z0-9_-]. "
            f"(Slides API rejects shorter/exotic IDs with HTTP 400.)"
        )
