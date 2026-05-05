"""Shape-level tools: create_shape, insert_image, set_fill, set_outline.

Encodes the ROUND_RECTANGLE subtle-radius trick (small base + scale transform)
as a flag — see docs/shape-quirks.md for the why.
"""

from __future__ import annotations

from ..app import mcp
from ..auth import slide_service
from ..util import (
    parse_pres_id,
    resolve_slide_ids,
    rgb_color,
    validate_object_id,
    PT_TO_EMU,
    SUBTLE_BASE_EMU,
)


@mcp.tool()
def create_shape(
    presentation: str,
    slide: str,
    shape_type: str,
    x_pt: float,
    y_pt: float,
    width_pt: float,
    height_pt: float,
    object_id: str | None = None,
    fill_hex: str | None = None,
    no_outline: bool = False,
    subtle_radius: bool = False,
    alt_title: str | None = None,
) -> dict:
    """Create a shape on a slide. Geometry in points.

    Args:
        shape_type: TEXT_BOX, ROUND_RECTANGLE, RECTANGLE, ELLIPSE, etc.
        object_id: optional custom element objectId. **Min 5 chars** —
            Slides API rejects shorter IDs ("t1", "s1", etc.) with HTTP 400.
            Allowed chars: ``[a-zA-Z0-9_-]``, must start with alpha/underscore.
        subtle_radius: ROUND_RECTANGLE only. If true, declare shape at
            SUBTLE_BASE_EMU (100k) and scale up — gives ~5px visual radius
            instead of the aggressive default ~150px+.
        alt_title: sets the page-element alt-title. Required if you plan to
            address this element later via gslides-api's markdown writer
            (which looks up elements by name).
        no_outline: removes the default border.
        fill_hex: solid fill color, e.g. 'F1EBE0' or '#F1EBE0'.
    """
    validate_object_id(object_id)
    pid = parse_pres_id(presentation)
    svc = slide_service()
    sid = resolve_slide_ids(svc, pid, [slide])[0]

    tx_emu = int(x_pt * PT_TO_EMU)
    ty_emu = int(y_pt * PT_TO_EMU)
    tw_emu = int(width_pt * PT_TO_EMU)
    th_emu = int(height_pt * PT_TO_EMU)

    if subtle_radius:
        if shape_type != "ROUND_RECTANGLE":
            raise ValueError("subtle_radius only valid for ROUND_RECTANGLE")
        # Declare at small base, scale up via transform → radius proportional
        # to the small base, not the visible size.
        size = {"width": {"magnitude": SUBTLE_BASE_EMU, "unit": "EMU"},
                "height": {"magnitude": SUBTLE_BASE_EMU, "unit": "EMU"}}
        transform = {
            "scaleX": tw_emu / SUBTLE_BASE_EMU,
            "scaleY": th_emu / SUBTLE_BASE_EMU,
            "translateX": tx_emu, "translateY": ty_emu,
            "unit": "EMU",
        }
    else:
        size = {"width": {"magnitude": tw_emu, "unit": "EMU"},
                "height": {"magnitude": th_emu, "unit": "EMU"}}
        transform = {"scaleX": 1, "scaleY": 1,
                     "translateX": tx_emu, "translateY": ty_emu, "unit": "EMU"}

    create_req: dict = {
        "createShape": {
            "shapeType": shape_type,
            "elementProperties": {
                "pageObjectId": sid,
                "size": size,
                "transform": transform,
            },
        }
    }
    if object_id:
        create_req["createShape"]["objectId"] = object_id

    reqs: list[dict] = [create_req]
    final_id = object_id

    if final_id and (fill_hex or no_outline or alt_title):
        if fill_hex or no_outline:
            props: dict = {}
            fields: list[str] = []
            if fill_hex:
                props["shapeBackgroundFill"] = {
                    "solidFill": {"color": {"rgbColor": rgb_color(fill_hex)}}
                }
                fields.append("shapeBackgroundFill.solidFill.color")
            if no_outline:
                props["outline"] = {"propertyState": "NOT_RENDERED"}
                fields.append("outline.propertyState")
            reqs.append({"updateShapeProperties": {
                "objectId": final_id,
                "shapeProperties": props,
                "fields": ",".join(fields),
            }})
        if alt_title:
            reqs.append({"updatePageElementAltText": {
                "objectId": final_id, "title": alt_title, "description": ""
            }})
        svc.presentations().batchUpdate(
            presentationId=pid, body={"requests": reqs}
        ).execute()
    else:
        # Two-step: create, learn the ID, then update properties
        resp = svc.presentations().batchUpdate(
            presentationId=pid, body={"requests": reqs}
        ).execute()
        final_id = resp["replies"][0]["createShape"]["objectId"]

        followup: list[dict] = []
        if fill_hex or no_outline:
            props = {}
            fields = []
            if fill_hex:
                props["shapeBackgroundFill"] = {
                    "solidFill": {"color": {"rgbColor": rgb_color(fill_hex)}}
                }
                fields.append("shapeBackgroundFill.solidFill.color")
            if no_outline:
                props["outline"] = {"propertyState": "NOT_RENDERED"}
                fields.append("outline.propertyState")
            followup.append({"updateShapeProperties": {
                "objectId": final_id,
                "shapeProperties": props,
                "fields": ",".join(fields),
            }})
        if alt_title:
            followup.append({"updatePageElementAltText": {
                "objectId": final_id, "title": alt_title, "description": ""
            }})
        if followup:
            svc.presentations().batchUpdate(
                presentationId=pid, body={"requests": followup}
            ).execute()

    return {"object_id": final_id, "slide_id": sid, "shape_type": shape_type}


@mcp.tool()
def insert_image(
    presentation: str,
    slide: str,
    x_pt: float,
    y_pt: float,
    width_pt: float,
    height_pt: float,
    url: str | None = None,
    drive_file_id: str | None = None,
    object_id: str | None = None,
) -> dict:
    """Insert an image from a URL or a Drive file ID. Geometry in points.

    Args:
        object_id: optional custom element objectId. **Min 5 chars** —
            Slides API rejects shorter IDs ("img", "i1", etc.) with HTTP 400.
            Allowed chars: ``[a-zA-Z0-9_-]``, must start with alpha/underscore.
    """
    validate_object_id(object_id)
    if not url and not drive_file_id:
        raise ValueError("provide url or drive_file_id")
    pid = parse_pres_id(presentation)
    svc = slide_service()
    sid = resolve_slide_ids(svc, pid, [slide])[0]
    req: dict = {
        "createImage": {
            "elementProperties": {
                "pageObjectId": sid,
                "size": {"width": {"magnitude": int(width_pt * PT_TO_EMU), "unit": "EMU"},
                         "height": {"magnitude": int(height_pt * PT_TO_EMU), "unit": "EMU"}},
                "transform": {"scaleX": 1, "scaleY": 1,
                              "translateX": int(x_pt * PT_TO_EMU),
                              "translateY": int(y_pt * PT_TO_EMU),
                              "unit": "EMU"},
            }
        }
    }
    if url:
        req["createImage"]["url"] = url
    else:
        req["createImage"]["url"] = f"https://drive.google.com/uc?export=view&id={drive_file_id}"
    if object_id:
        req["createImage"]["objectId"] = object_id

    resp = svc.presentations().batchUpdate(
        presentationId=pid, body={"requests": [req]}
    ).execute()
    new_id = resp["replies"][0]["createImage"]["objectId"]
    return {"object_id": new_id, "slide_id": sid}


@mcp.tool()
def set_fill(presentation: str, element: str, hex_color: str | None = None) -> dict:
    """Set or remove solid shape fill.

    Args:
        hex_color: hex string to set, or None to remove fill.
    """
    pid = parse_pres_id(presentation)
    if hex_color is None:
        req = {"updateShapeProperties": {
            "objectId": element,
            "shapeProperties": {"shapeBackgroundFill": {"propertyState": "NOT_RENDERED"}},
            "fields": "shapeBackgroundFill.propertyState",
        }}
    else:
        req = {"updateShapeProperties": {
            "objectId": element,
            "shapeProperties": {
                "shapeBackgroundFill": {"solidFill": {"color": {"rgbColor": rgb_color(hex_color)}}}
            },
            "fields": "shapeBackgroundFill.solidFill.color",
        }}
    slide_service().presentations().batchUpdate(
        presentationId=pid, body={"requests": [req]}
    ).execute()
    return {"element": element, "fill": hex_color or "(removed)"}


@mcp.tool()
def set_outline(
    presentation: str,
    element: str,
    hex_color: str | None = None,
    weight_pt: float | None = None,
    no_outline: bool = False,
) -> dict:
    """Set, restyle, or remove a shape outline."""
    pid = parse_pres_id(presentation)
    if no_outline:
        req = {"updateShapeProperties": {
            "objectId": element,
            "shapeProperties": {"outline": {"propertyState": "NOT_RENDERED"}},
            "fields": "outline.propertyState",
        }}
    else:
        outline: dict = {"propertyState": "RENDERED"}
        fields_parts = ["outline.propertyState"]
        if hex_color:
            outline["outlineFill"] = {"solidFill": {"color": {"rgbColor": rgb_color(hex_color)}}}
            fields_parts.append("outline.outlineFill.solidFill.color")
        if weight_pt is not None:
            outline["weight"] = {"magnitude": weight_pt, "unit": "PT"}
            fields_parts.append("outline.weight")
        req = {"updateShapeProperties": {
            "objectId": element,
            "shapeProperties": {"outline": outline},
            "fields": ",".join(fields_parts),
        }}
    slide_service().presentations().batchUpdate(
        presentationId=pid, body={"requests": [req]}
    ).execute()
    return {"element": element, "outline": "removed" if no_outline else "set"}
