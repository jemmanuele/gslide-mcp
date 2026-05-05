# gslide-mcp

A Python MCP server that exposes typed tools for building and editing Google Slides decks. It wraps the [gslides-api](https://pypi.org/project/gslides-api/) library and adds MCP tooling on top: markdown-aware text writing, slide screenshots, cross-deck copying, and a template-library workflow that lets you assemble new decks from slide fragments across any number of source decks.

## Why this exists

The Google Slides REST API and its Python client are expressive but verbose — a single formatted text update takes five nested request dicts. This server pre-composes the most common operations into typed MCP tools so a language model can build polished decks without reconstructing boilerplate every session. A small set of semantic shortcuts (`swap_client`, `fetch_logo_by_domain`, `assemble_from_template`) cover the tedious parts of agency-style deck work.

## Status

Early release. The API surface may shift between minor versions. Contributions welcome. Not affiliated with or endorsed by Google.

## Install

Requires Python 3.10 or newer.

```sh
git clone https://github.com/jan-emmanuele/gslide-mcp.git
cd gslide-mcp
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -e .
```

The entry point `gslides-mcp` is now on your PATH inside the venv.

## First-run setup (OAuth)

Full walkthrough: [docs/oauth-setup.md](docs/oauth-setup.md)

Three-step distillation:

1. In the [Google Cloud Console](https://console.cloud.google.com), create a **Desktop app** OAuth 2.0 Client ID with the Slides API and Drive API enabled.
2. Download the client-secret JSON, rename it `credentials.json`, and save it to `~/.gslides-mcp/creds/credentials.json`.
3. The first MCP tool call opens a browser tab for Google consent. After approval, `token.json` is written next to your credentials file (mode `0o600`) and reused from then on, with automatic refresh.

Required OAuth scopes:

```
https://www.googleapis.com/auth/presentations
https://www.googleapis.com/auth/drive
```

To store credentials somewhere other than `~/.gslides-mcp/creds/`, set `GSLIDES_MCP_CRED_DIR` to the desired directory before launching the server.

## Wiring it up to a client

Add the server to your Claude Desktop or Claude Code MCP config:

```json
{
  "mcpServers": {
    "gslides": {
      "command": "gslides-mcp"
    }
  }
}
```

If the entry point is not on your system PATH, use the full path to the venv binary, e.g. `"/path/to/venv/bin/gslides-mcp"`.

For debugging outside a client, run the server directly:

```sh
python -m gslides_mcp.server
```

## Tool overview

| Group | Tool | What it does |
|-------|------|--------------|
| **Deck** | `create_presentation` | Create a new blank deck; returns `{presentation_id, url}` |
| | `clone_deck` | Copy an existing deck via Drive |
| | `list_slides` | List slides with index, object ID, and summary |
| | `inspect_slide` | Inspect all elements on a slide (optionally recursive) |
| | `find_elements` | Search elements by type, alt-title, or text content |
| | `export_pres` | Export to local `.pptx` or `.pdf` |
| | `batch_apply` | Raw `batchUpdate` escape hatch for unsupported operations |
| **Slide** | `create_slide` | Insert a new slide at a given position |
| | `duplicate_slide` | Duplicate a slide within the same deck |
| | `move_slide` | Reorder a slide |
| | `delete_slides` | Delete one or more slides |
| | `set_background` | Set the slide background color (solid hex) |
| **Shape** | `create_shape` | Insert a shape |
| | `insert_image` | Insert an image by URL |
| | `set_fill` | Set the fill color of a shape |
| | `set_outline` | Set the outline of a shape |
| **Content** | `write_text_markdown` | Write bold/italic/bullets in one call via gslides-api's markdown writer |
| | `batch_write_markdown` | Batch version of `write_text_markdown` (~N× faster for multi-element updates) |
| | `set_text` | Set plain text on a shape |
| | `style_text` | Apply text styles (font, size, color) to a range |
| | `replace_text` | Find-and-replace text across a slide or deck |
| **Layout** | `transform_element` | Move an element (absolute or relative pt) |
| | `zorder` | Change element stacking order |
| | `duplicate_element` | Duplicate an element within a slide |
| | `delete_elements` | Delete one or more elements |
| **QA** | `screenshot` | Capture a slide as an inline image |
| | `screenshot_range` | Capture a range of slides |
| | `overlap_check` | Detect overlapping elements on a slide |
| **Cross-deck** | `copy_slide_cross_deck` | Copy a slide from one deck to another (requires Apps Script — see below) |
| | `cross_deck_ping` | Health-check the Apps Script web app |
| **Semantic** | `swap_client` | Clone a deck and rebrand it (logo swap, name replacement) in one call |
| **Assets** | `fetch_logo_by_domain` | Resolve a public logo URL for a brand by domain |
| **Library** | `summarize_deck` | Build a structured slide index for a single deck |
| | `build_template_library` | Summarize multiple decks into a reusable JSON registry |
| | `assemble_from_template` | Assemble a new deck from cherry-picked slides across decks |

## Optional: cross-deck copy via Apps Script

`copy_slide_cross_deck` and `assemble_from_template` route through a small Google Apps Script web app because the Slides REST API has no cross-presentation copy endpoint.

Setup guide: [docs/appscript-setup.md](docs/appscript-setup.md)

Once deployed, save the web-app URL to `~/.gslides-mcp/appscript_url` (one line, no quotes) or set `GSLIDES_MCP_APPSCRIPT_URL` in your environment. Without this configured, those two tools raise a descriptive error with setup instructions.

## Optional: logo.dev for `fetch_logo_by_domain`

`fetch_logo_by_domain` tries Wikipedia Commons, then Brandfetch CDN, then a Google favicon fallback by default. To enable the [logo.dev](https://logo.dev) source as an additional candidate:

```sh
export GSLIDES_MCP_LOGODEV_TOKEN=your_token_here
```

Without this variable set, logo.dev is skipped entirely and the fallback chain still produces a usable URL.

## The template-library workflow

See [docs/template-library.md](docs/template-library.md) for the full walkthrough and [examples/template_library_workflow.md](examples/template_library_workflow.md) for a concrete worked example.

In brief: `build_template_library` ingests a list of deck IDs into a JSON registry, you review and annotate it, then `assemble_from_template` pulls the slides you want into a new deck in the order you specify.

## Project layout

```
gslide-mcp/
├── README.md
├── LICENSE                         MIT license
├── pyproject.toml
├── appscript/
│   └── cross_deck_copy.gs          Apps Script web app for cross-deck copy
├── docs/
│   ├── oauth-setup.md              Google OAuth setup walkthrough
│   ├── appscript-setup.md          Apps Script deployment guide
│   └── template-library.md         Template library workflow
├── examples/
│   └── template_library_workflow.md  Worked example
└── src/gslides_mcp/
    ├── server.py                   MCP entry point
    ├── auth.py                     OAuth + service client
    ├── app.py                      MCP application instance
    ├── util.py                     Shared helpers
    └── tools/
        ├── deck.py
        ├── slides.py
        ├── shapes.py
        ├── content.py
        ├── layout.py
        ├── qa.py
        ├── cross_deck.py
        ├── semantic.py
        ├── assets.py
        └── library.py
```

## Contributing

Bug reports and pull requests are welcome at https://github.com/jan-emmanuele/gslide-mcp/issues.

## License

MIT. See [LICENSE](LICENSE).
