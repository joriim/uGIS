# Dependencies

Every third-party dependency, its licence and where it is used. Rule 3 in `CLAUDE.md`: licences must be compatible with GPL-3.0; check before adding.

## Development and CI tools (not shipped in the app or server)

| Package | Licence | Used by |
|---|---|---|
| jsonschema (with its dependency referencing) | MIT | `scripts/validate_schema` |
| PyYAML | MIT | `scripts/validate_schema` |

## App

None added yet beyond upstream Mergin Maps mobile (see upstream for its list). Planned: qtkeychain (BSD-3-Clause, ADR 0002).

## Server (`server/`, direct dependencies)

| Package | Licence | Used for |
|---|---|---|
| mcp (with mcp-types) | MIT | MCP server (`ufield-mcp`) |
| jsonschema | MIT | tool input validation in `ToolDispatcher` |
| PyYAML | MIT | layer registry, note front matter |
| hatchling (build only) | MIT | building the wheel |
| pytest (dev only) | MIT | tests |

Main transitive dependencies of mcp: anyio, pydantic (MIT), starlette (BSD-3-Clause). The full pinned set is in `server/uv.lock`.
