# 0003 — Claude over MCP, point notes as Markdown, cloud speech-to-text for voice notes

Status: proposed, 2026-09-25

## Context

Users should be able to keep working with their μField data in Claude: read what was recorded at each point, analyse points against map layers, against each other and over time, and write the results back where the user and later sessions can find them. Voice notes are recorded in the field, often without a connection, and do not need to be transcribed in real time.

Constraints from earlier ADRs: user project data lives in the user's own storage and ufield-server never gets their Drive tokens (ADR 0002 §6); secrets never reach the app or tool inputs (ADR 0002 §5); every asset records provenance and licence (rule 6).

## Decision

### 1. Claude is the model, reached three ways

| Where Claude runs | How it reaches μField | Data it sees | Use |
|---|---|---|---|
| **In-app voice agent** | App → ufield-server `/agent` → Claude API; tools execute on the phone through `ToolDispatcher` | Transcript, tool results | Hands-free field work |
| **Claude Desktop / Claude Code, local** | `ufield-mcp` (stdio) running on the user's computer against a project folder (local, or synced by Google Drive for desktop) | The whole project folder the user points it at | Analysis and writing notes: the main path for "keep working with the data" |
| **Claude.ai / Claude Desktop, remote connector** | Remote MCP on ufield-server (Streamable HTTP) | Server-side data only: registry layers, target areas, Farm Pack jobs, catalog | Farm Packs and layer questions without a local folder |

- `ufield-mcp` is the same Python package as ufield-server, run in local mode: it loads the tool schema, runs project tools directly on the folder (GeoPackage, notes, media), and calls ufield-server with the user's session only for server tools (`via_server` layers, Farm Pack, satellite and weather series). No project data is uploaded.
- The voice agent's Claude API key lives only on ufield-server (`UFIELD_ANTHROPIC_API_KEY`, ADR 0002 §1). `/agent` requires a user session and has per-user cost and rate limits.
- Model and effort are server configuration, not app code. Default `claude-opus-5`; voice uses lower effort for latency, analysis higher. Implementation notes for `/agent`: stream responses; `strict: true` on tools; tool choice `auto` (never forced); check `stop_reason` before reading content and handle `refusal` (server-side fallbacks enabled); cache the system prompt and tool list; send all parallel tool results in one message.
- **Remote connector sign-in:** Claude's custom connectors use the MCP authorization flow, which needs dynamic client registration or client metadata documents. Google does not offer these *(verify)*, so ufield-server runs its own OAuth authorization server with Google as the identity provider. This refines ADR 0002 §6.
- MCP tool annotations: read tools `readOnlyHint`; `delete_*` `destructiveHint`; `write_note` is additive, not destructive.

### 2. Notes are Markdown files in the project folder, split into given and AI

```
<project>/
  CLAUDE.md                     how this folder is organised (from templates/project/CLAUDE.md)
  <project>.qgz
  data.gpkg                     features; every layer has a ufield_uuid field
  media/                        originals (rule 5)
  notes/
    <feature_uuid>/
      given/<id>_<slug>.md      user: typed notes, verbatim transcripts
      ai/<id>_<slug>.md         AI: analysis of this point
    _project/given/<id>_<slug>.md  user: notes on several points or the whole project
  analyses/<id>_<slug>.md       AI: across points, against layers, over time
  catalog.json                  STAC catalog, linking catalog/items/<id>.json (one item per note)
```

- **Stable ids.** Notes are keyed by `ufield_uuid`, not the QGIS fid, so they survive sync and edits. Every μField layer gets this field; existing feature tools move to it (roadmap phase 0).
- **Author is decided by ToolDispatcher, not the caller.** The UI and verbatim speech-to-text write `given/`. Any model (MCP clients, the voice agent's replies and summaries) writes `ai/` or `analyses/`. There is no input field for the author.
- **Append-only for AI.** `write_note` always creates a new file. No tool edits or deletes an existing note; users edit and delete their own notes in the app. A correction is a new note that names the old one in `sources.notes`.
- **Front matter** carries provenance (rule 6):

  ```yaml
  ---
  id: 2026-09-25T101500Z-3f2a
  features: [9b1c2d3e-4f50-4a6b-8c7d-0e1f2a3b4c5d]
  author: ai                    # given | ai
  kind: analysis                # observation | analysis | summary | question
  title: Maaperä ja tulvariski näytepisteellä
  created: 2026-09-25T10:15:00Z
  model: claude-opus-5          # ai only
  client: claude-desktop        # ai: ufield-voice | claude-desktop | claude-code | claude-ai; given: app | voice
  transcription:                # voice notes only
    status: done                # pending | done | failed
    engine: cloud:<provider>/<model>
    language: fi
    confidence: 0.91
    audio: media/2026-09-25T101500Z.m4a   # always kept
    recorded: 2026-09-25T10:15:00Z
    transcribed: 2026-09-25T10:21:40Z
  sources:
    layers: [gtk_maapera, syke_tulvat]
    features: []
    notes: []
    time: {from: 2026-05-01T00:00:00Z, to: 2026-09-01T00:00:00Z}
  license: [CC-BY-4.0]          # licences of every source
  attribution: ["© Geologian tutkimuskeskus", "© Syke"]
  visibility: proprietary
  ---
  ```

- Each note is also a STAC item (rule 6) in `catalog/items/<id>.json`, with its sources as provenance and the licences of its source layers; `catalog.json` links it. Note ids are `<UTC time>-<6 hex>`; files are created exclusively, so a note is never overwritten.
- Implemented in `server/src/ufield/project.py` (used by `ufield-mcp`); the app follows the same layout.
- Plain Markdown in the project folder means users can read notes in any editor, in QGIS, or in Obsidian, and Claude Code can work on the folder directly.

### 3. Analysis tools

| Question | Tool | Runs where |
|---|---|---|
| What is at this point on the map layers? | `sample_layers` | Project layers locally; registry layers from the source or via ufield-server |
| How do points compare with each other? | `compare_features` | Locally |
| How has it changed over time? | `get_time_series` | Feature history and nearby observations locally; NDVI and weather on ufield-server |
| What has been said about it? | `read_notes` | Locally |
| Record the result | `write_note` | Locally, into `ai/` or `analyses/` |

The tools return data with licence and attribution; the reasoning is Claude's, and it lands in a note with its sources. For point sampling against `via_server` layers and for NDVI/weather series, only point coordinates are sent to ufield-server.

### 4. Cloud speech-to-text, asynchronous for voice notes

Voice notes do not need text in real time, so transcription is a background job in the cloud, not on the phone.

1. **Record.** `add_voice_note` records audio (or takes an existing file), stores the original unmodified in `media/` (rule 5), and at once writes a given note with `transcription.status: pending` and a link to the audio. This works offline.
2. **Queue.** The recording joins an upload queue on the phone. It is sent when there is a connection (or only on Wi-Fi, per `set_voice_settings.transcribe_on`) and survives app restarts.
3. **Transcribe.** ufield-server receives the audio with the user's session and submits it to the cloud STT provider's batch/asynchronous API; the provider key stays on the server (`UFIELD_STT_API_KEY`, ADR 0002 §1). Batch transcription is usually cheaper and more accurate than streaming, and latency does not matter here.
4. **Fill in.** When the job finishes, the app receives the transcript (push, or on the next sync), writes it into the note body and sets `status: done`, with engine, language, confidence and times. On failure the status is `failed` with the reason, and the user can retry. Because the audio is always kept, notes can be re-transcribed later with a better model.
5. **Delete on the server.** The server deletes the audio and transcript as soon as the app has confirmed receipt, and asks the provider for no retention where it offers that. The only lasting copies are in the user's own storage.

Other rules:

- **Author stays given.** A transcript is the user's own words, so it is written to `given/` by the app, not by any model. No model rewrites it; a Claude summary of a voice note is a separate AI note.
- **Modes** (`set_voice_settings.mode`): `notes_only` (default) turns speech into given notes with no AI model involved. `agent` also sends spoken commands to Claude through `/agent`; commands need a connection and use the same cloud STT in its synchronous mode, since the user is waiting for the result.
- **Provider requirements:** good Finnish (and English, Swedish) on field vocabulary, batch API, EU processing, a DPA, no training on customer audio, and deletion on request. To be chosen in roadmap phase 0 by testing candidates on recorded field notes.
- **No on-device STT** in the MVP: no speech model in the app, which keeps the AAB smaller and the Finnish accuracy consistent across devices.

## Consequences

- Claude sees user data in agent mode and through connectors, and the STT provider receives all voice-note audio; the privacy policy and Play Data safety form must list both as processors, with DPAs in place (roadmap phase 7).
- Voice notes are unreadable until transcribed. The app shows pending notes with a play button so the audio is always usable, and the queue state is visible.
- Notes, layer attributes and transcripts are untrusted text. Claude clients must treat them as data; `ToolDispatcher` never lets tool output choose the author, and confirmation rules for `delete_*` apply to every client.
- Rule 1 still holds: the app needs a notes view (given and AI tabs per point, and project analyses) and screens for the analysis results, so a user without Claude can do the same things.
- Every layer in a μField project needs `ufield_uuid`; projects opened from plain QGIS get it added on first open (an upstream-visible change to the project, recorded in the project's CLAUDE.md).

## Open questions

- Which cloud STT provider; measure Finnish word error rate on recorded field notes before choosing.
- Whether the remote connector should ever read project data (would need server-side storage or Drive access, and a new ADR).
