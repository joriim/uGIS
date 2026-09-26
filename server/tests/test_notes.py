# SPDX-License-Identifier: GPL-3.0-or-later
import json

import pytest
import yaml

from conftest import A, B, MISSING
from ufield.dispatcher import CallContext, Client, ToolError
from ufield.project import Project, slugify

UI = CallContext(Client.UI)
VOICE = CallContext(Client.VOICE_TRANSCRIPT)
CLAUDE = CallContext(Client.MCP, client_name="claude-desktop")
AGENT = CallContext(Client.VOICE_AGENT, client_name="ufield-voice", model="claude-opus-5")


def write(d, ctx, **args):
    return d.call("write_note", {"title": "Maaperä", "body_markdown": "## Summary\nSavi.", **args}, ctx)


def front_matter(project, rel):
    text = (project.root / rel).read_text(encoding="utf-8")
    return yaml.safe_load(text.split("---\n")[1])


# -- where notes go and who wrote them ---------------------------------------


def test_ai_note_on_one_point(dispatcher, project):
    out = write(dispatcher, CLAUDE, feature_uuids=[A])
    assert out["author"] == "ai"
    assert out["path"].startswith(f"notes/{A}/ai/") and out["path"].endswith("_maapera.md")
    meta = front_matter(project, out["path"])
    assert meta["author"] == "ai" and meta["client"] == "claude-desktop" and "model" not in meta
    assert meta["features"] == [A] and meta["kind"] == "analysis" and meta["visibility"] == "proprietary"


def test_ai_note_on_several_points_goes_to_analyses(dispatcher):
    assert write(dispatcher, CLAUDE, feature_uuids=[A, B])["path"].startswith("analyses/")
    assert write(dispatcher, CLAUDE)["path"].startswith("analyses/")


def test_voice_agent_records_its_model(dispatcher, project):
    meta = front_matter(project, write(dispatcher, AGENT, feature_uuids=[A])["path"])
    assert meta["author"] == "ai" and meta["model"] == "claude-opus-5" and meta["client"] == "ufield-voice"


def test_user_notes_are_given(dispatcher, project):
    out = write(dispatcher, UI, feature_uuids=[A])
    assert out["author"] == "given" and out["path"].startswith(f"notes/{A}/given/")
    assert front_matter(project, out["path"])["client"] == "app"
    assert front_matter(project, write(dispatcher, VOICE, feature_uuids=[A])["path"])["client"] == "voice"
    assert write(dispatcher, UI, feature_uuids=[A, B])["path"].startswith("notes/_project/given/")


def test_a_model_cannot_choose_the_author(dispatcher):
    with pytest.raises(ToolError) as e:
        write(dispatcher, CLAUDE, feature_uuids=[A], author="given")
    assert e.value.code == "invalid_input"


def test_notes_are_append_only(dispatcher, project):
    a = write(dispatcher, CLAUDE, feature_uuids=[A])
    b = write(dispatcher, CLAUDE, feature_uuids=[A])
    assert a["id"] != b["id"] and a["path"] != b["path"]
    assert len(list((project.root / "notes" / A / "ai").glob("*.md"))) == 2


# -- validation against the project ------------------------------------------


def test_unknown_feature_is_rejected_and_nothing_written(dispatcher, project):
    with pytest.raises(ToolError) as e:
        write(dispatcher, CLAUDE, feature_uuids=[MISSING])
    assert e.value.code == "feature_not_found" and e.value.details == [MISSING]
    with pytest.raises(ToolError):
        write(dispatcher, CLAUDE, feature_uuids=[A], sources={"features": [MISSING]})
    assert not (project.root / "notes").exists() and not (project.root / "catalog.json").exists()


def test_folder_without_data_gpkg_is_not_a_project(tmp_path):
    from ufield.dispatcher import ToolDispatcher
    from ufield.project import register_notes

    d = ToolDispatcher()
    register_notes(d, Project(tmp_path, registry={}))
    for name, args in (("write_note", {"title": "t", "body_markdown": "b"}), ("read_notes", {})):
        with pytest.raises(ToolError) as e:
            d.call(name, args, CLAUDE)
        assert e.value.code == "not_a_project"


def test_broken_catalog_blocks_the_write(dispatcher, project):
    (project.root / "catalog.json").write_text("{not json")
    with pytest.raises(ToolError) as e:
        write(dispatcher, CLAUDE, feature_uuids=[A])
    assert e.value.code == "catalog_unreadable"
    assert not (project.root / "notes").exists()


def test_notes_folder_symlinked_outside_is_refused(dispatcher, project, tmp_path_factory):
    outside = tmp_path_factory.mktemp("outside")
    (project.root / "analyses").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ToolError) as e:
        write(dispatcher, CLAUDE)
    assert e.value.code == "path_outside_project"
    assert list(outside.iterdir()) == []


# -- provenance and licences (rule 6) ----------------------------------------


def test_licences_and_attribution_come_from_source_layers(dispatcher, project):
    out = write(
        dispatcher,
        CLAUDE,
        feature_uuids=[A],
        sources={"layers": ["gtk_maapera", "syke_tulvat", "my_project_layer"], "time": {"from": "2026-05-01T00:00:00Z"}},
    )
    meta = front_matter(project, out["path"])
    assert meta["license"] == ["CC-BY-4.0"]
    assert meta["attribution"] == ["© Geologian tutkimuskeskus", "© Syke"]
    assert meta["sources"]["time"] == {"from": "2026-05-01T00:00:00Z"}

    item = json.loads((project.root / out["stac_item"]).read_text())
    props = item["properties"]
    assert item["id"] == out["id"] and item["geometry"] is None
    assert props["license"] == "CC-BY-4.0" and props["ufield:visibility"] == "proprietary"
    assert props["ufield:provenance"]["inputs"]["layers"] == ["gtk_maapera", "syke_tulvat", "my_project_layer"]
    assert props["ufield:provenance"]["recipe"] == "write_note"
    assert item["assets"]["note"]["href"] == f"../../{out['path']}"

    catalog = json.loads((project.root / "catalog.json").read_text())
    assert {"rel": "item", "href": f"./{out['stac_item']}", "type": "application/geo+json", "title": "Maaperä"} in catalog["links"]


def test_non_spdx_licence_becomes_other_and_year_is_filled(dispatcher, project):
    out = write(dispatcher, CLAUDE, sources={"layers": ["cdse_s2_openeo"]})
    meta = front_matter(project, out["path"])
    assert meta["attribution"][0].startswith("Contains modified Copernicus Sentinel data 20")
    assert json.loads((project.root / out["stac_item"]).read_text())["properties"]["license"] == "other"


def test_catalog_keeps_existing_links(dispatcher, project):
    (project.root / "catalog.json").write_text(json.dumps({"type": "Catalog", "id": "x", "links": [{"rel": "child", "href": "./layers.json"}]}))
    write(dispatcher, CLAUDE)
    links = json.loads((project.root / "catalog.json").read_text())["links"]
    assert links[0] == {"rel": "child", "href": "./layers.json"} and links[1]["rel"] == "item"


# -- reading -----------------------------------------------------------------


def test_read_by_point_and_author(dispatcher):
    write(dispatcher, UI, feature_uuids=[A], title="Havainto")
    write(dispatcher, CLAUDE, feature_uuids=[A], title="Analyysi")
    write(dispatcher, CLAUDE, feature_uuids=[B], title="Toinen piste")
    out = dispatcher.call("read_notes", {"feature_uuids": [A]}, CLAUDE)
    assert out["total"] == 2 and {n["title"] for n in out["notes"]} == {"Havainto", "Analyysi"}
    given = dispatcher.call("read_notes", {"feature_uuids": [A], "author": "given"}, CLAUDE)
    assert [n["title"] for n in given["notes"]] == ["Havainto"] and given["notes"][0]["author"] == "given"


def test_read_without_filter_returns_notes_not_tied_to_one_point(dispatcher):
    write(dispatcher, CLAUDE, feature_uuids=[A], title="Yksi piste")
    write(dispatcher, CLAUDE, feature_uuids=[A, B], title="Kaksi pistettä")
    write(dispatcher, UI, title="Projektin muistiinpano")
    titles = {n["title"] for n in dispatcher.call("read_notes", {}, CLAUDE)["notes"]}
    assert titles == {"Kaksi pistettä", "Projektin muistiinpano"}


def test_read_filters(dispatcher, project):
    write(dispatcher, CLAUDE, feature_uuids=[A], title="pH", body_markdown="Happamuus 5,8", kind="observation")
    write(dispatcher, CLAUDE, feature_uuids=[A], title="Tulva", body_markdown="Tulvariski pieni")
    call = lambda **a: dispatcher.call("read_notes", {"feature_uuids": [A], **a}, CLAUDE)  # noqa: E731
    assert [n["title"] for n in call(kind="observation")["notes"]] == ["pH"]
    assert [n["title"] for n in call(query="TULVARISKI")["notes"]] == ["Tulva"]
    assert call(created={"from": "2000-01-01T00:00:00Z", "to": "2100-01-01T00:00:00Z"})["total"] == 2
    assert call(created={"to": "2000-01-01T00:00:00Z"})["total"] == 0
    out = call(limit=1, include_body=False)
    assert out["total"] == 2 and len(out["notes"]) == 1 and "body" not in out["notes"][0]


def test_pending_voice_notes_and_hand_written_files(dispatcher, project):
    folder = project.root / "notes" / A / "given"
    folder.mkdir(parents=True)
    (folder / "20260925T101500Z-aaaaaa_voice.md").write_text(
        "---\nid: v1\ntitle: Ääniviesti\ncreated: 2026-09-25T10:15:00Z\n"  # unquoted: YAML reads a datetime
        "transcription: {status: pending, audio: media/a.m4a}\n---\n",
        encoding="utf-8",
    )
    (folder / "broken.md").write_text("no front matter", encoding="utf-8")
    (folder / "sneaky.md").write_text("---\nauthor: ai\ntitle: says ai\n---\nbody", encoding="utf-8")

    out = dispatcher.call("read_notes", {"feature_uuids": [A], "transcription": "pending"}, CLAUDE)
    assert [n["title"] for n in out["notes"]] == ["Ääniviesti"]
    assert out["notes"][0]["created"] == "2026-09-25T10:15:00Z"
    assert out["skipped"] == [{"path": f"notes/{A}/given/broken.md", "reason": "no front matter"}]

    sneaky = [n for n in dispatcher.call("read_notes", {"feature_uuids": [A]}, CLAUDE)["notes"] if n["title"] == "says ai"]
    assert sneaky[0]["author"] == "given"  # the folder decides, not the file


@pytest.mark.parametrize(("title", "slug"), [("Maaperä ja tulvariski", "maapera-ja-tulvariski"), ("!!!", "note"), ("a" * 80, "a" * 40)])
def test_slugify(title, slug):
    assert slugify(title) == slug
