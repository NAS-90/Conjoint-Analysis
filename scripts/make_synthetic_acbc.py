"""Write a synthetic ACBC demo ``acbc_responses.csv`` (dashboard / quick trials).

The frame is generated from a known utility vector with the four §8 data-quality
pathologies injected (see :mod:`conjoint.acbc.synthetic`), plus a per-row
``duration`` column, so the quality screen and diagnostics have realistic input.

Usage (from Distance-Analysis/)::

    python scripts/make_synthetic_acbc.py
    python scripts/make_synthetic_acbc.py --out outputs/acbc_demo/acbc_responses.csv --seed 7
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:  # allow ``python scripts/make_synthetic_acbc.py``
    sys.path.insert(0, str(ROOT))

from conjoint.acbc.responses import write_acbc_responses  # noqa: E402
from conjoint.acbc.synthetic import generate_demo_responses  # noqa: E402

DEFAULT_OUT = ROOT / "outputs" / "acbc_demo" / "acbc_responses.csv"


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns a process exit code."""
    parser = argparse.ArgumentParser(
        prog="python scripts/make_synthetic_acbc.py",
        description="Write a synthetic ACBC responses CSV with injected quality issues.",
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output CSV path.")
    parser.add_argument("--seed", type=int, default=2026, help="random seed (default 2026).")
    args = parser.parse_args(argv)

    frame = generate_demo_responses(seed=args.seed)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    write_acbc_responses(frame, args.out)
    print(
        f"Wrote {len(frame)} rows "
        f"({frame['respondent'].nunique()} respondents) to {args.out}"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised via CLI
    raise SystemExit(main())
