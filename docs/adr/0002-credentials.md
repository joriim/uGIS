# 0002 — How credentials are entered, stored and used

Status: proposed, 2026-09-25

## Context

μField talks to services that need credentials: MML (API key), CDSE (OAuth), Google (sign-in, Drive), OneDrive later, and any private map service a user adds. The first drafts only said where secrets must not go. They did not say how a credential enters the system, where it is stored, or how it is attached to a request, and two choices in them leaked keys: `local.properties` (compiled into the APK) and the MML key as an `api-key=` URL parameter.

Two paths make leaks easy in this app: every user action is also an LLM-callable tool (rule 1), so anything typed into a tool input ends up in model context and provider transcripts; and projects are synced to user storage, so anything in a `.qgs` file is copied to Google Drive.

## Decision

### 1. Where each secret lives

| Secret | Owner | Stored in | Never in |
|---|---|---|---|
| MML API key (Biomitta) | server | server environment / secret manager | app, repo, URLs, logs, STAC |
| CDSE OAuth client (Biomitta) | server | server environment / secret manager | app, repo, logs |
| Google OAuth client secret for the MCP server | server | server environment / secret manager | app, repo |
| Anthropic API key for the voice agent (`UFIELD_ANTHROPIC_API_KEY`) | server | server environment / secret manager | app, repo, logs |
| Play upload key, keystore passwords | CI | GitHub Actions secrets | repo, `local.properties` |
| User's own service credentials (private WMS, own MML key) | user | on device, QGIS auth manager (encrypted auth DB) | `.qgs` files, tool inputs, synced storage, server |
| User's Google Drive / OneDrive tokens | user | on device, Android Keystore (via qtkeychain) | `QSettings`, logs, server |
| User's session with ufield-server | user | on device, Android Keystore | `QSettings`, logs |

`local.properties` holds only build configuration (SDK paths, signing *file paths* in local builds). Nothing read at runtime comes from it, because values read into BuildConfig or resources are compiled into the APK and are extractable.

### 2. Server secrets are named in the registry and loaded at startup

`config/layers.yaml` has an `auth` section that maps each `auth` id to an environment variable and to how it is applied to requests. `ufield-server` reads all of them at startup and refuses to start if one that an enabled layer uses is missing. Secrets are never written back to disk, to logs or to responses.

### 3. MML key: HTTP Basic only

The MML key is sent only as the HTTP Basic user name with an empty password, never as `?api-key=`. Query strings end up in access logs, cache keys, error messages and STAC asset hrefs.

- Proxied WMTS/WMS capabilities are rewritten so every resource URL points at `ufield-server`, with no key.
- STAC asset hrefs point at `ufield-server` or at the packaged file, never at a keyed upstream URL.
- Cache keys are built from the upstream URL without credentials.

### 4. The server proxy is not an open proxy

Every `via_server` endpoint requires a signed-in user session and is rate-limited per user and globally, so Biomitta's MML key and CDSE quota cannot be used anonymously through ufield-server and MML's small-scale-use terms are respected.

### 5. Credentials are entered only in native UI, never through tools

This is an explicit exception to rule 1 (tool parity):

- Entering, viewing or exporting a secret happens only in a native settings screen. There is no tool that accepts a secret, and the voice agent never reads a credential aloud or repeats one it heard.
- The screen stores the credential with the QGIS auth manager (the same mechanism QGIS desktop uses) and returns an `auth_config_id`. A layer references its credential by that id, so the `.qgs` file carries the id, not the secret.
- Tools may only refer to stored credentials: `list_credentials` (metadata only: id, name, method, host) and `delete_credential` (confirmed). `add_layer` takes `auth_config_id`.
- `ToolDispatcher` rejects any URL input with embedded credentials: userinfo (`https://user:pass@host`) or query parameters such as `api-key`, `apikey`, `key`, `token`, `access_token`, `password` or `sig`. The schema carries a first-pass check; the dispatcher does the complete, case-insensitive check. The error tells the user to add the credential in settings instead.

### 6. How the app and MCP clients sign in to ufield-server

- The app signs the user in with Google on the device, and sends the Google ID token to ufield-server once. The server verifies signature, issuer, expiry and that the audience is μField's client id, then issues its own short-lived access token and a refresh token. The app stores both in the Android Keystore.
- The MCP server is an OAuth resource server (MCP authorization spec). ufield-server runs its own authorization server with Google as the identity provider, because MCP clients such as Claude's connectors need client registration that Google does not offer (ADR 0003 §1). It validates that each token was issued for it (audience), and never passes a client's token on to another service.
- The server never receives the user's Google Drive or OneDrive tokens; storage sync runs on the device.

### 7. CDSE

The MVP uses Biomitta's own CDSE account with the OAuth client-credentials flow, loaded from the server environment as in §2 (confirm that CDSE's openEO back-end accepts client credentials for this account type; if it does not, use a stored refresh token for that account, loaded the same way). Letting users connect their own CDSE account is deferred: it needs a per-user OAuth flow, encrypted per-user refresh tokens on the server and a disconnect action, and gets its own ADR.

### 8. CI

`scripts/check_layers.py` reads the MML key from a GitHub Actions secret. GitHub masks only the exact secret string, so encoded forms (URL-encoded, base64 inside a Basic auth header) are printed in clear. The script therefore masks the key itself and never logs request URLs or headers of authenticated requests.

## Consequences

- Credential entry needs one native settings screen that no tool covers. That is deliberate; reviewers should not flag it as a parity bug.
- Mergin upstream stores some settings in `QSettings`; token storage moves to qtkeychain (BSD-3-Clause, GPL-compatible; record in `docs/dependencies.md`), with the smallest possible `// UFIELD:` change upstream.
- Private layers added with an `auth_config_id` do not work on another device until the user enters the credential there too. The layer shows as "credential missing" instead of failing silently.

## Open questions

- Which secret manager hosts ufield-server's secrets in production (depends on the hosting choice).
- Whether CDSE's openEO back-end accepts client credentials for Biomitta's account (see §7).
