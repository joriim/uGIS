# ufield-server and ufield-mcp

Python side of μField (`CLAUDE.md`, ADR 0003). Today it contains:

| Module | What it does |
|---|---|
| `ufield.schema` | Loads `schema/tools.json`, exports standalone tool schemas, checks `x-ufield-rules`. Shared with `scripts/validate_schema`. |
| `ufield.dispatcher` | `ToolDispatcher`: validates every call (JSON Schema, cross-field rules, no credentials in URLs) and routes it to a handler. |
| `ufield.project` | A project folder's notes: `read_notes`, `write_note`, append-only Markdown with front matter, a STAC item per note. |
| `ufield.mcp_local` | `ufield-mcp`, the local MCP server (stdio) for Claude Desktop and Claude Code. |

The remote server (`/agent`, authenticated layer proxy, Farm Pack jobs, remote MCP) is not built yet (roadmap phase 3).

## Develop

```sh
cd server
uv sync
uv run pytest
```

The tests include MCP round trips: a real MCP client calls `ufield-mcp` in-process.

## Use μField data from Claude

`ufield-mcp` works on one project folder: a folder with `data.gpkg`, usually synced to your computer by Google Drive for desktop. Only the tools implemented in local mode are offered; today that is `read_notes` and `write_note`. Claude can read your notes and write AI notes; it cannot write in `given/` or change existing notes.

**Claude Code**

```sh
claude mcp add ufield -- uv run --directory /path/to/uGIS/server ufield-mcp --project "/path/to/Kotitila" --client-name claude-code
```

**Claude Desktop** (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "ufield": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/uGIS/server", "ufield-mcp",
               "--project", "/path/to/Kotitila", "--client-name", "claude-desktop"]
    }
  }
}
```

`--client-name` is written into each AI note's front matter as `client`; without it the MCP client's own name is used. The model is not recorded, since MCP clients don't report it.

## Where notes go

| Written by | About | Folder |
|---|---|---|
| The user (app, voice transcript) | one point | `notes/<ufield_uuid>/given/` |
| The user | several points, or the project | `notes/_project/given/` |
| A model (Claude over MCP, voice agent) | one point | `notes/<ufield_uuid>/ai/` |
| A model | several points, layers, time | `analyses/` |

The author comes from which client called, never from the input. Each note also gets `catalog/items/<id>.json` (STAC, with licences from the source layers in `config/layers.yaml`), linked from `catalog.json`.
