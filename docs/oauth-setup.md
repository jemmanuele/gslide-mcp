# OAuth Setup

This guide walks through creating a Google Cloud OAuth credential and getting the MCP server authenticated for the first time. It covers the Desktop app OAuth flow used by `gslides-mcp`.

---

## Prerequisites

- A Google account (personal or Workspace).
- Python 3.10+ with `gslides-mcp` installed (see the README Install section).

---

## Step 1 — Create or select a Google Cloud project

1. Navigate to [https://console.cloud.google.com](https://console.cloud.google.com) and sign in.
2. In the top toolbar, click the project selector and either pick an existing project or click **New Project**. Give the project a name (e.g. `gslides-mcp`) and click **Create**.

---

## Step 2 — Enable the required APIs

You need both the Slides API and the Drive API.

1. In the left navigation, go to **APIs & Services > Library**.
2. Search for **Google Slides API**, click the result, then click **Enable**.
3. Go back to the Library (browser Back button or the breadcrumb).
4. Search for **Google Drive API**, click the result, then click **Enable**.

---

## Step 3 — Configure the OAuth consent screen

Before you can create a client ID you must configure what Google shows users when they consent.

1. In the left navigation, go to **APIs & Services > OAuth consent screen**.
2. Choose **External** for User type (this works for any Google account, including personal). Click **Create**.

   If your account belongs to a Google Workspace organization, **Internal** is also available and limits consent to users in your org — that's fine too, and it skips the "publishing status" step below.

3. Fill in the required fields:
   - **App name**: anything descriptive, e.g. `gslides-mcp`.
   - **User support email**: your email address.
   - **Developer contact information**: your email address.
4. Click **Save and Continue** through the Scopes screen without adding any scopes there (the server requests them programmatically at runtime).
5. On the **Test users** screen, click **Add Users** and enter your own Google account email. This is required while the app is in "testing" mode — only listed test users can complete the OAuth flow.
6. Click **Save and Continue**, then **Back to Dashboard**.

Your app stays in **Testing** mode indefinitely, which is fine for personal or team use. If you ever want to remove the 100-user limit and share the server with others, you can submit for Google verification, but that is not required for a single developer or small team.

---

## Step 4 — Create an OAuth 2.0 Client ID

1. In the left navigation, go to **APIs & Services > Credentials**.
2. Click **Create credentials** at the top, then choose **OAuth client ID**.
3. For **Application type**, select **Desktop app**.
4. Give it a name (e.g. `gslides-mcp desktop`) and click **Create**.
5. A dialog appears with your Client ID and Client Secret. Click **Download JSON** (or the download icon on the credentials list row).

---

## Step 5 — Save the credentials file

Rename the downloaded file to `credentials.json` and copy it to the credentials directory:

```sh
mkdir -p ~/.gslides-mcp/creds
cp ~/Downloads/client_secret_*.json ~/.gslides-mcp/creds/credentials.json
```

The server looks for `credentials.json` at `~/.gslides-mcp/creds/credentials.json` by default.

To use a different directory, set the environment variable before launching the server:

```sh
export GSLIDES_MCP_CRED_DIR=/path/to/your/creds
```

The directory is created automatically on first launch if it does not exist.

---

## Step 6 — First-run browser consent

The next time any MCP tool is called, the server detects that no `token.json` exists and launches the OAuth flow:

1. A message is printed to stderr: `gslides-mcp: opening browser for Google OAuth — follow the prompts then return here.`
2. A browser tab opens to the Google consent page. Sign in with the Google account you added as a test user in Step 3.
3. You will see a warning that the app is unverified — click **Advanced** then **Go to <app name> (unsafe)**. This warning appears for any unverified Desktop app in testing mode and is expected.
4. Grant the requested permissions (Slides and Drive).
5. The browser shows a success page ("The authentication flow has completed"). You can close the tab.

The server saves `token.json` next to `credentials.json` with file permissions `0o600`. Future launches reuse this token and refresh it automatically when it expires.

Required OAuth scopes (for reference):

```
https://www.googleapis.com/auth/presentations
https://www.googleapis.com/auth/drive
```

---

## Troubleshooting

### `redirect_uri_mismatch`

The OAuth flow starts a temporary local HTTP server to receive the callback. This requires that `localhost` be reachable from the machine running the MCP server. If you are running inside a Docker container or a remote machine without port forwarding, the redirect will fail.

Resolution: run the server on the machine where a browser is available, or set up SSH port forwarding so the local callback port is reachable.

### Token expired

Expired access tokens are refreshed automatically using the stored refresh token. You do not need to re-authenticate.

### Revoked refresh token or `invalid_grant` error

Google revokes refresh tokens if:
- Your app's OAuth consent screen is in testing mode and the token is older than 7 days (Google policy for testing-mode apps). Re-authenticate to get a fresh token.
- You revoked access from [https://myaccount.google.com/permissions](https://myaccount.google.com/permissions).
- You changed the allowed scopes in the credentials.

Resolution: delete `token.json` and trigger a new tool call to re-run the OAuth flow.

```sh
rm ~/.gslides-mcp/creds/token.json
```

### 403 errors from the Drive or Slides API

This means the token is valid but the requested operation is not permitted. Common causes:

- **Wrong scopes**: both `presentations` and `drive` scopes are required. If you created the token before adding one of the scopes, delete `token.json` and re-authenticate.
- **Shared Drive permissions**: `copy_slide_cross_deck` and Drive file moves use the `supportsAllDrives=True` flag, but the underlying Drive sharing settings still apply. Ensure the authenticated account has edit access to the target folder.

### `credentials.json` not found

The server prints a setup message and raises a `RuntimeError`. Place `credentials.json` at `~/.gslides-mcp/creds/credentials.json` (or at `$GSLIDES_MCP_CRED_DIR/credentials.json`) and retry.
