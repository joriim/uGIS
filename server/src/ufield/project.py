# SPDX-License-Identifier: GPL-3.0-or-later
"""A μField project folder and its Markdown notes (ADR 0003 §2).

    <project>/
      data.gpkg                        features; layers carry a ufield_uuid field
      notes/<ufield_uuid>/given/*.md   user notes on one point
      notes/<ufield_uuid>/ai/*.md      AI notes on one point
      notes/_project/given/*.md        user notes on several points or the whole project
      analyses/*.md                    AI notes on several points, layers or time
      catalog.json, catalog/items/     STAC: one item per note (rule 6)

Notes are never edited or deleted here: every write creates a new file.
"""

from __future__ import annotations

import json
import re
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

import yaml

from . import schema as us
from .dispatcher import CallContext, ToolDispatcher, ToolError

PROJECT_NOTES = "_project"
STAC_VERSION = "1.1.0"
_SPDX_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.+-]*$")
_TRANSLIT = str.maketrans({"ä": "a", "ö": "o", "å": "a", "é": "e", "ü": "u"})


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_time(value) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            return _parse_time(datetime.fromisoformat(value.replace("Z", "+00:00")))
        except ValueError:
            return None
    return None


def slugify(title: str) -> str:
    words = re.findall(r"[a-z0-9]+", title.lower().translate(_TRANSLIT))
    return "-".join(words)[:40].strip("-") or "note"


def load_registry(path: Path = us.LAYERS_PATH) -> dict:
    """Layer id -> (licence, attribution) from config/layers.yaml; {} if unavailable."""
    try:
        reg = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError:
        return {}
    providers = reg.get("providers", {})
    out = {}
    for layer in reg.get("layers", []):
        p = providers.get(layer.get("provider"), {})
        out[layer["id"]] = (layer.get("license", p.get("license")), layer.get("attribution", p.get("attribution")))
    return out


@dataclass
class Note:
    path: Path  # relative to the project root
    meta: dict
    body: str

    def to_dict(self, include_body: bool = True) -> dict:
        out = {"path": self.path.as_posix(), **self.meta}
        if include_body:
            out["body"] = self.body
        return out


class Project:
    def __init__(self, root: Path, registry: dict | None = None):
        self.root = Path(root).resolve()
        self.registry = load_registry() if registry is None else registry

    # -- project and features --------------------------------------------

    @property
    def gpkg(self) -> Path:
        return self.root / "data.gpkg"

    def require_project(self) -> None:
        if not self.gpkg.is_file():
            raise ToolError("not_a_project", f"{self.root} is not a μField project folder (no data.gpkg)")

    def missing_features(self, uuids: list[str]) -> list[str]:
        """The uuids that no feature layer in data.gpkg contains."""
        if not uuids:
            return []
        self.require_project()
        found: set[str] = set()
        con = sqlite3.connect(f"{self.gpkg.as_uri()}?mode=ro", uri=True)
        try:
            tables = [r[0] for r in con.execute("SELECT table_name FROM gpkg_contents WHERE data_type = 'features'")]
            marks = ",".join("?" * len(uuids))
            for table in tables:
                quoted = '"' + table.replace('"', '""') + '"'
                cols = {r[1] for r in con.execute(f"PRAGMA table_info({quoted})")}
                if "ufield_uuid" in cols:
                    rows = con.execute(f"SELECT ufield_uuid FROM {quoted} WHERE ufield_uuid IN ({marks})", uuids)
                    found.update(r[0] for r in rows)
        except sqlite3.DatabaseError as e:
            raise ToolError("project_unreadable", f"cannot read data.gpkg: {e}") from e
        finally:
            con.close()
        return [u for u in uuids if u not in found]

    def _inside(self, path: Path) -> Path:
        resolved = path.resolve()
        if not resolved.is_relative_to(self.root):
            raise ToolError("path_outside_project", f"{path} resolves outside the project folder")
        return resolved

    # -- writing ----------------------------------------------------------

    def _note_dir(self, features: list[str], author: str) -> Path:
        if author == "ai":
            return self.root / "notes" / features[0] / "ai" if len(features) == 1 else self.root / "analyses"
        return self.root / "notes" / (features[0] if len(features) == 1 else PROJECT_NOTES) / "given"

    def _licences(self, layer_ids: list[str], year: int) -> tuple[list[str], list[str]]:
        licences, attributions = [], []
        for layer_id in layer_ids:
            lic, attr = self.registry.get(layer_id, (None, None))
            if lic and lic not in licences:
                licences.append(lic)
            if attr:
                attr = attr.replace("{year}", str(year))
                if attr not in attributions:
                    attributions.append(attr)
        return licences, attributions

    def write_note(self, args: dict, ctx: CallContext) -> dict:
        self.require_project()
        features = args.get("feature_uuids", [])
        sources = args.get("sources", {})
        missing = self.missing_features(features + [f for f in sources.get("features", []) if f not in features])
        if missing:
            raise ToolError("feature_not_found", "no feature with ufield_uuid " + ", ".join(missing), details=missing)

        catalog_path = self.root / "catalog.json"
        catalog = self._load_catalog(catalog_path)

        author = "ai" if ctx.client.is_model else "given"
        created = _now()
        note_id = f"{created:%Y%m%dT%H%M%SZ}-{secrets.token_hex(3)}"
        licences, attributions = self._licences(sources.get("layers", []), created.year)
        meta = {
            "id": note_id,
            "features": features,
            "author": author,
            "kind": args.get("kind", "analysis"),
            "title": args["title"],
            "created": _iso(created),
        }
        if author == "ai":
            meta["client"] = ctx.client_name or ctx.client.value
            if ctx.model:
                meta["model"] = ctx.model
        else:
            meta["client"] = "voice" if ctx.client.value == "voice_transcript" else "app"
        meta |= {
            "sources": {k: sources.get(k, []) for k in ("layers", "features", "notes", "assets")}
            | ({"time": sources["time"]} if "time" in sources else {}),
            "license": licences,
            "attribution": attributions,
            "visibility": args.get("visibility", "proprietary"),
        }

        note_dir = self._inside(self._note_dir(features, author))
        note_dir.mkdir(parents=True, exist_ok=True)
        path = self._inside(note_dir / f"{note_id}_{slugify(args['title'])}.md")
        text = "---\n" + yaml.safe_dump(meta, allow_unicode=True, sort_keys=False) + "---\n\n" + args["body_markdown"].rstrip() + "\n"
        with open(path, "x", encoding="utf-8") as f:  # "x": never overwrite a note
            f.write(text)

        rel = path.relative_to(self.root)
        item_rel = self._write_stac_item(meta, rel, ctx)
        catalog["links"].append({"rel": "item", "href": f"./{item_rel.as_posix()}", "type": "application/geo+json", "title": meta["title"]})
        catalog_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return {"id": note_id, "path": rel.as_posix(), "author": author, "stac_item": item_rel.as_posix()}

    def _load_catalog(self, path: Path) -> dict:
        if not path.exists():
            return {
                "type": "Catalog",
                "stac_version": STAC_VERSION,
                "id": "ufield-project",
                "description": "μField project catalog",
                "links": [{"rel": "root", "href": "./catalog.json", "type": "application/json"}],
            }
        try:
            catalog = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise ToolError("catalog_unreadable", f"catalog.json cannot be read, so nothing was written: {e}") from e
        if not isinstance(catalog, dict) or not isinstance(catalog.get("links"), list):
            raise ToolError("catalog_unreadable", "catalog.json has no links list, so nothing was written")
        return catalog

    def _write_stac_item(self, meta: dict, note_rel: Path, ctx: CallContext) -> Path:
        lic = meta["license"]
        stac_licence = " AND ".join(lic) if lic and all(_SPDX_ID.match(x) and x != "copernicus-open" for x in lic) else "other"
        src = meta["sources"]
        item = {
            "type": "Feature",
            "stac_version": STAC_VERSION,
            "id": meta["id"],
            "geometry": None,
            "properties": {
                "datetime": meta["created"],
                "title": meta["title"],
                "license": stac_licence,
                "ufield:asset_kind": "note",
                "ufield:author": meta["author"],
                "ufield:visibility": meta["visibility"],
                "ufield:provenance": {
                    "inputs": {
                        "features": sorted(set(meta["features"]) | set(src["features"])),
                        "notes": src["notes"],
                        "assets": src["assets"],
                        "layers": src["layers"],
                    },
                    "recipe": "write_note",
                    "client": meta["client"],
                    **({"model": meta["model"]} if "model" in meta else {}),
                },
            },
            "links": [
                {"rel": "root", "href": "../../catalog.json", "type": "application/json"},
                {"rel": "parent", "href": "../../catalog.json", "type": "application/json"},
            ],
            "assets": {"note": {"href": f"../../{note_rel.as_posix()}", "type": "text/markdown", "roles": ["data"]}},
        }
        rel = Path("catalog") / "items" / f"{meta['id']}.json"
        path = self._inside(self.root / rel)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "x", encoding="utf-8") as f:
            f.write(json.dumps(item, ensure_ascii=False, indent=2) + "\n")
        return rel

    # -- reading ----------------------------------------------------------

    def _note_files(self):
        for path in sorted((self.root / "notes").glob("*/*/*.md")):
            yield path, path.parent.name, path.parent.parent.name
        for path in sorted((self.root / "analyses").glob("*.md")):
            yield path, "ai", None

    def read_notes(self, args: dict, ctx: CallContext) -> dict:
        self.require_project()
        wanted = set(args.get("feature_uuids", []))
        author = args.get("author", "all")
        created = args.get("created", {})
        t_from, t_to = _parse_time(created.get("from")), _parse_time(created.get("to"))
        query = args.get("query", "").lower()
        notes, skipped = [], []

        for path, folder_author, owner in self._note_files():
            rel = path.relative_to(self.root)
            if folder_author not in ("given", "ai"):
                continue
            try:
                self._inside(path)
                note = self._parse(path, rel)
            except (ToolError, ValueError, OSError, yaml.YAMLError) as e:
                skipped.append({"path": rel.as_posix(), "reason": str(e)})
                continue
            # The folder, written by ToolDispatcher, decides the author.
            note.meta["author"] = folder_author
            features = note.meta.get("features") or ([] if owner in (None, PROJECT_NOTES) else [owner])
            note.meta["features"] = features
            if wanted:
                if not wanted & set(features):
                    continue
            elif len(features) == 1:
                continue  # no feature filter: notes not tied to a single point
            if author != "all" and folder_author != author:
                continue
            if "kind" in args and note.meta.get("kind") != args["kind"]:
                continue
            if "transcription" in args and (note.meta.get("transcription") or {}).get("status") != args["transcription"]:
                continue
            when = _parse_time(note.meta.get("created"))
            if (t_from or t_to) and when is None:
                continue
            if (t_from and when < t_from) or (t_to and when > t_to):
                continue
            if query and query not in (str(note.meta.get("title", "")) + "\n" + note.body).lower():
                continue
            note.meta["created"] = _iso(when) if when else note.meta.get("created")
            notes.append(note)

        notes.sort(key=lambda n: str(n.meta.get("created", "")), reverse=True)
        limit = args.get("limit", 50)
        include_body = args.get("include_body", True)
        return {
            "notes": [n.to_dict(include_body) for n in notes[:limit]],
            "total": len(notes),
            "skipped": skipped,
        }

    @staticmethod
    def _parse(path: Path, rel: Path) -> Note:
        text = path.read_text(encoding="utf-8")
        if not text.startswith("---\n"):
            raise ValueError("no front matter")
        end = text.find("\n---\n", 4)
        if end < 0:
            raise ValueError("front matter is not closed")
        meta = yaml.safe_load(text[4:end]) or {}
        if not isinstance(meta, dict):
            raise ValueError("front matter is not a mapping")
        return Note(rel, meta, text[end + 5 :].lstrip("\n"))


def register_notes(dispatcher: ToolDispatcher, project: Project) -> None:
    dispatcher.register("read_notes", project.read_notes)
    dispatcher.register("write_note", project.write_note)
