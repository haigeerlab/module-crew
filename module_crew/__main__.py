"""CLI entry: python3 -m module_crew."""

import sys


def main(argv: list[str] | None = None) -> int:
    print("用法：module-crew store init|check", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
