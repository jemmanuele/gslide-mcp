"""Auth + persistent client.

The whole MCP runs in one process, so OAuth + service Resources load ONCE at
startup and every tool reuses them. This is the single biggest win over the
CLI-script architecture (which cold-started Python+OAuth on every call).

On first run (no token.json), an interactive OAuth browser flow is launched.
The resulting token is saved to <cred_dir>/token.json (mode 0o600) and reused
on subsequent starts (with automatic refresh when expired).

All user-facing messages go to sys.stderr — stdout is the JSON-RPC channel.
"""

from __future__ import annotations

import functools
import os
import sys
from pathlib import Path

from gslides_api.client import GoogleAPIClient


def _write_token_atomic(token_path: Path, payload: str) -> None:
    """Write ``payload`` to ``token_path`` at mode 0o600 atomically.

    Plain ``write_text`` + ``chmod`` leaves a brief window where the file
    exists at the default umask (typically 0o644). On a shared host that's
    enough for a co-tenant to read the OAuth token. ``os.open`` with explicit
    0o600 mode closes that window.

    ``O_CREAT`` only sets the mode when the file is being created, so we
    also re-chmod in case ``token.json`` already existed at a permissive
    mode from a previous run.
    """
    fd = os.open(str(token_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write(payload)
    os.chmod(str(token_path), 0o600)


SCOPES = [
    "https://www.googleapis.com/auth/presentations",
    "https://www.googleapis.com/auth/drive",
]

DEFAULT_CRED_DIR = Path.home() / ".gslides-mcp" / "creds"

_SETUP_MESSAGE = """\
gslides-mcp: missing credentials.json at {creds_path}

To authenticate this MCP server you need an OAuth 2.0 Client ID:

  1. Open https://console.cloud.google.com/
  2. Create (or select) a project and enable the Google Slides API and Drive API.
  3. Go to "APIs & Services > Credentials" and click "Create Credentials >
     OAuth client ID".
  4. Choose Application type: Desktop app.
  5. Download the JSON file and save it to:
       {creds_path}
  6. Re-run the MCP server — a browser window will open to complete sign-in.

See docs/oauth-setup.md for step-by-step screenshots and troubleshooting.
"""


def cred_dir() -> Path:
    """Return the directory holding token.json + credentials.json.

    Override with the GSLIDES_MCP_CRED_DIR environment variable.
    The directory is created on first access if it does not exist.
    """
    d = Path(os.environ.get("GSLIDES_MCP_CRED_DIR", DEFAULT_CRED_DIR))
    d.mkdir(mode=0o700, parents=True, exist_ok=True)
    return d


def _run_oauth_flow(creds_path: Path, token_path: Path):
    """Run the InstalledAppFlow and save the resulting token."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    print(
        "gslides-mcp: opening browser for Google OAuth — "
        "follow the prompts then return here.",
        file=sys.stderr,
    )
    flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
    creds = flow.run_local_server(port=0)
    _write_token_atomic(token_path, creds.to_json())
    print(f"gslides-mcp: token saved to {token_path}", file=sys.stderr)
    return creds


def _load_or_refresh_creds(cred_directory: Path):
    """Return valid google.oauth2 Credentials, running OAuth if necessary."""
    import google.auth.transport.requests
    import google.oauth2.credentials

    token_path = cred_directory / "token.json"
    creds_path = cred_directory / "credentials.json"

    creds = None

    # --- Try to load an existing token ---
    if token_path.exists():
        try:
            creds = google.oauth2.credentials.Credentials.from_authorized_user_file(
                str(token_path), SCOPES
            )
        except Exception as exc:
            print(
                f"gslides-mcp: could not parse {token_path} ({exc}); re-authenticating.",
                file=sys.stderr,
            )
            creds = None

    # --- Refresh if expired ---
    if creds is not None and creds.expired and creds.refresh_token:
        try:
            creds.refresh(google.auth.transport.requests.Request())
            _write_token_atomic(token_path, creds.to_json())
            print("gslides-mcp: OAuth token refreshed.", file=sys.stderr)
        except Exception:
            creds = None  # fall through to full re-auth

    # --- Validate scopes — a token issued for a narrower scope set will
    # refresh successfully but fail at API call time. Force re-auth instead.
    if creds is not None and not all(s in (creds.scopes or []) for s in SCOPES):
        print(
            "gslides-mcp: token scopes do not cover required scopes; re-authenticating.",
            file=sys.stderr,
        )
        creds = None

    # --- Still not valid — run the full flow ---
    if creds is None or not creds.valid:
        if not creds_path.exists():
            raise RuntimeError(
                _SETUP_MESSAGE.format(creds_path=creds_path)
            )
        creds = _run_oauth_flow(creds_path, token_path)

    return creds


@functools.lru_cache(maxsize=1)
def client() -> GoogleAPIClient:
    """Persistent factory client. Holds OAuth + slide/drive Resources.

    First call may take ~1s (OAuth refresh + service build). Subsequent calls
    return the cached client instantly.
    """
    d = cred_dir()

    # Ensure we have valid credentials on disk before handing control to
    # gslides-api, which reads token.json directly from the directory.
    _load_or_refresh_creds(d)

    c = GoogleAPIClient(auto_flush=True)
    c.initialize_credentials(str(d))
    return c


def slide_service():
    """Shortcut: googleapiclient discovery Resource for slides v1."""
    return client().slide_service


def drive_service():
    """Shortcut: googleapiclient discovery Resource for drive v3."""
    return client().drive_service
