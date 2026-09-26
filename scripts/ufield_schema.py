# SPDX-License-Identifier: GPL-3.0-or-later
"""Scripts use the same schema helpers as the server: server/src/ufield/schema.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "server" / "src"))
from ufield.schema import *  # noqa: E402,F401,F403
from ufield.schema import _inline, _resolve  # noqa: E402,F401
