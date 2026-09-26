# SPDX-License-Identifier: GPL-3.0-or-later
"""MCP round-trip tests: a real MCP client talking to ufield-mcp in-process."""

import json
import subprocess
import sys

import pytest
from mcp import Client

from conftest import A, MISSING
from ufield.mcp_local import build_server

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def server(project):
    return build_server(project)


async def test_lists_only_implemented_tools_with_standalone_schemas(server):
    async with Client(server) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}
    assert set(tools) == {"read_notes", "write_note"}
    for tool in tools.values():
        text = json.dumps(tool.input_schema)
        assert "$ref" not in text and "x-ufield" not in text
    assert tools["read_notes"].annotations.read_only_hint is True
    assert tools["write_note"].annotations.read_only_hint is False
    assert tools["write_note"].annotations.destructive_hint is False
    assert "author" not in tools["write_note"].input_schema["properties"]


async def test_write_then_read_round_trip(server, project):
    async with Client(server) as client:
        written = await client.call_tool(
            "write_note",
            {"feature_uuids": [A], "title": "Maaperä", "body_markdown": "Savi.", "sources": {"layers": ["gtk_maapera"]}},
        )
        assert written.is_error is False
        note = written.structured_content
        assert note["author"] == "ai" and note["path"].startswith(f"notes/{A}/ai/")

        read = await client.call_tool("read_notes", {"feature_uuids": [A]})
    notes = read.structured_content["notes"]
    assert [n["id"] for n in notes] == [note["id"]]
    assert notes[0]["body"] == "Savi.\n" and notes[0]["license"] == ["CC-BY-4.0"]
    # The client's own name is recorded, since no --client-name was given.
    assert notes[0]["client"]


async def test_errors_come_back_as_tool_errors(server):
    async with Client(server) as client:
        bad = await client.call_tool("write_note", {"title": "t"})
        missing = await client.call_tool("write_note", {"feature_uuids": [MISSING], "title": "t", "body_markdown": "b"})
        unlisted = await client.call_tool("delete_feature", {"feature_uuid": A, "confirm": True})
    assert bad.is_error and bad.structured_content["error"] == "invalid_input"
    assert missing.is_error and missing.structured_content["error"] == "feature_not_found"
    assert unlisted.is_error and unlisted.structured_content["error"] == "unknown_tool"


async def test_client_name_option_is_recorded(project):
    async with Client(build_server(project, client_name="claude-code")) as client:
        out = await client.call_tool("write_note", {"title": "t", "body_markdown": "b"})
    text = (project.root / out.structured_content["path"]).read_text(encoding="utf-8")
    assert "client: claude-code" in text


def test_cli_refuses_a_folder_that_is_not_a_project(tmp_path):
    run = subprocess.run(
        [sys.executable, "-m", "ufield.mcp_local", "--project", str(tmp_path)], capture_output=True, text=True, timeout=30
    )
    assert run.returncode == 2 and "not a μField project folder" in run.stderr
