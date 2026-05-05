# Apps Script Setup for Cross-Deck Copy

This guide explains how to deploy the `cross_deck_copy.gs` web app and connect it to the MCP server.

---

## Why it's needed

The Google Slides REST API has no endpoint for copying slides from one presentation to another. Google Apps Script does expose this capability through `SlidesApp.appendSlide(slide)` and `SlidesApp.insertSlide(index, slide)` — both carry the full layout, theme, fonts, images, and element styling across presentations.

The solution is a small Apps Script web app that the MCP server calls via HTTP. You deploy it once, under your own Google account, and it runs as you whenever the MCP calls it. The source code is at `appscript/cross_deck_copy.gs` in this repo.

Two MCP tools rely on this web app:

- `copy_slide_cross_deck` — copies a single slide from one deck to another.
- `assemble_from_template` — assembles a new deck from cherry-picked slides; it calls `copy_slide_cross_deck` in a loop.

Both raise a descriptive error if the URL is not configured.

---

## Step 1 — Create a new Apps Script project

1. Open [https://script.google.com](https://script.google.com) and sign in with the same Google account you authenticated the MCP server with.
2. Click **New project**.
3. Give the project a name: click "Untitled project" at the top left and type `gslides-mcp cross-deck copy`.

---

## Step 2 — Add the script

1. You will see a default file called `Code.gs` with a placeholder function. Select all the content and delete it.
2. Copy the entire contents of `appscript/cross_deck_copy.gs` from this repo and paste it into the editor.
3. Click the save icon (or press `Ctrl+S` / `Cmd+S`). The project saves automatically in the cloud.

---

## Step 3 — Enable Google APIs in the project

The script uses the Slides and Drive APIs as advanced services.

1. In the left sidebar of the Apps Script editor, click **Services** (the `+` icon next to "Services").
2. Find **Google Slides API** in the list, select it, and click **Add**.
3. Repeat for **Google Drive API**.

Both services should now appear in the left sidebar under "Services".

---

## Step 4 — Deploy as a Web App

1. Click **Deploy** in the top-right toolbar, then choose **New deployment**.
2. Click the gear icon next to "Select type" and choose **Web app**.
3. Fill in the deployment settings:
   - **Description**: anything you like, e.g. `v1`.
   - **Execute as**: **Me** — the script runs under your Google account, so it can access any deck your account can access.
   - **Who has access**: **Anyone** — this means the URL is functional without sign-in. The URL itself is unguessable (a long random path under `/macros/s/AKfycbx.../exec`). If you prefer a softer restriction, choose **Anyone with Google account** and the MCP will pass your OAuth token as a Bearer header on each request.
4. Click **Deploy**.
5. Google will ask you to authorize the script. Click **Authorize access**, choose your account, and grant the permissions shown (Slides and Drive).
6. After authorization the deployment dialog shows a **Web app URL**. It looks like:

   ```
   https://script.google.com/macros/s/AKfycbx.../exec
   ```

   Copy this URL. You will need it in the next step.

---

## Step 5 — Save the URL

Choose one of the two methods below.

**Option A — file** (recommended for local use):

```sh
echo "https://script.google.com/macros/s/AKfycbx.../exec" > ~/.gslides-mcp/appscript_url
```

The file must contain the URL as a single line with no quotes.

**Option B — environment variable**:

```sh
export GSLIDES_MCP_APPSCRIPT_URL="https://script.google.com/macros/s/AKfycbx.../exec"
```

To persist this across sessions, add the export line to your shell profile (`~/.zshrc`, `~/.bashrc`, etc.), or set it in your MCP client's config:

```json
{
  "mcpServers": {
    "gslides": {
      "command": "gslides-mcp",
      "env": {
        "GSLIDES_MCP_APPSCRIPT_URL": "https://script.google.com/macros/s/AKfycbx.../exec"
      }
    }
  }
}
```

---

## Step 6 — Verify the deployment

From your MCP client, call `cross_deck_ping`. Expected response:

```json
{"ok": true, "version": "0.3", "url": "https://script.google.com/macros/s/AKfycbx.../exec"}
```

If you get an error, check the troubleshooting section below.

---

## Updating the script

If you need to update `Code.gs` (e.g. after pulling a new version of this repo):

1. Open [https://script.google.com](https://script.google.com) and open the `gslides-mcp cross-deck copy` project.
2. Replace the contents of `Code.gs` with the updated file and save.
3. Click **Deploy** > **Manage deployments**.
4. Find your existing deployment, click the pencil (edit) icon.
5. Under **Version**, choose **New version** and click **Deploy**.

The deployed URL does not change when you create a new version — you do not need to update the saved URL.

---

## Troubleshooting

### `cross-deck copy requires a deployed Apps Script web app`

The MCP could not find the URL. Check that either:

- `~/.gslides-mcp/appscript_url` exists and contains the URL (no extra whitespace or quotes).
- `GSLIDES_MCP_APPSCRIPT_URL` is set in the environment where the MCP server process runs.

### HTTP 401 from the web app

The deployment may have been set to "Anyone with Google account" and the Bearer token was rejected or missing. Either switch the access level to **Anyone** in the deployment settings (re-deploy), or ensure the MCP server has a valid `token.json` so it can attach a Bearer token.

### HTTP 500 from the web app

An unhandled error occurred inside the script. To diagnose:

1. Open the Apps Script project at [https://script.google.com](https://script.google.com).
2. In the left sidebar, click **Executions** (clock icon). Find the failing execution and expand it to see the error message and stack trace.

Common causes:
- The source deck ID is wrong or the account does not have read access.
- The destination deck ID is wrong or the account does not have edit access.
- The slide index is out of range.

### `cross_deck_ping` returns the wrong version

You may be running an old deployment. Follow the update steps above to create a new version. The current expected version string is `"0.3"`.

### Timeouts on large decks

Apps Script has a 6-minute execution limit per call. Individual `copy_slide_cross_deck` calls time out after 180 seconds on the MCP side. Very large slides (many high-resolution images) can occasionally exceed this. If you see timeouts:

- Try splitting a large `assemble_from_template` call into smaller batches.
- Re-check the Apps Script Executions log for the actual error.
