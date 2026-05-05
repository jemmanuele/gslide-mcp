"""Slide-level tools: create / copy / move / duplicate / delete / set background."""

from __future__ import annotations

from ..app import mcp
from ..auth import slide_service
from ..util import parse_pres_id, resolve_slide_ids, rgb_color, validate_object_id


@mcp.tool()
def create_slide(presentation: str, insertion_index: int, object_id: str | None = None) -> dict:
    """Create a blank slide at insertion_index (0-based).

    Note: omits slideLayoutReference so it works on any master that lacks BLANK
    (a known Slides API trap).

    Args:
        object_id: optional custom slide objectId. **Min 5 chars** —
            Slides API rejects shorter IDs ("s1", "t1", etc.) with HTTP 400.
            Allowed chars: ``[a-zA-Z0-9_-]``, must start with alpha/underscore.
    """
    validate_object_id(object_id)
    pid = parse_pres_id(presentation)
    req: dict = {"createSlide": {"insertionIndex": insertion_index}}
    if object_id:
        req["createSlide"]["objectId"] = object_id
    resp = slide_service().presentations().batchUpdate(
        presentationId=pid, body={"requests": [req]}
    ).execute()
    new_id = resp["replies"][0]["createSlide"]["objectId"]
    return {"slide_id": new_id}


@mcp.tool()
def duplicate_slide(presentation: str, slide: str, to_index: int | None = None) -> dict:
    """Duplicate a slide within the same deck. Optionally move to to_index (0-based).

    Args:
        slide: 1-based index or objectId of the slide to duplicate.
    """
    pid = parse_pres_id(presentation)
    svc = slide_service()
    src_id = resolve_slide_ids(svc, pid, [slide])[0]
    resp = svc.presentations().batchUpdate(
        presentationId=pid,
        body={"requests": [{"duplicateObject": {"objectId": src_id}}]},
    ).execute()
    new_id = resp["replies"][0]["duplicateObject"]["objectId"]
    if to_index is not None:
        svc.presentations().batchUpdate(
            presentationId=pid,
            body={"requests": [{"updateSlidesPosition": {
                "slideObjectIds": [new_id], "insertionIndex": to_index
            }}]},
        ).execute()
    return {"new_slide_id": new_id}


@mcp.tool()
def move_slide(presentation: str, slide: str, to_index: int) -> dict:
    """Move a single slide to to_index (0-based).

    NOTE: Moving multiple slides is index-shifting-error-prone — call this once
    per slide, re-reading positions in between, rather than batching.
    """
    pid = parse_pres_id(presentation)
    svc = slide_service()
    sid = resolve_slide_ids(svc, pid, [slide])[0]
    svc.presentations().batchUpdate(
        presentationId=pid,
        body={"requests": [{"updateSlidesPosition": {
            "slideObjectIds": [sid], "insertionIndex": to_index
        }}]},
    ).execute()
    return {"slide_id": sid, "moved_to": to_index}


@mcp.tool()
def delete_slides(presentation: str, slides: list[str]) -> dict:
    """Delete one or more slides. Refs can be 1-based indexes or objectIds.

    Re-resolves IDs once at the start, so order doesn't matter — but the deck
    must not be edited concurrently while this runs.
    """
    pid = parse_pres_id(presentation)
    svc = slide_service()
    ids = resolve_slide_ids(svc, pid, slides)
    reqs = [{"deleteObject": {"objectId": sid}} for sid in ids]
    svc.presentations().batchUpdate(
        presentationId=pid, body={"requests": reqs}
    ).execute()
    return {"deleted": ids}


@mcp.tool()
def set_background(presentation: str, slides: list[str], hex_color: str) -> dict:
    """Set solid background fill on one or more slides.

    Args:
        hex_color: e.g. 'F1EBE0' or '#F1EBE0'.
    """
    pid = parse_pres_id(presentation)
    svc = slide_service()
    ids = resolve_slide_ids(svc, pid, slides)
    reqs = [
        {
            "updatePageProperties": {
                "objectId": sid,
                "pageProperties": {
                    "pageBackgroundFill": {
                        "solidFill": {"color": {"rgbColor": rgb_color(hex_color)}}
                    }
                },
                "fields": "pageBackgroundFill.solidFill.color",
            }
        }
        for sid in ids
    ]
    svc.presentations().batchUpdate(
        presentationId=pid, body={"requests": reqs}
    ).execute()
    return {"updated": ids, "color": hex_color}
