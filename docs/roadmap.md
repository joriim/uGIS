# Roadmap to GitHub and Google Play — μField

Status: draft, 2026-09-25. Scope follows the MVP in `CLAUDE.md`. Store rules and dates change often; every item marked *(verify)* must be checked against the current Play Console and Google documentation when that phase starts.

Today the repository holds only design documents: `CLAUDE.md`, the layer registry, the tool schema and two ADRs. There is no app or server code yet.

## Principles

- **Ship a thin vertical slice early.** The first build on the Play internal track should be the rebranded fork with nothing new. It proves the build, signing, 16 KB alignment and upload pipeline before any feature depends on them.
- **Public from the first code.** The app is GPL-3.0; every build given to testers is a distribution and owes them the source. Making the repository public when the fork lands is simpler than tracking that per build.
- **Tool first.** Every feature follows rule 1: schema → core → UI → MCP → voice, with the three required tests.
- **Each phase ends with an exit check.** A phase is done when its checks pass, not when its tasks are ticked.

## Phase overview

| # | Phase | Main output | Rough size* |
|---|---|---|---|
| 0 | Decisions and accounts | Name cleared, accounts open, schema must-fixes done | 2–3 weeks, mostly waiting |
| 1 | Fork, rebrand, build pipeline | Rebranded app on Play internal track from CI; repo public | 3–5 weeks |
| 2 | Tool layer and local app | ToolDispatcher, codegen, observations with full capture metadata, open layers | 5–8 weeks |
| 3 | ufield-server | Auth, proxy, credentials, MCP, STAC, target areas | 4–6 weeks, parallel with 2 |
| 4 | Google Drive storage | StorageProvider for Drive with `drive.file` | 3–4 weeks |
| 5 | Farm Pack | `request_farm_pack` end to end | 5–7 weeks |
| 6 | Voice, Claude and notes | Voice notes with background cloud STT; Claude via voice agent and MCP; given/AI notes and analysis tools | 5–7 weeks |
| 7 | Compliance and hardening | Privacy, data safety, account deletion, security review, translations | 3–4 weeks, starts during 5 |
| 8 | Release | Closed testing → production; tagged GitHub release | 3–6 weeks incl. review |

\* For one or two developers who know Qt/QGIS. A rough guide for ordering, not a commitment. Phases 2 and 3 run in parallel; 7 starts before 5 and 6 finish.

---

## Phase 0 — Decisions and accounts

Several of these have lead times of days to weeks, so start them first.

**Name and identity**
- [ ] Trademark and name search for "μField" / "uField": PRH (Finnish Patent and Registration Office), EUIPO, and Google Play search. Fix the name before anything public carries it: the package id `fi.biomitta.ufield` can never change after the first Play upload.
- [ ] Decide the GitHub repository name (`joriim/uGIS` today; `ufield` would match the product) and whether it lives under a Biomitta organisation. Rename before going public; GitHub redirects the old URL, but links in store listings should use the final one.
- [ ] Register `ufield.biomitta.fi` (schema `$id`, privacy policy, account deletion page, OAuth consent domain).

**Accounts** (organisation, in Biomitta Oy's name)
- [ ] Google Play Console **organisation** account. Needs a D-U-N-S number for Biomitta Oy (can take weeks) and developer verification. Organisation accounts are not subject to the 12-tester/14-day closed test that new personal accounts need *(verify)*.
- [ ] Google Cloud project: OAuth consent screen (brand verification: name, logo, verified domain, privacy policy), Android and web OAuth clients. `drive.file` is a non-sensitive scope, so no security assessment should be needed *(verify)*.
- [ ] MML open-data API key for the server; read MML's terms for the open service vs a contract (small-scale use, ADR 0002 §4).
- [ ] CDSE account for the server; confirm openEO client-credentials login (ADR 0002 §7) and whether serving app users from one account fits CDSE's terms.
- [ ] Anthropic (Claude) as the model provider: API account, commercial terms and DPA; check data retention and processing location options.
- [ ] Cloud speech-to-text provider: record 30–50 real field notes in Finnish (some in English), run them through candidate batch APIs, compare word error rate on field vocabulary and cost; then sign a DPA and confirm EU processing, no training on customer audio and deletion on request.
- [ ] Server hosting in the EU (GDPR) and its secret manager.

**Design fixes from the first review** (all in `schema/tools.json` and `config/layers.yaml`)
- [x] One Farm Pack contents vocabulary shared by both files (`ortho_cir`, `water`, `nature`); checked by `scripts/validate_schema`.
- [x] Export inlines `$defs` (`scripts/ufield_schema.py`); every exported tool schema is checked to stand alone. Codegen itself comes in phase 2.
- [x] Replace top-level `oneOf` with dispatcher checks (`x-ufield-rules`), for `add_layer`, `request_farm_pack` and the other tools with either/or inputs.
- [x] Use `position`/`orientation` in `add_observation` and `attach_media`.
- [x] Stable feature ids in the schema: feature tools use `feature_uuid` (ADR 0003 §2); `asset_id` allows STAC ids with `.` and `:`. (Adding `ufield_uuid` to layers is app work, phase 2.)
- [x] Align `add_layer.service_type` with registry types.
- [ ] Fill registry TODOs: layer/collection names, `id_attribute`s, licences marked "confirm" (needs access to the services' capabilities documents).
- [x] Remove Peltoraportti from `CLAUDE.md` until confirmed.

**Exit check:** name cleared; Play organisation account and Google Cloud project exist; schema must-fixes merged.

## Phase 1 — Fork, rebrand, build pipeline

**Repository**
- [ ] Bring upstream in with history: add `MerginMaps/mobile` as the `upstream` remote and merge its default branch into `main`, keeping these documents on top. Record the upstream commit in `docs/upstream.md`, with how to rebase.
- [ ] Before going public: run secret scanning over the whole history, enable GitHub secret scanning and push protection.
- [ ] Add `LICENSE` (GPL-3.0, kept from upstream), `README.md` (what μField is, how it relates to Mergin Maps, build steps), `CONTRIBUTING.md`, `SECURITY.md` (how to report vulnerabilities), `docs/dependencies.md`.
- [ ] Branch protection on `main`: PRs only, required CI checks.
- [ ] Make the repository public.

**Rebrand** (rule 2 and 4: minimal, marked `// UFIELD:` changes)
- [ ] Package id `fi.biomitta.ufield`, app name, icons, splash, About screen with GPL notice, upstream credit and source link.
- [ ] Remove Mergin trademarks from UI strings and assets; turn off Mergin cloud sign-in and sync by default (MerginCE comes later).
- [ ] Finnish and English translations of every changed string.

**Build and release pipeline**
- [ ] GitHub Actions: Android build with Qt 6, NDK and vcpkg as upstream does; cache vcpkg. Build AAB for arm64-v8a and armeabi-v7a (x86_64 for emulator tests).
- [ ] Target API level as required by Play at release time (API 36 in `CLAUDE.md`) *(verify)*.
- [ ] **16 KB page size:** Play requires native libraries aligned for 16 KB pages for apps targeting Android 15+ *(verify)*. Every native library (Qt, QGIS, GDAL, PROJ, vcpkg ports) must pass the alignment check in CI; fail the build otherwise.
- [ ] Play App Signing enrolled; upload key and passwords in GitHub Actions secrets (ADR 0002).
- [ ] CI uploads tagged builds to the Play internal track (Play Developer API with a service account, also in secrets).
- [ ] Check AAB download size against Play limits; QGIS-based apps are large.

**Exit check:** a tag on `main` produces a signed AAB in CI that installs from the internal track, runs, opens a QGIS project and shows no Mergin branding; repository is public.

## Phase 2 — Tool layer and local app

- [ ] `scripts/codegen_tools`: C++ bindings and server stubs from `schema/tools.json`; `scripts/validate_schema`; both run in CI.
- [ ] `ToolDispatcher` in `ufield/tools/`: schema validation, the checks moved out of the schema (exactly-one-of, credential-free URLs, confirmations).
- [ ] Test harness for the three tests every tool needs (schema, core unit, MCP round trip).
- [ ] Local StorageProvider; `list_projects`, `open_project`.
- [ ] `get_location` with fix type, accuracy, satellites, RTK status where the receiver reports it.
- [ ] `add_observation`, `update_feature`, `delete_feature`, `query_features`.
- [ ] `attach_media` with full capture metadata (rule 5): EXIF kept, GNSS fix, orientation, UTC time; video pose track. Existing files through the **Android photo picker**, so the app does not need broad media permissions (Play photo and video permissions policy) *(verify)*.
- [ ] Layer registry in the app: `list_layers`, `add_layer` for `auth: none` layers; attribution shown on the map.
- [ ] Credentials settings screen and `list_credentials` / `delete_credential` (ADR 0002 §5).
- [ ] `scripts/check_layers.py` running weekly in CI.

**Exit check:** a user can open a project, record observations with photos and video in the field, and see open layers, all through tools, with tests passing in CI.

## Phase 3 — ufield-server (parallel with phase 2)

- [x] Python project in `server/` (`uv`, `pytest`) with `ToolDispatcher` (schema, `x-ufield-rules`, credential-free URLs); tests in CI.
- [ ] Container image, deploy to the chosen EU host from CI.
- [ ] Sign-in: Google ID token → server session (ADR 0002 §6); per-user and global rate limits.
- [ ] Secrets loaded from the environment per the registry's `auth` section; startup fails if missing.
- [ ] Authenticated proxy for `via_server` layers: MML via HTTP Basic, capabilities rewritten, cache without keys.
- [ ] MCP server (Streamable HTTP, OAuth resource server) generated from the same schema, with ufield-server's own OAuth authorization server (Google as identity provider) so it works as a Claude custom connector.
- [ ] `/agent` endpoint: Claude API proxy for the voice agent; key from the environment; per-user cost and rate limits.
- [ ] STAC catalog with `ufield:visibility` and `ufield:provenance`.
- [ ] Target areas: `select_target_area`, `list_target_areas`, `delete_target_area` (ADR 0001).
- [ ] `ProductJob` store; `request_product` returns `unavailable`; `get_job_status`.
- [ ] Account deletion endpoint that removes the user's server data (needed for Play, phase 7).
- [ ] Logging that never records keys, tokens or authenticated request URLs; structured logs, error reporting without personal data.

**Exit check:** the app uses MML basemaps through the server; an MCP client (MCP Inspector) can sign in and run every tool; nothing works without a session.

## Phase 4 — Google Drive storage

- [ ] Google sign-in and authorisation on Android with `drive.file` only (rule 8). Tokens in the Android Keystore via qtkeychain.
- [ ] Picker flow so users can open existing QGIS projects: `drive.file` only sees files the app created or the user picked.
- [ ] `sync_project`: `changes_since`, conflict policy, resumable uploads for video, offline queue.
- [ ] Media originals uploaded unmodified (rule 5).

**Exit check:** a project edited offline on one phone syncs through Drive to QGIS desktop and back with no data or metadata loss.

## Phase 5 — Farm Pack

- [ ] Server fetchers: MML WCS ortho (2 × 2 km tiling, mosaic to COG) and DEM with hillshade and slope; clipped vector layers.
- [ ] openEO recipe `farm_pack_s2_season` (true colour + NDVI per cloud-free date); quota tracking and a clear error when the monthly quota is used up.
- [ ] Packaging: `farm.gpkg`, COGs, `catalog.json`, `overview.pdf`; licence and attribution on every item.
- [ ] Size budget measured on real farms; decide whether rasters go in both the GeoPackage and COGs.
- [ ] Maximum AOI area enforced in the dispatcher.
- [ ] Job notification to the phone, download and open in the app.

**Exit check:** Farm Packs for three real target areas (a farm, a forest property, an urban green area) open on the phone offline and in QGIS, within the size budget, with correct attribution.

## Phase 6 — Voice, Claude and notes

See `docs/adr/0003-claude-notes-and-voice.md`. Given notes (typed) can ship in phase 2; everything below builds on them.

**Notes and analysis**
- [ ] Project folder layout with `notes/<ufield_uuid>/given|ai/` and `analyses/`; `templates/project/CLAUDE.md` copied into every project.
- [x] `read_notes`, `write_note` (author set by `ToolDispatcher`, AI append-only), notes as STAC items: `server/src/ufield/project.py`.
- [ ] `sample_layers`, `compare_features`, `get_time_series` (NDVI and weather via ufield-server).
- [ ] App notes view: given and AI tabs per point, project analyses, analysis results (rule 1).

**Claude**
- [x] `ufield-mcp` local stdio mode with `read_notes` / `write_note`; setup for Claude Desktop and Claude Code in `server/README.md`. Analysis tools still to add.
- [ ] Remote MCP tested as a Claude custom connector (sign-in, tool calls, annotations).
- [ ] Prompt-injection tests: instructions hidden in given notes and layer attributes must not change what Claude does without the user.

**Voice**
- [ ] `add_voice_note`: record offline, keep original audio, write a pending given note.
- [ ] Upload queue on the phone (survives restarts, Wi-Fi-only option) and server transcription jobs on the provider's batch API; transcript written into the note; failed jobs retryable.
- [ ] Server deletes audio and transcript after the app confirms receipt; provider retention off where possible.
- [ ] Pending notes playable in the app; queue status visible.
- [ ] Agent mode: spoken command → cloud STT (synchronous) → Claude tool loop via `/agent` → `ToolDispatcher`; same confirmations as other clients (`delete_*` asks the user).
- [ ] `set_voice_settings` (language, `notes_only` / `agent`, Wi-Fi-only upload).
- [ ] Microphone permission requested only when voice is first used; clear indicator while listening.
- [ ] No secrets or credentials ever in the voice path (ADR 0002 §5).
- [ ] Cost and latency limits per user; graceful offline behaviour.
- [ ] Review Play's policy on AI-generated content for what applies to a tool-driving assistant (e.g. user reporting) *(verify)*.

**Exit check:** common field tasks ("add an observation here, soil pH 5.8, take a photo") work by voice in both languages; a voice note recorded offline is transcribed into its note after the phone reconnects; Claude Desktop, working on a synced project folder, can answer "how do the soil samples compare with the soil map and with last year?" and write the answer as an AI note that shows up in the app.

## Phase 7 — Compliance and hardening

**Privacy and Play policy**
- [ ] Privacy policy (Finnish and English) at a stable URL on `ufield.biomitta.fi`: what is collected, why, processors (hosting, STT, LLM, Google), retention, rights under GDPR.
- [ ] Data processing records and DPAs with every processor.
- [ ] **Account deletion** inside the app and on a web page, as Play requires for apps with accounts *(verify)*.
- [ ] Play **Data safety** form: location, photos and videos, audio, account info, files; what is shared with processors; encryption in transit; deletion. Declare Anthropic (agent mode: transcripts and tool results) and the cloud STT provider (all voice-note audio, deleted after transcription).
- [ ] Permissions review: foreground location only (rule 8; if background is ever needed, justify it in `docs/play-policy.md` and prepare the declaration video); camera; microphone; no broad storage or media permissions.
- [ ] Content rating questionnaire, target audience (not directed at children), ads declaration (none).
- [ ] `docs/play-policy.md` completed with every declaration and its reasoning.

**Licences**
- [ ] Dependency licence audit into `docs/dependencies.md` (Qt, QGIS, GDAL, PROJ, qtkeychain, Python packages); confirm GPL-3.0 compatibility.
- [ ] Open-source notices screen in the app; source link to the exact tag of each release.
- [ ] Data licence and attribution checks for every registry layer (TODOs in `layers.yaml`).

**Quality and security**
- [ ] Security review of server auth, proxy and credential handling; dependency scanning (Dependabot) and CodeQL for Python.
- [ ] Crash and ANR reporting without personal data; fix the top issues from internal testing.
- [ ] Accessibility pass (TalkBack labels, contrast, touch target sizes).
- [ ] Complete Finnish and English translations; Finnish as default store language.
- [ ] Field test on at least three devices, including a low-end one and one with an external GNSS/RTK receiver.

**Exit check:** Play pre-launch report clean; every policy declaration drafted and reviewed; no open security findings above low.

## Phase 8 — Release

**Google Play**
- [ ] Store listing in Finnish and English: short and long description, screenshots (phone, tablet), feature graphic, icon, category, contact email, privacy policy URL. Include "ufield" and "mufield" as search terms, since "μ" is hard to type.
- [ ] Closed testing track with real farmers and at least one forest and one urban green user; collect feedback for two or more weeks.
- [ ] Staged rollout to production (e.g. 10 % → 50 % → 100 %), watching crashes, ANRs and server load; server quotas (MML, CDSE, LLM) sized for the rollout.
- [ ] Plan for review time: the first production review and any policy-sensitive declaration can take days *(verify)*.

**GitHub**
- [ ] Tag `v1.0.0`; GitHub Release with changelog, link to the Play listing, and the exact source (GPL). Optionally attach a universal APK for users outside Play.
- [ ] `CHANGELOG.md` and semantic versioning; `versionCode` derived from the tag in CI.
- [ ] Issue templates (bug, feature, layer source request), labels, and a public roadmap (this file or GitHub Projects).

**Exit check:** v1.0.0 live in Play production in Finland; matching tagged source on GitHub.

## After 1.0

- Upstream rebases on a fixed cadence (e.g. each upstream release), with CI proving the fork still builds.
- OneDrive and MerginCE storage; users connecting their own CDSE account (new ADR).
- Planet Agriculture as the first paid imagery (licence terms first, `layer-sources.md` §3).
- Product workers (orthomosaic, 3DGS, super-resolution) behind the existing `request_product` interface.

## Main risks

| Risk | Impact | Mitigation |
|---|---|---|
| Upstream Android build (Qt, QGIS, vcpkg, NDK) is slow and brittle | Phase 1 slips, blocks everything | Start with upstream's CI unchanged; cache vcpkg; change one thing at a time |
| Native libraries not 16 KB aligned | Play rejects the upload | Alignment check in CI from phase 1 |
| D-U-N-S / Play account verification delays | No internal track | Apply in week 1 |
| MML open-service limits or CDSE free-tier terms don't fit a public app | Farm Pack blocked or throttled | Ask MML and CDSE early; budget for contract access; server caching |
| Play policy findings (permissions, data safety, AI features) | Release delayed | Draft declarations in phase 7, not at submission; foreground-only location; photo picker |
| Name conflict found late | Rebrand after launch; package id fixed forever | Trademark search in phase 0 before first upload |
| LLM / STT cost per active user | Unsustainable voice feature | Per-user limits; batch STT pricing; notes-only mode needs no LLM; measure in closed testing |
| Cloud STT not accurate enough in Finnish field vocabulary | Poor voice notes | Test providers on real recordings in phase 0; audio always kept, so notes can be re-transcribed with a better model |
