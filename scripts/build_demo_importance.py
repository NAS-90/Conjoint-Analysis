"""Convert the published N=381 tractor importance reference to ``importance.csv``.

The conjoint demo (see :mod:`scripts.build_demo_workbook`) re-uses the *real*
N=381 tractor conjoint relative importance as its customer-weighting input, so
the dashboard's customer-weighted view is driven by an authentic study rather
than a fabricated weighting.

Source : ``tests/fixtures/n381/importance_reference.json`` (RI + AI per
attribute; the 7 attribute names already match the demo's feature names).
Output : an ``importance.csv`` with the canonical
``attribute, absolute_importance, relative_importance`` columns, written via the
shared :mod:`conjoint.io` contract so it round-trips through Module 3/4.

Usage (from Distance-Analysis/)::

    python scripts/build_demo_importance.py \
        --reference tests/fixtures/n381/importance_reference.json \
        --out outputs/conjoint_demo/importance.csv
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:  # allow ``python scripts/build_demo_importance.py``
    sys.path.insert(0, str(ROOT))

from conjoint.io import (  # noqa: E402  (import after sys.path bootstrap)
    ABSOLUTE_IMPORTANCE_COL,
    ATTRIBUTE_COL,
    RELATIVE_IMPORTANCE_COL,
    write_importance,
)

DEFAULT_REFERENCE = ROOT / "tests" / "fixtures" / "n381" / "importance_reference.json"
DEFAULT_OUT = ROOT / "outputs" / "conjoint_demo" / "importance.csv"


def reference_to_importance(reference: dict[str, dict[str, float]]) -> pd.DataFrame:
    """Turn the ``{attribute: {absolute_importance, relative_importance}}`` map
    into a canonical importance frame.

    Attribute order follows the JSON insertion order (which mirrors the
    questionnaire/workbook order: engine, injection, transmission, shuttle,
    gears, cabin, tank). The input dict is never mutated.
    """
    if not isinstance(reference, dict) or not reference:
        raise ValueError("importance reference must be a non-empty JSON object")

    records: list[dict[str, object]] = []
    for attribute, entry in reference.items():
        if not isinstance(entry, dict):
            raise ValueError(f"reference entry for {attribute!r} must be an object")
        if RELATIVE_IMPORTANCE_COL not in entry or ABSOLUTE_IMPORTANCE_COL not in entry:
            raise ValueError(
                f"reference entry for {attribute!r} must carry "
                f"'{ABSOLUTE_IMPORTANCE_COL}' and '{RELATIVE_IMPORTANCE_COL}'"
            )
        records.append(
            {
                ATTRIBUTE_COL: str(attribute),
                ABSOLUTE_IMPORTANCE_COL: float(entry[ABSOLUTE_IMPORTANCE_COL]),
                RELATIVE_IMPORTANCE_COL: float(entry[RELATIVE_IMPORTANCE_COL]),
            }
        )
    return pd.DataFrame.from_records(records)


def build(reference_path: Path, out_path: Path) -> pd.DataFrame:
    """Read the reference JSON, build the importance frame, and write it."""
    reference = json.loads(Path(reference_path).read_text(encoding="utf-8"))
    importance = reference_to_importance(reference)
    write_importance(importance, out_path)
    return importance


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, default=DEFAULT_REFERENCE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    importance = build(args.reference, args.out)
    print(f"Wrote importance for {len(importance)} attributes to {args.out}")
    for _, row in importance.iterrows():
        print(
            f"  {row[ATTRIBUTE_COL]:<14s} "
            f"RI={row[RELATIVE_IMPORTANCE_COL] * 100:6.2f}%  "
            f"AI={row[ABSOLUTE_IMPORTANCE_COL]:.4f}"
        )
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised via CLI
    raise SystemExit(main())
