# Template Library Workflow — Worked Example

This example shows the full flow: ingest three source decks, build a registry, pick slides, and assemble a new deck.

---

## Source decks

Assume you have three decks on Google Drive:

| Deck | Purpose | Drive ID |
|------|---------|----------|
| Q3 sales pitch | External sales deck, 12 slides | `1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2Upms` |
| Product launch | Launch announcement, 15 slides | `1EiwhyBqO8bNj5ayWwXgkYqJFvYKl5bWRJd4M5XYZ999` |
| Internal all-hands | Company-wide update, 10 slides | `1FjXzN1pqrCdA2bBcCeEfGhHiIjJkKlLmMnNoOpPqQrR` |

---

## Step 1 — Build the registry

```python
build_template_library(
    decks=[
        "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2Upms",
        "1EiwhyBqO8bNj5ayWwXgkYqJFvYKl5bWRJd4M5XYZ999",
        "1FjXzN1pqrCdA2bBcCeEfGhHiIjJkKlLmMnNoOpPqQrR",
    ],
    output_path="./library.json"
)
```

The tool summarizes each deck and writes `library.json`. Returned metadata:

```json
{
  "version": 1,
  "deck_count": 3,
  "total_slides": 37,
  "output_path": "./library.json"
}
```

---

## Step 2 — Review the registry

Open `library.json`. A truncated view of the relevant sections:

```json
{
  "version": 1,
  "decks": [
    {
      "drive_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2Upms",
      "title": "Q3 sales pitch",
      "slide_count": 12,
      "slides": [
        {
          "index": 1,
          "object_id": "g1a2b3c4d5e_0",
          "topic": "Q3 Sales Pitch",
          "text_snippet": "Q3 Sales Pitch  Confidential",
          "element_count": 4,
          "has_image": true
        },
        {
          "index": 5,
          "object_id": "g1a2b3c4d5e_4",
          "topic": "Why Us",
          "text_snippet": "Why Us  Proven track record  50+ enterprise clients  99.9% uptime SLA",
          "element_count": 6,
          "has_image": false
        }
      ]
    },
    {
      "drive_id": "1EiwhyBqO8bNj5ayWwXgkYqJFvYKl5bWRJd4M5XYZ999",
      "title": "Product launch",
      "slide_count": 15,
      "slides": [
        {
          "index": 3,
          "object_id": "g2b3c4d5e6f_2",
          "topic": "The Problem",
          "text_snippet": "Teams spend 40% of their time on manual reporting. There is no single source of truth.",
          "element_count": 5,
          "has_image": false
        },
        {
          "index": 9,
          "object_id": "g2b3c4d5e6f_8",
          "topic": "Roadmap 2025",
          "text_snippet": "Q1: Data connectors  Q2: Automated summaries  Q3: Team collaboration  Q4: Enterprise SSO",
          "element_count": 8,
          "has_image": false
        }
      ]
    },
    {
      "drive_id": "1FjXzN1pqrCdA2bBcCeEfGhHiIjJkKlLmMnNoOpPqQrR",
      "title": "Internal all-hands",
      "slide_count": 10,
      "slides": [
        {
          "index": 6,
          "object_id": "g3c4d5e6f7g_5",
          "topic": "Pricing",
          "text_snippet": "Starter $49/mo  Growth $149/mo  Enterprise custom",
          "element_count": 10,
          "has_image": false
        }
      ]
    }
  ]
}
```

From this you can see:

- Slide 1 of the sales deck is a branded cover with an image.
- Slide 3 of the product launch deck is the "problem statement".
- Slide 9 of the product launch deck is the roadmap.
- Slide 6 of the all-hands deck is the pricing table.

---

## Step 3 — Build the picks list

You want a short external proposal deck: cover, problem statement, roadmap, pricing.

```python
picks = [
    {"deck": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2Upms", "slide": 1},
    {"deck": "1EiwhyBqO8bNj5ayWwXgkYqJFvYKl5bWRJd4M5XYZ999", "slide": 3},
    {"deck": "1EiwhyBqO8bNj5ayWwXgkYqJFvYKl5bWRJd4M5XYZ999", "slide": 9},
    {"deck": "1FjXzN1pqrCdA2bBcCeEfGhHiIjJkKlLmMnNoOpPqQrR", "slide": 6},
]
```

The list is in slide order for the new deck. You can mix indexes and `object_id` strings — both are accepted.

---

## Step 4 — Assemble the deck

```python
assemble_from_template(
    picks=picks,
    dst_title="Acme Corp Proposal",
    parent_folder_id="PUT_YOUR_FOLDER_ID_HERE"
)
```

Sample response (after ~5–8 seconds for four slides):

```json
{
  "presentation_id": "1ZnewDECKidABCDEFGHIJKLMNOPQRSTUVWXYZ12345678",
  "url": "https://docs.google.com/presentation/d/1ZnewDECKidABCDEFGHIJKLMNOPQRSTUVWXYZ12345678/edit",
  "title": "Acme Corp Proposal",
  "copied": [
    {"deck": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2Upms", "slide": 1, "new_slide_id": "gNEW1_0", "dst_index": 0},
    {"deck": "1EiwhyBqO8bNj5ayWwXgkYqJFvYKl5bWRJd4M5XYZ999", "slide": 3, "new_slide_id": "gNEW1_1", "dst_index": 1},
    {"deck": "1EiwhyBqO8bNj5ayWwXgkYqJFvYKl5bWRJd4M5XYZ999", "slide": 9, "new_slide_id": "gNEW1_2", "dst_index": 2},
    {"deck": "1FjXzN1pqrCdA2bBcCeEfGhHiIjJkKlLmMnNoOpPqQrR", "slide": 6, "new_slide_id": "gNEW1_3", "dst_index": 3}
  ],
  "parent_folder_id": "PUT_YOUR_FOLDER_ID_HERE",
  "folder_move": "ok"
}
```

---

## Step 5 — Review the output

Open the URL from the response, or use `screenshot_range` to capture all four slides without leaving your MCP client:

```python
screenshot_range(
    presentation="1ZnewDECKidABCDEFGHIJKLMNOPQRSTUVWXYZ12345678",
    start=1,
    end=4
)
```

From here you can use `replace_text`, `write_text_markdown`, or `insert_image` to customize any slide before sharing the deck.

---

## Notes

- `library.json` is a plain file you can edit between runs. Adjust `topic` labels, remove slides you never use, or add notes — the tools only read the `drive_id` and per-slide `index` / `object_id` fields when assembling.
- The cross-deck copy requires the Apps Script web app to be deployed. See [docs/appscript-setup.md](../docs/appscript-setup.md).
- If a source deck changes (slides added, removed, or reordered), re-run `build_template_library` to refresh the registry before picking slides.
