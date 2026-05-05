"""Template library: ingest decks into a structured registry and assemble new decks.

Three tools:

1. ``summarize_deck``   — inspect a single deck and return a structured slide index.
2. ``build_template_library`` — summarize multiple decks and optionally write a JSON registry.
3. ``assemble_from_template`` — assemble a new deck by cherry-picking slides from the registry.

The workflow is intentionally generic: any user can point these tools at their own Google
Slides decks, get a structured registry they can review and edit, then pass picks back to
``assemble_from_template`` to build a new deck slide-by-slide.

Cross-deck copying routes through the deployed Apps Script web app (see
``tools/cross_deck.py`` and ``appscript/cross_deck_copy.gs``) because the Slides REST API
cannot copy slides across presentations.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..app import mcp
from ..auth import slide_service, drive_service
from ..util import parse_pres_id


# ---------------------------------------------------------------------------
# Internal helpers (local, independent of deck.py private helpers)
# ---------------------------------------------------------------------------

def _collect_text_runs(elements: list) -> list[str]:
    """Recursively walk pageElements and collect all non-empty text runs."""
    runs: list[str] = []
    for el in elements:
        # Shape text
        for te in el.get("shape", {}).get("text", {}).get("textElements", []):
            run = te.get("textRun", {}).get("content", "").strip()
            if run:
                runs.append(run)
        # Table cells
        for row in el.get("table", {}).get("tableRows", []):
            for cell in row.get("tableCells", []):
                for te in cell.get("text", {}).get("textElements", []):
                    run = te.get("textRun", {}).get("content", "").strip()
                    if run:
                        runs.append(run)
        # Groups — recurse
        children = el.get("elementGroup", {}).get("children", [])
        if children:
            runs.extend(_collect_text_runs(children))
    return runs


def _font_size_pt(style: dict) -> float:
    """Extract font size in points from a textStyle dict. Returns 0 if absent."""
    magnitude = style.get("fontSize", {}).get("magnitude", 0)
    return float(magnitude)


def _largest_text_element(elements: list, min_pt: float = 24.0) -> str:
    """Return the text of the largest text element whose font size >= min_pt.

    Walks top-level and grouped elements. Returns '' if none qualify.
    """
    best_pt = 0.0
    best_text = ""
    stack = list(elements)
    while stack:
        el = stack.pop()
        text_obj = el.get("shape", {}).get("text", {})
        chunks: list[str] = []
        for te in text_obj.get("textElements", []):
            run_content = te.get("textRun", {}).get("content", "").strip()
            run_style = te.get("textRun", {}).get("style", {})
            para_style = te.get("paragraphMarker", {}).get("style", {})
            pt = _font_size_pt(run_style) or _font_size_pt(para_style)
            if run_content and pt >= min_pt and pt > best_pt:
                best_pt = pt
                chunks = [run_content]
            elif run_content and pt >= min_pt and pt == best_pt:
                chunks.append(run_content)
        if chunks:
            best_text = " ".join(chunks)
        # Recurse into groups
        stack.extend(el.get("elementGroup", {}).get("children", []))
    return best_text


def _infer_topic(slide: dict) -> str:
    """Infer a short topic label for a slide.

    Priority order:
    1. alt_title (``title`` or ``description``) on any page element, ≤ 80 chars.
    2. Text of the largest text element with font size ≥ 24pt, trimmed to 80 chars.
    3. First text run on the slide, trimmed to 80 chars.
    4. Empty string.

    Speaker notes (priority 1 in the spec) are skipped — the notesPage is not
    included in a standard presentations.get() response and requires a separate
    call per slide, which would be prohibitively slow for large decks.
    """
    elements = slide.get("pageElements", [])

    # Priority 1: alt_title on any element
    for el in elements:
        alt = (el.get("title") or el.get("description") or "").strip()
        if alt:
            return alt[:80]

    # Priority 2: largest text element >= 24pt
    large = _largest_text_element(elements, min_pt=24.0).strip()
    if large:
        return large[:80]

    # Priority 3: first text run
    runs = _collect_text_runs(elements)
    if runs:
        return runs[0][:80]

    return ""


def _summarize_slide(slide: dict, index: int) -> dict:
    """Build the per-slide summary dict."""
    elements = slide.get("pageElements", [])
    element_count = len(elements)

    has_image = any("image" in el for el in elements)

    runs = _collect_text_runs(elements)
    text_snippet = " ".join(runs)[:200]

    topic = _infer_topic(slide)

    return {
        "index": index,
        "object_id": slide["objectId"],
        "topic": topic,
        "text_snippet": text_snippet,
        "element_count": element_count,
        "has_image": has_image,
    }


# ---------------------------------------------------------------------------
# Tool 1: summarize_deck
# ---------------------------------------------------------------------------

@mcp.tool()
def summarize_deck(presentation: str) -> dict:
    """Inspect a single deck and return a structured slide-by-slide index.

    Useful for building or updating a template library: run this over each of
    your decks, review the output, then pass picks to ``assemble_from_template``.

    Args:
        presentation: Google Slides deck — bare ID or full URL.

    Returns:
        {
            "drive_id": "<deck id>",
            "title": "<deck title>",
            "slide_count": N,
            "slides": [
                {
                    "index": 1,         # 1-based
                    "object_id": "...",
                    "topic": "...",     # best-effort label (see heuristic below)
                    "text_snippet": "...",  # concatenated text, up to 200 chars
                    "element_count": N,
                    "has_image": bool,
                },
                ...
            ],
        }

    Topic heuristic (in priority order):
    1. alt_title (the ``title`` or ``description`` field) set on any page element.
    2. Text of the largest text element whose font size is >= 24pt.
    3. First text run on the slide.
    4. Empty string.

    Note: speaker-note-based topic inference is intentionally omitted — the
    notesPage is not part of the standard presentations.get() response and
    fetching it per slide would be prohibitively slow for large decks.
    """
    pid = parse_pres_id(presentation)

    pres = slide_service().presentations().get(presentationId=pid).execute()
    meta = drive_service().files().get(
        fileId=pid, fields="id,name", supportsAllDrives=True
    ).execute()

    slides_data = []
    for idx, slide in enumerate(pres.get("slides", []), 1):
        slides_data.append(_summarize_slide(slide, idx))

    return {
        "drive_id": pid,
        "title": meta.get("name", ""),
        "slide_count": len(slides_data),
        "slides": slides_data,
    }


# ---------------------------------------------------------------------------
# Tool 2: build_template_library
# ---------------------------------------------------------------------------

@mcp.tool()
def build_template_library(
    decks: list[str],
    output_path: str | None = None,
) -> dict:
    """Summarize multiple decks and return a unified template library registry.

    Calls ``summarize_deck`` over each entry in ``decks`` and aggregates the
    results. If ``output_path`` is provided the JSON is written there so you can
    review, edit, and share the registry outside the MCP session.

    Args:
        decks: list of deck IDs or URLs to ingest.
        output_path: optional file path to write the registry JSON (indent=2).
            Parent directory must exist. If omitted, no file is written.

    Returns:
        {
            "version": 1,
            "decks": [<summarize_deck output per deck>],
            "deck_count": N,
            "total_slides": M,
            "output_path": "<path>",   # only present when output_path was given
        }

    Error handling: if any single deck fails (e.g. you lack read access), the
    exception propagates and no output file is written. Remove that deck from
    the list and retry.
    """
    summaries = [summarize_deck(d) for d in decks]

    result: dict = {
        "version": 1,
        "decks": summaries,
        "deck_count": len(summaries),
        "total_slides": sum(s["slide_count"] for s in summaries),
    }

    if output_path is not None:
        Path(output_path).write_text(json.dumps(result, indent=2))
        result["output_path"] = output_path

    return result


# ---------------------------------------------------------------------------
# Tool 3: assemble_from_template
# ---------------------------------------------------------------------------

@mcp.tool()
def assemble_from_template(
    picks: list[dict],
    dst_title: str,
    parent_folder_id: str | None = None,
) -> dict:
    """Assemble a new deck by cherry-picking slides from template decks.

    Each entry in ``picks`` names a source deck and a slide reference:

        [
            {"deck": "<src deck id or URL>", "slide": "<1-based index OR objectId>"},
            ...
        ]

    Steps:
    1. Create a new blank Google Slides deck titled ``dst_title``.
    2. Optionally move it to ``parent_folder_id`` (soft failure — see result).
    3. Copy each picked slide (in order) into the new deck via the Apps Script
       cross-deck copy helper. The Slides REST API cannot copy slides across
       presentations; Apps Script's ``SlidesApp.appendSlide`` does.
    4. Delete the default blank slide that Google inserts into every new deck.

    Args:
        picks: non-empty list of ``{"deck": ..., "slide": ...}`` dicts.
        dst_title: title for the new presentation.
        parent_folder_id: optional Drive folder ID to move the new deck into.
            On failure (e.g. shared-drive permission mismatch) the error is
            recorded in the result and the deck is left in Drive root — the
            assembly itself is not aborted.

    Returns:
        {
            "presentation_id": "...",
            "url": "https://docs.google.com/presentation/d/.../edit",
            "title": dst_title,
            "copied": [
                {"deck": "<src>", "slide": "<src ref>", "new_slide_id": "...", "dst_index": N},
                ...
            ],
            "parent_folder_id": parent_folder_id,
            "folder_move": "ok" | "skipped" | "failed: <reason>",
        }

    Raises:
        ValueError: if ``picks`` is empty or any pick is missing ``deck`` / ``slide`` keys.
        RuntimeError: if the Apps Script web app URL is not configured (see cross_deck.py).
    """
    from . import cross_deck as _cross_deck

    # --- Validate inputs ---
    if not picks:
        raise ValueError("picks must be a non-empty list")
    for i, pick in enumerate(picks):
        if "deck" not in pick or "slide" not in pick:
            raise ValueError(
                f"picks[{i}] is missing required keys — expected {{'deck': ..., 'slide': ...}}, "
                f"got {list(pick.keys())!r}"
            )

    # --- 1. Create a new blank deck ---
    svc = slide_service()
    new_pres = svc.presentations().create(body={"title": dst_title}).execute()
    new_id: str = new_pres["presentationId"]

    # --- 2. Optionally move to parent folder ---
    folder_move: str
    if parent_folder_id is None:
        folder_move = "skipped"
    else:
        try:
            # Remove from current parents, add to target folder
            existing = drive_service().files().get(
                fileId=new_id, fields="parents", supportsAllDrives=True
            ).execute()
            current_parents = ",".join(existing.get("parents", []))
            drive_service().files().update(
                fileId=new_id,
                addParents=parent_folder_id,
                removeParents=current_parents,
                supportsAllDrives=True,
                fields="id,parents",
            ).execute()
            folder_move = "ok"
        except Exception as exc:
            folder_move = f"failed: {exc}"

    # --- 3. Copy each picked slide ---
    copied: list[dict] = []
    copied_ids: set[str] = set()

    for pick in picks:
        result = _cross_deck.copy_slide_cross_deck(
            src_presentation=pick["deck"],
            src_slide=pick["slide"],
            dst_presentation=new_id,
        )
        new_slide_id = result.get("newSlideId", "")
        dst_index = result.get("dstIndex")
        if new_slide_id:
            copied_ids.add(new_slide_id)
        copied.append({
            "deck": pick["deck"],
            "slide": pick["slide"],
            "new_slide_id": new_slide_id,
            "dst_index": dst_index,
        })

    # --- 4. Delete the default blank slide ---
    # After creation and copies the deck has the default blank slide at index 0
    # plus all copied slides. The blank slide's objectId is NOT in copied_ids.
    refreshed = svc.presentations().get(presentationId=new_id).execute()
    blank_id: str | None = None
    for sl in refreshed.get("slides", []):
        if sl["objectId"] not in copied_ids:
            blank_id = sl["objectId"]
            break

    if blank_id is not None:
        svc.presentations().batchUpdate(
            presentationId=new_id,
            body={"requests": [{"deleteObject": {"objectId": blank_id}}]},
        ).execute()

    return {
        "presentation_id": new_id,
        "url": f"https://docs.google.com/presentation/d/{new_id}/edit",
        "title": dst_title,
        "copied": copied,
        "parent_folder_id": parent_folder_id,
        "folder_move": folder_move,
    }
