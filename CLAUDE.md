# CLAUDE.md — μField

Guidance for Claude Code when working in this repository. Read this fully before making changes.

## What this is

μField is an Android field-data app forked from **Mergin Maps mobile** (GPL-3.0), published on Google Play by Biomitta Oy. Users collect text, numbers, photos and video with location and metadata, work against their own QGIS project, store data in their own storage (local folder, Google Drive, OneDrive), and view open map layers (Ruokavirasto, SYKE, MML, GTK, Luke, Metsäkeskus, FMI).

It is designed **API-first**: every user action is a *tool* defined in `schema/tools.json`. The same tool definitions drive the app UI, the MCP servers (Claude and other MCP clients), and the in-app voice agent, which uses Claude.

## Non-negotiable rules

1. **Tool parity.** Any new user-facing capability must first be added to `schema/tools.json`, then implemented in `core/`, then wired to the UI, MCP server and voice agent. A UI action with no matching tool is a bug. Never implement business logic only in QML. **Exception: secrets.** Entering, viewing or exporting a credential is native-UI only; no tool accepts a secret, and tools refer to stored credentials only by `auth_config_id` (`docs/adr/0002-credentials.md`).
2. **Stay close to upstream.** Put μField code in `ufield/` modules. Change upstream files (`app/`, `core/` from Mergin) only when unavoidable, keep the diff minimal, and mark it with `// UFIELD:` plus a one-line reason. We rebase on upstream regularly.
3. **GPL-3.0.** Keep upstream license headers. All code in this repo is GPL-3.0. Do not add dependencies with incompatible licenses (check before adding; record them in `docs/dependencies.md`).
4. **No Mergin branding.** Use the μField name, icons and package ID `fi.biomitta.ufield`. Don't reintroduce Mergin trademarks in UI strings or assets. The display name is written with the Greek letter mu, `μField` (U+03BC, not the micro sign U+00B5); identifiers, paths, package IDs, STAC prefixes and URLs use ASCII `ufield`.
5. **Capture fidelity.** Never recompress or strip metadata from originals. Every photo/video capture stores: full EXIF, GNSS fix (lat, lon, alt, horizontal/vertical accuracy, fix type incl. RTK status, satellite count), device orientation (azimuth, pitch, roll), timestamp (UTC), and for video a per-frame pose/GNSS track. These feed future ortho, 3DGS and super-resolution products.
6. **Provenance and licence on every asset.** Each asset (capture, imported layer, product) is a STAC item with `ufield:visibility` (`proprietary` | `public`), `license`, and `ufield:provenance` (input asset IDs + recipe). Never merge proprietary and public data into an output without recording both.
7. **Secrets.** No keys, tokens or signing material in the repo. Details: `docs/adr/0002-credentials.md`.
   - Server secrets (MML key, CDSE client, OAuth client secrets) live only in ufield-server's environment, named in the `auth` section of `config/layers.yaml`. Never in the app: anything compiled in (BuildConfig, resources, `local.properties` values) is extractable.
   - CI and signing secrets live in GitHub Actions secrets. `local.properties` (git-ignored) holds build configuration only, never a runtime key.
   - User credentials stay on the device: service credentials in the QGIS auth manager, tokens in the Android Keystore (qtkeychain), never in `QSettings`, `.qgs` files or synced storage.
   - Never put a key in a URL: MML keys go in HTTP Basic auth. Never log request URLs or headers of authenticated requests.
8. **Google Play.** Target API 36. Request the Google Drive `drive.file` scope only — never full `drive`. Background location only if a feature truly needs it, with a written justification in `docs/play-policy.md`.

## Architecture

```
┌── Android app (Qt 6 / QML, Mergin fork) ───────────────────────────────┐
│  UI (QML) ──► ToolDispatcher ◄── Voice agent                           │
│                     │           (cloud STT → Claude)                   │
│                     ▼                                                  │
│  ufield/core: projects, features, notes, media capture, layers, STAC   │
│                     │                                                  │
│  StorageProvider: Local | GoogleDrive | OneDrive | MerginCE            │
└────────────────────────────────────────────────────────────────────────┘
        ▲ same tool schema
┌── ufield-server (headless core) ───────────────────────────────────────┐
│  Remote MCP server (Streamable HTTP, own OAuth, Google sign-in)        │
│  /agent: Claude API proxy for the voice agent (key stays here)         │
│  Authenticated layer proxy · target areas · STAC catalog               │
│  ProductJob queue: Farm Pack (other products: stub in MVP)             │
└────────────────────────────────────────────────────────────────────────┘
        ▲ same tool schema, same project folder
┌── ufield-mcp (local, stdio) on the user's computer ────────────────────┐
│  Claude Desktop / Claude Code ──► project folder (local or Drive sync) │
│  Notes and analysis tools; server tools via the user's session         │
└────────────────────────────────────────────────────────────────────────┘
```

- **ToolDispatcher** validates input against `schema/tools.json`, then calls `ufield/core`. UI, voice and MCP all go through it.
- **StorageProvider** is an interface (`list`, `read`, `write`, `delete`, `changes_since`, `conflict_policy`). MVP: Local and GoogleDrive. OneDrive and MerginCE after.
- **Claude:** three paths, one schema (`docs/adr/0003-claude-notes-and-voice.md`): the in-app voice agent (Claude API through ufield-server `/agent`, tools run on the phone); `ufield-mcp` in local stdio mode for Claude Desktop and Claude Code on a project folder; and the remote MCP server as a Claude custom connector for server-side tools.
- **Notes:** Markdown per point under `notes/<ufield_uuid>/given/` (user) and `ai/` (AI), plus `analyses/` for work across points, layers and time. ToolDispatcher sets the author from the calling client; AI notes are append-only. Analysis tools: `sample_layers`, `compare_features`, `get_time_series`.
- **Voice:** cloud speech-to-text through ufield-server. Voice notes (`add_voice_note`) are recorded offline, audio kept, and transcribed in the background; the note fills in when the transcript arrives. Agent mode (spoken commands to Claude) needs a connection.
- **Credentials:** the app signs in with Google and exchanges the ID token for a ufield-server session; `via_server` endpoints require that session and are rate-limited. The MCP server validates token audience and never passes tokens through. See `docs/adr/0002-credentials.md`.
- **Layers** come from `config/layers.yaml` (type, url, crs, license, attribution, auth). `scripts/check_layers.py` checks every endpoint in CI.
- **Target areas** (`select_target_area`) are what the Farm Pack and products are built for: saved areas made of field parcels (peltolohkotunnus, Ruokavirasto), properties (kiinteistötunnus, MML) or map picks, each classed as field, forest, other green, brownfield or urban green. See `docs/adr/0001-target-areas.md`.
- **Farm Pack** is the one product built in the MVP (`request_farm_pack`): server-side fetch of MML ortho/DEM (WCS, tiled at 2 × 2 km), a CDSE openEO Sentinel-2 season series and clipped open vector layers, delivered as GeoPackage + COGs + STAC. Sources and limits: `docs/layer-sources.md`.
- **Other products** (orthomosaic, 3DGS, super-resolution) are **not implemented in the MVP**. `request_product` validates input, records a `ProductJob` with status `unavailable`, and returns it. Don't build workers until asked.

## Repo layout

```
app/, core/          upstream Mergin Maps code (minimise changes)
ufield/core/         μField domain logic (C++)
ufield/tools/        ToolDispatcher + generated bindings from schema
ufield/storage/      StorageProvider implementations
ufield/voice/        voice notes (recording, upload queue) and voice agent (Claude via server, tool loop)
ufield/qml/          μField UI components
server/              ufield-server and ufield-mcp (local mode): MCP, /agent, transcription, STAC, job queue (Python)
schema/tools.json    single source of truth for tools
config/layers.yaml   map layer registry
scripts/             codegen, layer checks, release helpers
templates/project/   files added to every μField project folder (its CLAUDE.md)
docs/                ADRs (docs/adr/NNNN-title.md), play-policy.md, dependencies.md
.github/workflows/   CI: build, test, layer check, release to Play
```

## Build and test

- Android build follows upstream instructions (see upstream `INSTALL.md` / build docs). Prefer CI builds; local builds need the Qt 6 Android kit, NDK and vcpkg as upstream specifies. Verify commands against upstream docs before running — do not guess.
- After editing `schema/tools.json` or `config/layers.yaml`: run `scripts/format_schema`, then `scripts/validate_schema` (CI runs it too; `pip install -r scripts/requirements.txt`). Once it exists, run `scripts/codegen_tools` to regenerate C++ bindings and server stubs.
- Tool input schemas never use top-level `oneOf`/`anyOf`/`allOf`/`if` (LLM tool APIs reject them). Put cross-field constraints in the tool's `x-ufield-rules` (`exactly_one_of`, `at_least_one_of`, `at_most_one_of`, `required_if`, see `scripts/ufield_schema.py`); ToolDispatcher enforces them and exported schemas drop them.
- Features are addressed by `feature_uuid` (the `ufield_uuid` field), never by QGIS fid.
- Server: `cd server && uv sync && uv run pytest`.
- MCP smoke test: run the server locally and exercise tools with the MCP Inspector.
- Every tool needs: a schema test (valid + invalid input, in `schema/tests/cases.json`), a core unit test, and an MCP round-trip test.

## Working style

- One feature per branch and PR. Small, reviewable commits with conventional messages (`feat:`, `fix:`, `chore:`, `docs:`).
- For design choices with lasting impact, write a short ADR in `docs/adr/` before coding.
- UI strings go through Qt translations. Finnish and English are both required; Finnish is the default for the Finnish store listing.
- CRS: store in EPSG:4326 for interchange; display and measurements default to EPSG:3067 (ETRS-TM35FIN).
- When unsure about upstream behaviour, read the upstream code rather than assuming.

## MVP scope

In: fork + rebrand, CI build, Google sign-in, Local + Google Drive storage, observations (text, number, photo, video) with full capture metadata, open QGIS project, layer registry with open layers, target areas (peltolohkotunnus, kiinteistötunnus, map pick), Farm Pack, STAC catalog, tool schema, MCP server (remote and local, usable from Claude), point notes (given / AI Markdown) and analysis tools, voice notes (Finnish + English) with background cloud speech-to-text, voice agent, signed AAB release to Play internal track.

Out (interfaces only): product generation (ortho, 3DGS, super-resolution), OneDrive, MerginCE sync, multi-user collaboration.

Phases, exit checks and release steps for GitHub and Google Play: `docs/roadmap.md`.
