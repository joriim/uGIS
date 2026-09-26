# SPDX-License-Identifier: GPL-3.0-or-later
"""Helpers for schema/tools.json, shared by scripts/ and the server: loading, exporting standalone tool schemas,
and the cross-field rules that ToolDispatcher enforces.

Tool input schemas avoid top-level oneOf/anyOf/allOf/if because several LLM
tool-calling APIs reject or mishandle them. Constraints that need them live in
an "x-ufield-rules" object on the tool instead; ToolDispatcher (and
check_rules below) enforce them. Exported schemas drop every "x-" key.

Rule kinds, each a list of property groups (a group is a list of names):
  exactly_one_of   exactly one group is used, and it is complete
  at_least_one_of  at least one group is complete
  at_most_one_of   at most one group is used
  required_if      [{"if": {prop: value}, "then_required": [props]}];
                   an absent prop counts as its schema default
A group is "used" when any of its properties is present.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import os

# In a repository checkout this file is server/src/ufield/schema.py; an installed
# wheel carries copies of tools.json and layers.yaml in ufield/data/.
_HERE = Path(__file__).resolve().parent
REPO_ROOT = _HERE.parent.parent.parent
_DATA = _HERE / "data"


def _locate(env: str, packaged: str, in_repo: Path) -> Path:
    if os.environ.get(env):
        return Path(os.environ[env])
    if (_DATA / packaged).exists():
        return _DATA / packaged
    return in_repo


TOOLS_PATH = _locate("UFIELD_TOOLS_JSON", "tools.json", REPO_ROOT / "schema" / "tools.json")
LAYERS_PATH = _locate("UFIELD_LAYERS_YAML", "layers.yaml", REPO_ROOT / "config" / "layers.yaml")
CASES_PATH = REPO_ROOT / "schema" / "tests" / "cases.json"

RULE_KINDS = ("exactly_one_of", "at_least_one_of", "at_most_one_of", "required_if")
FORBIDDEN_TOP_LEVEL = ("oneOf", "anyOf", "allOf", "if", "then", "else", "not", "dependentRequired", "dependentSchemas")


def load_tools(path: Path = TOOLS_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _resolve(doc: dict, ref: str) -> dict:
    if not ref.startswith("#/"):
        raise ValueError(f"only local refs are supported: {ref}")
    node = doc
    for part in ref[2:].split("/"):
        if not isinstance(node, dict) or part not in node:
            raise ValueError(f"unresolved $ref: {ref}")
        node = node[part]
    return node


def _inline(node, doc: dict, stack: tuple = ()):
    if isinstance(node, list):
        return [_inline(x, doc, stack) for x in node]
    if not isinstance(node, dict):
        return node
    out = {}
    if "$ref" in node:
        ref = node["$ref"]
        if ref in stack:
            raise ValueError(f"recursive $ref: {' -> '.join(stack + (ref,))}")
        out.update(_inline(copy.deepcopy(_resolve(doc, ref)), doc, stack + (ref,)))
    for key, value in node.items():
        if key == "$ref" or key.startswith("x-"):
            continue
        # Keys next to a $ref (e.g. a more specific description) win.
        out[key] = _inline(value, doc, stack)
    return out


def export_tool(doc: dict, tool: dict) -> dict:
    """The tool as an MCP / LLM client sees it: $defs inlined, x- keys removed."""
    return {
        "name": tool["name"],
        "description": tool["description"],
        "inputSchema": _inline(tool["inputSchema"], doc),
    }


def used_refs(node, acc: set | None = None) -> set:
    acc = set() if acc is None else acc
    if isinstance(node, dict):
        if "$ref" in node:
            acc.add(node["$ref"])
        for value in node.values():
            used_refs(value, acc)
    elif isinstance(node, list):
        for value in node:
            used_refs(value, acc)
    return acc


def rule_properties(rules: dict) -> set:
    names = set()
    for kind in ("exactly_one_of", "at_least_one_of", "at_most_one_of"):
        for group in rules.get(kind, []):
            names.update(group)
    for cond in rules.get("required_if", []):
        names.update(cond["if"])
        names.update(cond["then_required"])
    return names


def check_rules(schema: dict, instance: dict) -> list[str]:
    """Cross-field rule violations for a tool input (empty list = valid)."""
    rules = schema.get("x-ufield-rules", {})
    props = schema.get("properties", {})
    errors = []

    def used(group):
        return any(p in instance for p in group)

    def complete(group):
        return all(p in instance for p in group)

    def fmt(groups):
        return " | ".join("+".join(g) for g in groups)

    groups = rules.get("exactly_one_of")
    if groups:
        touched = [g for g in groups if used(g)]
        if len(touched) != 1 or not complete(touched[0]):
            errors.append(f"give exactly one of: {fmt(groups)}")
    groups = rules.get("at_least_one_of")
    if groups and not any(complete(g) for g in groups):
        errors.append(f"give at least one of: {fmt(groups)}")
    groups = rules.get("at_most_one_of")
    if groups and sum(used(g) for g in groups) > 1:
        errors.append(f"give at most one of: {fmt(groups)}")
    for cond in rules.get("required_if", []):
        matches = all(
            instance.get(k, props.get(k, {}).get("default")) == v
            for k, v in cond["if"].items()
        )
        if matches:
            missing = [p for p in cond["then_required"] if p not in instance]
            if missing:
                errors.append(f"when {cond['if']}, also give: {', '.join(missing)}")
    return errors


def format_json(node, width: int = 160) -> str:
    """Canonical layout for schema/tools.json: an object or array goes on one
    line ("{ "a": 1 }") when it fits in `width`, otherwise one member per line."""

    def one_line(n) -> str:
        if isinstance(n, dict):
            if not n:
                return "{}"
            inner = ", ".join(f"{json.dumps(k, ensure_ascii=False)}: {one_line(v)}" for k, v in n.items())
            return "{ " + inner + " }"
        if isinstance(n, list):
            return "[" + ", ".join(one_line(v) for v in n) + "]"
        return json.dumps(n, ensure_ascii=False)

    def fmt(n, indent: int, prefix_len: int) -> str:
        flat = one_line(n)
        if not isinstance(n, (dict, list)) or indent + prefix_len + len(flat) <= width:
            return flat
        pad = " " * (indent + 2)
        if isinstance(n, dict):
            items = []
            for k, v in n.items():
                key = f"{json.dumps(k, ensure_ascii=False)}: "
                items.append(pad + key + fmt(v, indent + 2, len(key)))
            return "{\n" + ",\n".join(items) + "\n" + " " * indent + "}"
        items = [pad + fmt(v, indent + 2, 0) for v in n]
        return "[\n" + ",\n".join(items) + "\n" + " " * indent + "]"

    return fmt(node, 0, 0) + "\n"
