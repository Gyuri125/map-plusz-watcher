"""A ``python -m allampapir_ertesito`` belépési pontja."""

from __future__ import annotations

import sys

if sys.version_info < (3, 11):
    print(
        "A MÁP+ értesítőhöz Python 3.11 vagy újabb szükséges. "
        f"Jelenlegi verzió: {sys.version.split()[0]}.",
        file=sys.stderr,
    )
    raise SystemExit(2)

from .cli import main  # noqa: E402

raise SystemExit(main())
