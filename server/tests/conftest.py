# SPDX-License-Identifier: GPL-3.0-or-later
import sqlite3

import pytest

from ufield.dispatcher import ToolDispatcher
from ufield.project import Project, register_notes

A = "9b1c2d3e-4f50-4a6b-8c7d-0e1f2a3b4c5d"
B = "0b1c2d3e-4f50-4a6b-8c7d-0e1f2a3b4c5d"
MISSING = "ffffffff-4f50-4a6b-8c7d-0e1f2a3b4c5d"

REGISTRY = {
    "gtk_maapera": ("CC-BY-4.0", "© Geologian tutkimuskeskus"),
    "syke_tulvat": ("CC-BY-4.0", "© Syke"),
    "cdse_s2_openeo": ("copernicus-open", "Contains modified Copernicus Sentinel data {year}"),
}


def make_gpkg(path, uuids):
    """Minimal GeoPackage: gpkg_contents plus one feature table with ufield_uuid,
    and a second feature table without it (a plain QGIS layer)."""
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE gpkg_contents (table_name TEXT PRIMARY KEY, data_type TEXT)")
    con.execute("INSERT INTO gpkg_contents VALUES ('näytteet', 'features'), ('plain', 'features'), ('attrs', 'attributes')")
    con.execute('CREATE TABLE "näytteet" (fid INTEGER PRIMARY KEY, ufield_uuid TEXT, ph REAL)')
    con.executemany('INSERT INTO "näytteet" (ufield_uuid, ph) VALUES (?, 5.8)', [(u,) for u in uuids])
    con.execute("CREATE TABLE plain (fid INTEGER PRIMARY KEY, name TEXT)")
    con.commit()
    con.close()


@pytest.fixture
def project(tmp_path):
    make_gpkg(tmp_path / "data.gpkg", [A, B])
    return Project(tmp_path, registry=REGISTRY)


@pytest.fixture
def dispatcher(project):
    d = ToolDispatcher()
    register_notes(d, project)
    return d
