"""CLI for v3 campaign validation. Full by default; --turn skips large source hash."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from v3_core import ValidationError, validate


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--turn", action="store_true")
    arguments = parser.parse_args()
    try:
        result = validate(arguments.root, turn=arguments.turn)
    except (ValidationError, OSError, ValueError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
