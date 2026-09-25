# 0003 — Claude over MCP, point notes as Markdown, local speech-to-text

Status: proposed, 2026-09-25

## Context

Users should be able to keep working with their μField data in Claude: read what was recorded at each point, analyse points against map layers, against each other and over time, and write the results back where the user and later sessions can find them. Voice input needs an option that keeps audio on the phone.

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
      given/<created>_<slug>.md user: typed notes, verbatim transcripts
      ai/<created>_<slug>.md    AI: analysis of this point
  analyses/<created>_<slug>.md  AI: across points, against layers, over time
  catalog.json                  STAC
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
  transcription:                # given from voice only
    engine: whisper             # android | whisper | cloud:<provider>
    language: fi
    confidence: 0.91
    audio: media/2026-09-25T101500Z.m4a   # when keep_audio is on
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

- Each note is also a STAC item (rule 6), with its sources as provenance.
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

### 4. Speech-to-text on the device or in the cloud

- `set_voice_settings` chooses `stt_engine: on_device | cloud` and `mode: agent | dictation_only`.
- **On device:** the Android on-device recogniser (`SpeechRecognizer` on-device mode) where the device has a Finnish or English language pack *(verify availability per device)*, or **whisper.cpp** (MIT licence) with a multilingual model downloaded on first use, not shipped in the AAB. Finnish accuracy of phone-sized Whisper models must be measured on field vocabulary before it is offered as the default.
- **Cloud:** provider still to be chosen (roadmap phase 0); audio goes to that provider under a DPA.
- **Dictation only** saves the transcript as a given note or attribute value with no model involved. With on-device STT it works fully offline and no audio or text leaves the phone.
- In agent mode the transcript text goes to Claude through ufield-server even when STT runs on the device. The UI states this.
- `keep_audio` stores the original recording as an audio attachment and links it from the transcript note.

## Consequences

- Claude sees user data in agent mode and through connectors; the privacy policy and Play Data safety form must list Anthropic as a processor, and the DPA with Anthropic must be in place (roadmap phase 7).
- Notes, layer attributes and transcripts are untrusted text. Claude clients must treat them as data; `ToolDispatcher` never lets tool output choose the author, and confirmation rules for `delete_*` apply to every client.
- Rule 1 still holds: the app needs a notes view (given and AI tabs per point, and project analyses) and screens for the analysis results, so a user without Claude can do the same things.
- Every layer in a μField project needs `ufield_uuid`; projects opened from plain QGIS get it added on first open (an upstream-visible change to the project, recorded in the project's CLAUDE.md).

## Open questions

- Which cloud STT provider, and whether on-device Whisper is good enough in Finnish to be the default.
- Whether the remote connector should ever read project data (would need server-side storage or Drive access, and a new ADR).
