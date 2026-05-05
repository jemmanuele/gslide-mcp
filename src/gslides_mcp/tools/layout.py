"""Layout-level tools: transform, z-order, duplicate, delete elements."""

from __future__ import annotations

from ..app import mcp
from ..auth import slide_service
from ..util import parse_pres_id, find_element, PT_TO_EMU


@mcp.tool()
def transform_element(
    presentation: str,
    element: str,
    x_pt: float | None = None,
    y_pt: float | None = None,
    dx_pt: float | None = None,
    dy_pt: float | None = None,
) -> dict:
    """Move an element. Either absolute (x_pt, y_pt) or relative (dx_pt, dy_pt).

    Preserves the element's existing scaleX/scaleY (critical — naive
    `applyMode: ABSOLUTE` with `scale: 1` silently resizes elements that had
    custom scales applied at create time).
    """
    pid = parse_pres_id(presentation)
    svc = slide_service()
    pres = svc.presentations().get(presentationId=pid).execute()
    el, _slide = find_element(pres, element)
    if el is None:
        raise ValueError(f"element not found: {element!r}")
    t = el.get("transform", {})
    cur_sx = t.get("scaleX", 1)
    cur_sy = t.get("scaleY", 1)
    cur_tx = t.get("translateX", 0)
    cur_ty = t.get("translateY", 0)

    if (x_pt is None) != (y_pt is None):
        raise ValueError("x_pt and y_pt must be provided together")
    if (dx_pt is None) != (dy_pt is None):
        raise ValueError("dx_pt and dy_pt must be provided together")
    if x_pt is not None and dx_pt is not None:
        raise ValueError("provide either absolute (x_pt, y_pt) OR relative (dx_pt, dy_pt), not both")

    if x_pt is not None:
        new_tx = int(x_pt * PT_TO_EMU)
        new_ty = int(y_pt * PT_TO_EMU)
    elif dx_pt is not None:
        new_tx = int(cur_tx + dx_pt * PT_TO_EMU)
        new_ty = int(cur_ty + dy_pt * PT_TO_EMU)
    else:
        raise ValueError("provide absolute or relative coordinates")

    svc.presentations().batchUpdate(
        presentationId=pid,
        body={"requests": [{"updatePageElementTransform": {
            "objectId": element,
            "applyMode": "ABSOLUTE",
            "transform": {
                "scaleX": cur_sx, "scaleY": cur_sy,
                "translateX": new_tx, "translateY": new_ty,
                "unit": "EMU",
            },
        }}]},
    ).execute()
    return {"element": element, "x_emu": new_tx, "y_emu": new_ty}


@mcp.tool()
def zorder(presentation: str, elements: list[str], op: str) -> dict:
    """Z-order: BRING_TO_FRONT | SEND_TO_BACK | BRING_FORWARD | SEND_BACKWARD."""
    valid = {"BRING_TO_FRONT", "SEND_TO_BACK", "BRING_FORWARD", "SEND_BACKWARD"}
    if op not in valid:
        raise ValueError(f"op must be one of {valid}, got {op!r}")
    pid = parse_pres_id(presentation)
    slide_service().presentations().batchUpdate(
        presentationId=pid,
        body={"requests": [{"updatePageElementsZOrder": {
            "pageObjectIds": elements, "operation": op
        }}]},
    ).execute()
    return {"elements": elements, "op": op}


@mcp.tool()
def duplicate_element(
    presentation: str,
    element: str,
    new_id: str | None = None,
    dx_pt: float = 0.0,
    dy_pt: float = 0.0,
) -> dict:
    """Duplicate an element on the same slide, optionally offset by (dx, dy)."""
    pid = parse_pres_id(presentation)
    svc = slide_service()
    req: dict = {"duplicateObject": {"objectId": element}}
    if new_id:
        req["duplicateObject"]["objectIds"] = {element: new_id}
    resp = svc.presentations().batchUpdate(
        presentationId=pid, body={"requests": [req]}
    ).execute()
    dup_id = resp["replies"][0]["duplicateObject"]["objectId"]

    if dx_pt or dy_pt:
        # Shift the dup by (dx, dy). Relative apply preserves the dup's scale.
        svc.presentations().batchUpdate(
            presentationId=pid,
            body={"requests": [{"updatePageElementTransform": {
                "objectId": dup_id,
                "applyMode": "RELATIVE",
                "transform": {
                    "scaleX": 1, "scaleY": 1,
                    "translateX": int(dx_pt * PT_TO_EMU),
                    "translateY": int(dy_pt * PT_TO_EMU),
                    "unit": "EMU",
                },
            }}]},
        ).execute()
    return {"original": element, "duplicate": dup_id, "dx_pt": dx_pt, "dy_pt": dy_pt}


@mcp.tool()
def delete_elements(presentation: str, elements: list[str]) -> dict:
    """Delete one or more elements by objectId."""
    pid = parse_pres_id(presentation)
    reqs = [{"deleteObject": {"objectId": e}} for e in elements]
    slide_service().presentations().batchUpdate(
        presentationId=pid, body={"requests": reqs}
    ).execute()
    return {"deleted": elements}
