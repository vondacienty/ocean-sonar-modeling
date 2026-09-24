"""Module entry point for ``python -m ocean_sonar``."""

from __future__ import annotations

import sys

from ocean_sonar.cli import main as _cli_main


def main(argv: list[str] | None = None) -> int:
    return _cli_main(argv)


if __name__ == "__main__":
    sys.exit(main())
