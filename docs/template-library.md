# Template Library Workflow

## What this is

The template library is a set of three MCP tools that let you turn any collection of your own Google Slides decks into a structured, reusable registry, then assemble new decks from cherry-picked slides:

- `summarize_deck(presentation)` — inspects a single deck and returns a structured slide-by-slide index.
- `build_template_library(decks, output_path?)` — summarizes multiple decks and aggregates the results into a single JSON registry, optionally writing it to a file.
- `assemble_from_template(picks, dst_title, parent_folder_id?)` — creates a new deck and copies slides into it in the order you specify.

The registry is plain JSON. You can save it, edit it, version it, or generate it programmatically — there is no proprietary format or database involved.

---

## Why

Without a template library, reusing slides across decks requires manually opening multiple presentations, remembering which deck has the timeline layout you want, copying slides one at a time, and cleaning up the formatting that breaks on paste. `assemble_from_template` replaces that workflow: describe which slides you want and in what order, and the tool does the copying.

The workflow is especially useful for pattern-matched deck types — proposals, case studies, quarterly reviews — where you want to pull "the cover slide from deck A, the problem-framing from deck B, the pricing table from deck C" without rebuilding them from scratch.

---

## Workflow walkthrough

### 1. Ingest your decks

Call `build_template_library` with a list of deck IDs or URLs and an optional output path:

```python
build_template_library(
    decks=[
        "https://docs.google.com/presentation/d/DECK_A_ID/edit",
        "https://docs.google.com/presentation/d/DECK_B_ID/edit",
        "https://docs.google.com/presentation/d/DECK_C_ID/edit",
    ],
    output_path="./library.json"
)
```

The tool calls `summarize_deck` on each deck in sequence and writes the result to `library.json`. The return value includes `{version, decks, deck_count, total_slides, output_path}`.

If any deck fails (e.g. missing read access), the exception propagates and no file is written. Remove the failing deck from the list and retry.

### 2. Review the registry

Open `library.json` and skim the slide summaries. Each slide entry looks like:

```json
{
  "index": 3,
  "object_id": "g1f2a3b4c5d_0",
  "topic": "Q3 Results",
  "text_snippet": "Revenue grew 18% YoY. Net new logos: 12. Churn held at 4.2%.",
  "element_count": 7,
  "has_image": true
}
```

Use `topic` and `text_snippet` to identify the slide you want. `has_image` and `element_count` give a rough sense of the slide's complexity.

You can edit the `topic` field manually if the inferred label is wrong — the registry is just a file.

### 3. Build a picks list

Construct a list of `{"deck": "<id or URL>", "slide": <1-based index or objectId>}` dicts. The order of the list is the order slides appear in the new deck:

```python
picks = [
    {"deck": "DECK_A_ID", "slide": 1},    # cover slide from deck A
    {"deck": "DECK_B_ID", "slide": 4},    # problem statement from deck B
    {"deck": "DECK_C_ID", "slide": 7},    # timeline from deck C
    {"deck": "DECK_A_ID", "slide": 9},    # pricing table from deck A
]
```

Both 1-based integer indexes and `object_id` strings are accepted as the `slide` value.

### 4. Assemble the new deck

```python
assemble_from_template(
    picks=picks,
    dst_title="Client Proposal — Acme Corp",
    parent_folder_id="OPTIONAL_DRIVE_FOLDER_ID"
)
```

The tool:
1. Creates a new blank Google Slides deck titled `dst_title`.
2. Optionally moves it into `parent_folder_id` (soft failure — if the move fails, the deck stays in Drive root and the error is recorded in the result, but the assembly continues).
3. Copies each slide in order via the Apps Script cross-deck copy helper.
4. Deletes the default blank slide Google inserts into every new deck.

Sample response:

```json
{
  "presentation_id": "NEW_DECK_ID",
  "url": "https://docs.google.com/presentation/d/NEW_DECK_ID/edit",
  "title": "Client Proposal — Acme Corp",
  "copied": [
    {"deck": "DECK_A_ID", "slide": 1, "new_slide_id": "g2a3b4c5d6e_0", "dst_index": 0},
    {"deck": "DECK_B_ID", "slide": 4, "new_slide_id": "g3b4c5d6e7f_0", "dst_index": 1},
    {"deck": "DECK_C_ID", "slide": 7, "new_slide_id": "g4c5d6e7f8g_0", "dst_index": 2},
    {"deck": "DECK_A_ID", "slide": 9, "new_slide_id": "g5d6e7f8g9h_0", "dst_index": 3}
  ],
  "parent_folder_id": "OPTIONAL_DRIVE_FOLDER_ID",
  "folder_move": "ok"
}
```

---

## Topic heuristic

`summarize_deck` infers a short label for each slide using the following priority order:

1. The `title` or `description` field set on any page element (the accessibility alt-title). If present, this wins and is truncated to 80 characters.
2. The text of the largest text element whose explicit font size is 24pt or larger. Trimmed to 80 characters.
3. The first text run on the slide. Trimmed to 80 characters.
4. Empty string.

**Limitation on priority 2**: Google Slides elements that inherit their font size from a layout or theme have no `fontSize` field in the API response. The heuristic treats them as 0pt and they do not qualify. On heavily theme-styled decks with no explicit font sizes set, priority 2 is often skipped and priority 3 provides the label.

**Speaker notes are intentionally omitted**: fetching notes requires a separate API call per slide and would be prohibitively slow for large decks.

---

## Limitations

- `assemble_from_template` and `copy_slide_cross_deck` require the Apps Script web app to be deployed. See [docs/appscript-setup.md](appscript-setup.md). Without it both tools raise a descriptive error.
- `element_count` and `has_image` reflect only top-level elements on the slide. Elements nested inside groups are not counted individually.
- Assembly is sequential — each slide copy is a separate HTTP round-trip to the Apps Script web app. Steady-state throughput is approximately 700ms–1.5s per slide. A 20-slide assembly takes roughly 15–30 seconds.
- `build_template_library` writes the output file using the path you supply. The parent directory must exist; the tool does not create it. Existing files at that path are overwritten without warning.

---

## Recovery from partial assembly

If `assemble_from_template` fails mid-loop (e.g. a network timeout or a source deck permission error), the exception message includes the URL of the partially-assembled destination deck:

```
copy failed at picks[3] (...); partial deck at
https://docs.google.com/presentation/d/NEW_DECK_ID/edit
has 3 slide(s) so far: <original error>
```

Open that URL in a browser to see the slides that were successfully copied. You can either delete the partial deck and retry, or complete the assembly by hand.
