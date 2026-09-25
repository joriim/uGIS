# Dependencies

Every third-party dependency, its licence and where it is used. Rule 3 in `CLAUDE.md`: licences must be compatible with GPL-3.0; check before adding.

## Development and CI tools (not shipped in the app or server)

| Package | Licence | Used by |
|---|---|---|
| jsonschema (with its dependency referencing) | MIT | `scripts/validate_schema` |
| PyYAML | MIT | `scripts/validate_schema` |

## App

None added yet beyond upstream Mergin Maps mobile (see upstream for its list). Planned: qtkeychain (BSD-3-Clause, ADR 0002).

## Server

None yet.
