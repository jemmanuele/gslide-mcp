/**
 * Cross-deck slide copy via SlidesApp.appendSlide().
 *
 * The Slides REST API has NO cross-presentation copy. Apps Script's
 * SlidesApp.appendSlide(slide) does — it carries layout, theme, fonts,
 * images, and styling. This web app exposes that as an HTTP endpoint the
 * gslides MCP can call.
 *
 * Deployment (one-time):
 *   1. Open https://script.google.com → New project → name it
 *      "gslides-mcp cross-deck copy".
 *   2. Paste this entire file as Code.gs (replace the default).
 *   3. Project Settings → enable Slides API and Drive API (advanced services).
 *   4. Deploy → New deployment → type: Web app.
 *      - Execute as: Me (your account).
 *      - Who has access: Anyone (or "Anyone with Google account" if you
 *        prefer a softer scope; the URL is unguessable).
 *   5. Authorize when prompted.
 *   6. Copy the deployed URL (`/macros/s/AKfycbx.../exec`).
 *   7. Save it to `~/.gslides-mcp/appscript_url` (one-line text file) OR
 *      export `GSLIDES_MCP_APPSCRIPT_URL=...` before launching the MCP.
 *
 * Subsequent edits to this file: re-deploy via Manage Deployments → edit →
 * new version. The URL stays the same.
 */

function doPost(e) {
  try {
    var body = JSON.parse(e.postData.contents || "{}");
    var op = body.op || "copy";
    if (op === "copy") {
      return _json(copySlide_(body));
    } else if (op === "ping") {
      return _json({ok: true, version: "0.3"});
    } else {
      return _json({error: "unknown op: " + op}, 400);
    }
  } catch (err) {
    // Do not reflect err.stack — when this web app is deployed "Anyone",
    // any caller could probe it with malformed input and harvest script
    // internals via the response.
    return _json({error: String(err)}, 500);
  }
}

/**
 * Copy ONE slide from src to dst.
 *
 * @param {Object} req
 *   - srcId: source presentation ID
 *   - dstId: destination presentation ID
 *   - srcSlide: 1-based index OR objectId of slide to copy from src
 *   - insertionIndex: optional 0-based insertion index in dst (default = end)
 *
 * @return {Object} {newSlideId, dstIndex}
 */
function copySlide_(req) {
  var src = SlidesApp.openById(req.srcId);
  var dst = SlidesApp.openById(req.dstId);
  var srcSlide = _resolveSlide_(src, req.srcSlide);
  if (!srcSlide) {
    throw new Error("src slide not found: " + req.srcSlide);
  }

  var newSlide;
  var newIndex;
  if (typeof req.insertionIndex === "number") {
    newSlide = dst.insertSlide(req.insertionIndex, srcSlide);
    newIndex = req.insertionIndex;
  } else {
    // appendSlide: the new slide goes to the end.
    var existingCount = dst.getSlides().length;
    newSlide = dst.appendSlide(srcSlide);
    newIndex = existingCount;
  }

  // Apps Script auto-saves at script exit — no saveAndClose() + openById()
  // round-trip needed. Earlier versions did that and burned ~10-20s per
  // call; dropped after timeout regressions in high-slide-count workflows.
  return {newSlideId: newSlide.getObjectId(), dstIndex: newIndex};
}

function _resolveSlide_(presentation, ref) {
  // Numeric ref → 1-based index
  if (typeof ref === "number" || /^\d+$/.test(String(ref))) {
    var idx = parseInt(ref, 10) - 1;
    var slides = presentation.getSlides();
    return slides[idx] || null;
  }
  // String ref → objectId
  var slides = presentation.getSlides();
  for (var i = 0; i < slides.length; i++) {
    if (slides[i].getObjectId() === ref) {
      return slides[i];
    }
  }
  return null;
}

function _json(payload, status) {
  // Note: ContentService has no HTTP-status API; the `status` param is accepted
  // for caller intent but ignored. Errors are conveyed via the JSON body.
  var out = ContentService.createTextOutput(JSON.stringify(payload));
  out.setMimeType(ContentService.MimeType.JSON);
  return out;
}
