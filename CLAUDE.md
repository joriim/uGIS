# CLAUDE.md — μField

Guidance for Claude Code when working in this repository. Read this fully before making changes.

## What this is

μField is an Android field-data app forked from **Mergin Maps mobile** (GPL-3.0), published on Google Play by Biomitta Oy. Users collect text, numbers, photos and video with location and metadata, work against their own QGIS project, store data in their own storage (local folder, Google Drive, OneDrive), and view open map layers (Ruokavirasto, SYKE, MML, GTK, Luke, Peltoraportti).

It is designed **API-first**: every user action is a *tool* defined in `schema/tools.json`. The same tool definitions drive the app UI, the MCP server (LLM clients), and the in-app voice agent.

## Non-negotiable rules

1. **Tool parity.** Any new user-facing capability must first be added to `schema/tools.json`, then implemented in `core/`, then wired to the UI, MCP server and voice agent. A UI action with no matching tool is a bug. Never implement business logic only in QML.
2. **Stay close to upstream.** Put μField code in `ufield/` modules. Change upstream files (`app/`, `core/` from Mergin) only when unavoidable, keep the diff minimal, and mark it with `// UFIELD:` plus a one-line reason. We rebase on upstream regularly.
3. **GPL-3.0.** Keep upstream license headers. All code in this repo is GPL-3.0. Do not add dependencies with incompatible licenses (check before adding; record them in `docs/dependencies.md`).
4. **No Mergin branding.** Use the μField name, icons and package ID `fi.biomitta.ufield`. Don't reintroduce Mergin trademarks in UI strings or assets. The display name is written with the Greek letter mu, `μField` (U+03BC, not the micro sign U+00B5); identifiers, paths, package IDs, STAC prefixes and URLs use ASCII `ufield`.
5. **Capture fidelity.** Never recompress or strip metadata from originals. Every photo/video capture stores: full EXIF, GNSS fix (lat, lon, alt, horizontal/vertical accuracy, fix type incl. RTK status, satellite count), device orientation (azimuth, pitch, roll), timestamp (UTC), and for video a per-frame pose/GNSS track. These feed future ortho, 3DGS and super-resolution products.
6. **Provenance and licence on every asset.** Each asset (capture, imported layer, product) is a STAC item with `ufield:visibility` (`proprietary` | `public`), `license`, and `ufield:provenance` (input asset IDs + recipe). Never merge proprietary and public data into an output without recording both.
7. **Secrets.** No keys, tokens or signing material in the repo. Use GitHub Actions secrets and `local.properties` (git-ignored).
8. **Google Play.** Target API 36. Request the Google Drive `drive.file` scope only — never full `drive`. Background location only if a feature truly needs it, with a written justification in `docs/play-policy.md`.

## Architecture

```
┌────────────── Android app (Qt 6 / QML, Mergin fork) ──────────────┐
│  UI (QML) ──► ToolDispatcher ◄── Voice agent (STT → LLM → tools) │
│                    │                                              │
│                    ▼                                              │
│  ufield/core: projects, features, media capture, layers, STAC    │
│                    │                                              │
│  StorageProvider: Local | GoogleDrive | OneDrive | MerginCE      │
└───────────────────────────────────────────────────────────────────┘
        ▲ same tool schema
┌───────┴─────── ufield-server (headless core) ─────────────────────┐
│  MCP server (Streamable HTTP, Google OAuth)                       │
│  STAC catalog · ProductJob queue (stub in MVP)                    │
└───────────────────────────────────────────────────────────────────┘
```

- **ToolDispatcher** validates input against `schema/tools.json`, then calls `ufield/core`. UI, voice and MCP all go through it.
- **StorageProvider** is an interface (`list`, `read`, `write`, `delete`, `changes_since`, `conflict_policy`). MVP: Local and GoogleDrive. OneDrive and MerginCE after.
- **Layers** come from `config/layers.yaml` (type, url, crs, license, attribution, auth). `scripts/check_layers.py` checks every endpoint in CI.
- **Farm Pack** is the one product built in the MVP (`request_farm_pack`): server-side fetch of MML ortho/DEM (WCS, tiled at 2 × 2 km), a CDSE openEO Sentinel-2 season series and clipped open vector layers, delivered as GeoPackage + COGs + STAC. Sources and limits: `docs/layer-sources.md`.
- **Other products** (orthomosaic, 3DGS, super-resolution) are **not implemented in the MVP**. `request_product` validates input, records a `ProductJob` with status `unavailable`, and returns it. Don't build workers until asked.

## Repo layout

```
app/, core/          upstream Mergin Maps code (minimise changes)
ufield/core/         μField domain logic (C++)
ufield/tools/        ToolDispatcher + generated bindings from schema
ufield/storage/      StorageProvider implementations
ufield/voice/        voice agent (STT, LLM client, tool loop)
ufield/qml/          μField UI components
server/              ufield-server: MCP server, STAC, job queue (Python)
schema/tools.json    single source of truth for tools
config/layers.yaml   map layer registry
scripts/             codegen, layer checks, release helpers
docs/                ADRs (docs/adr/NNNN-title.md), play-policy.md, dependencies.md
.github/workflows/   CI: build, test, layer check, release to Play
```

## Build and test

- Android build follows upstream instructions (see upstream `INSTALL.md` / build docs). Prefer CI builds; local builds need the Qt 6 Android kit, NDK and vcpkg as upstream specifies. Verify commands against upstream docs before running — do not guess.
- After editing `schema/tools.json`, run `scripts/codegen_tools` to regenerate C++ bindings and server stubs, then `scripts/validate_schema`.
- Server: `cd server && uv sync && uv run pytest`.
- MCP smoke test: run the server locally and exercise tools with the MCP Inspector.
- Every tool needs: a schema test (valid + invalid input), a core unit test, and an MCP round-trip test.

## Working style

- One feature per branch and PR. Small, reviewable commits with conventional messages (`feat:`, `fix:`, `chore:`, `docs:`).
- For design choices with lasting impact, write a short ADR in `docs/adr/` before coding.
- UI strings go through Qt translations. Finnish and English are both required; Finnish is the default for the Finnish store listing.
- CRS: store in EPSG:4326 for interchange; display and measurements default to EPSG:3067 (ETRS-TM35FIN).
- When unsure about upstream behaviour, read the upstream code rather than assuming.

## MVP scope

In: fork + rebrand, CI build, Google sign-in, Local + Google Drive storage, observations (text, number, photo, video) with full capture metadata, open QGIS project, layer registry with open layers, Farm Pack, STAC catalog, tool schema, MCP server, voice input (Finnish + English), signed AAB release to Play internal track.

Out (interfaces only): product generation (ortho, 3DGS, super-resolution), OneDrive, MerginCE sync, multi-user collaboration.
