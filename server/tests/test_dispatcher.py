# SPDX-License-Identifier: GPL-3.0-or-later
import json

import pytest

from ufield import schema as us
from ufield.dispatcher import CallContext, Client, ToolDispatcher, ToolError, credential_in_url

UI = CallContext(Client.UI)


@pytest.fixture(scope="module")
def dispatcher():
    return ToolDispatcher()


def _cases():
    cases = json.loads(us.CASES_PATH.read_text(encoding="utf-8"))
    for name, sets in cases.items():
        for expect in ("valid", "invalid"):
            for i, inst in enumerate(sets[expect]):
                yield pytest.param(name, inst, expect == "valid", id=f"{name}-{expect}-{i}")


@pytest.mark.parametrize(("name", "args", "valid"), list(_cases()))
def test_schema_cases(dispatcher, name, args, valid):
    errors = dispatcher.validate(name, args)
    assert (not errors) == valid, errors


def test_every_exported_tool_is_standalone(dispatcher):
    for name in dispatcher._tools:
        text = json.dumps(dispatcher.exported(name))
        assert "$ref" not in text
        assert '"x-ufield-rules"' not in text


def test_unknown_tool(dispatcher):
    with pytest.raises(ToolError) as e:
        dispatcher.call("fly_drone", {}, UI)
    assert e.value.code == "unknown_tool"


def test_invalid_input_lists_every_problem(dispatcher):
    with pytest.raises(ToolError) as e:
        dispatcher.call("sample_layers", {"layers": ["gtk_maapera"]}, UI)
    assert e.value.code == "invalid_input"
    assert "feature_uuids" in e.value.message and "points" in e.value.message


def test_valid_but_unimplemented(dispatcher):
    with pytest.raises(ToolError) as e:
        dispatcher.call("sync_project", {}, UI)
    assert e.value.code == "not_implemented"


def test_handler_gets_args_and_context():
    d = ToolDispatcher()
    seen = {}

    def handler(args, ctx):
        seen.update(args=args, ctx=ctx)
        return {"ok": True}

    d.register("get_job_status", handler)
    assert d.call("get_job_status", {"job_id": "j1"}, UI) == {"ok": True}
    assert seen == {"args": {"job_id": "j1"}, "ctx": UI}
    assert d.implemented() == ["get_job_status"]


def test_register_unknown_tool_fails():
    with pytest.raises(KeyError):
        ToolDispatcher().register("fly_drone", lambda a, c: {})


@pytest.mark.parametrize(
    "url",
    [
        "https://x.org/wms?API-KEY=abc",
        "https://x.org/wms?Api_Key=abc",
        "https://x.org/wms?SERVICE=WMS&Token=abc",
        "https://x.org/tiles?access-token=abc",
        "https://x.org/f.tif?sv=1&SIG=abc",
        "https://u:p@x.org/wms",
        "https://u@x.org/wms",
    ],
)
def test_credentials_in_url_are_rejected(dispatcher, url):
    assert credential_in_url(url)
    errors = dispatcher.validate("add_layer", {"url": url, "service_type": "wms"})
    assert any("auth_config_id" in e for e in errors)


@pytest.mark.parametrize(
    "url",
    ["https://x.org/wms?SERVICE=WMS&REQUEST=GetCapabilities", "https://x.org/keys/wms?keywords=pelto", "https://x.org/monkey"],
)
def test_ordinary_urls_pass(url):
    assert credential_in_url(url) is None


def test_only_models_are_model_clients():
    assert Client.MCP.is_model and Client.VOICE_AGENT.is_model
    assert not Client.UI.is_model and not Client.VOICE_TRANSCRIPT.is_model
