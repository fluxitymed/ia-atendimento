from __future__ import annotations

from .reporting import dumps_report
from .runner import run_sandbox


def main() -> int:
    result = run_sandbox()
    print(dumps_report(result.as_dict()))
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
