# SPDX-License-Identifier: GPL-3.0-or-later
"""ToolDispatcher: the one entry point for every tool call.

The app UI, the voice agent and MCP clients all call tools through a
dispatcher. It validates input against schema/tools.json (JSON Schema plus the
tool's x-ufield-rules), applies checks the schema cannot express, and routes
the call to the handler registered for that tool.
"""

from __future__ import annotations

import enum
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qsl, urlsplit

from jsonschema import Draft202012Validator

from . import schema as us


class Client(enum.Enum):
    """Who is calling. Decides, among other things, who a note's author is."""

    UI = "ui"  # the app's own screens: the user acting directly
    VOICE_TRANSCRIPT = "voice_transcript"  # verbatim speech-to-text of the user
    VOICE_AGENT = "voice_agent"  # Claude acting on spoken commands
    MCP = "mcp"  # an MCP client such as Claude Desktop or Claude Code

    @property
    def is_model(self) -> bool:
        return self in (Client.VOICE_AGENT, Client.MCP)


@dataclass(frozen=True)
class CallContext:
    client: Client
    client_name: str = ""  # e.g. "claude-desktop"; recorded in note front matter
    model: str = ""  # model id when known (voice agent); MCP clients don't say


class ToolError(Exception):
    """A tool call that cannot be done. `code` is stable; `message` is for people."""

    def __init__(self, code: str, message: str, details: Any = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details

    def to_dict(self) -> dict:
        out = {"error": self.code, "message": self.message}
        if self.details is not None:
            out["details"] = self.details
        return out


# Query parameters that carry credentials (ADR 0002 §5), compared case-insensitively
# with "-" and "_" removed.
_SECRET_PARAMS = {"apikey", "key", "token", "accesstoken", "password", "passwd", "sig", "signature", "secret"}

Handler = Callable[[dict, CallContext], dict]


def credential_in_url(url: str) -> str | None:
    """Why `url` carries a credential, or None if it does not."""
    parts = urlsplit(url)
    if "@" in parts.netloc:
        return "the URL contains a user name or password"
    for name, _ in parse_qsl(parts.query, keep_blank_values=True):
        if name.lower().replace("-", "").replace("_", "") in _SECRET_PARAMS:
            return f"the URL contains the parameter '{name}'"
    return None


@dataclass
class ToolDispatcher:
    doc: dict = field(default_factory=us.load_tools)

    def __post_init__(self) -> None:
        self._tools = {t["name"]: t for t in self.doc["tools"]}
        self._exported = {name: us.export_tool(self.doc, t) for name, t in self._tools.items()}
        self._validators = {
            name: Draft202012Validator(e["inputSchema"]) for name, e in self._exported.items()
        }
        self._handlers: dict[str, Handler] = {}

    # -- registry ---------------------------------------------------------

    def register(self, name: str, handler: Handler) -> None:
        if name not in self._tools:
            raise KeyError(f"no tool named {name} in the schema")
        self._handlers[name] = handler

    def implemented(self) -> list[str]:
        return [n for n in self._tools if n in self._handlers]

    def exported(self, name: str) -> dict:
        """The tool as clients see it: $defs inlined, x- keys removed."""
        return self._exported[name]

    # -- validation -------------------------------------------------------

    def validate(self, name: str, args: dict) -> list[str]:
        """Every reason `args` is not a valid input for tool `name` (empty = valid)."""
        if name not in self._tools:
            return [f"no tool named {name}"]
        errors = []
        for err in sorted(self._validators[name].iter_errors(args), key=lambda e: list(e.path)):
            where = "/".join(str(p) for p in err.path)
            errors.append(f"{where}: {err.message}" if where else err.message)
        if not errors:
            errors += us.check_rules(self._tools[name]["inputSchema"], args)
        url = args.get("url")
        if isinstance(url, str):
            reason = credential_in_url(url)
            if reason:
                errors.append(
                    f"url: {reason}. Add the credential in the app's settings and pass its auth_config_id instead."
                )
        return errors

    # -- calls ------------------------------------------------------------

    def call(self, name: str, args: dict | None, ctx: CallContext) -> dict:
        args = {} if args is None else args
        if name not in self._tools:
            raise ToolError("unknown_tool", f"no tool named {name}")
        errors = self.validate(name, args)
        if errors:
            raise ToolError("invalid_input", "; ".join(errors), details=errors)
        handler = self._handlers.get(name)
        if handler is None:
            raise ToolError("not_implemented", f"{name} is not available here yet")
        return handler(args, ctx)
