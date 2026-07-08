"""python -m corral.generate [--check]"""

from __future__ import annotations

import sys

from . import check_all, write_all


def main(argv=None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args == ["--check"]:
        if check_all():
            return 0
        print(
            "generated artifacts are out of date — run: make generate",
            file=sys.stderr,
        )
        return 1
    if args:
        print("usage: python -m corral.generate [--check]", file=sys.stderr)
        return 1
    write_all()
    return 0


if __name__ == "__main__":
    sys.exit(main())
