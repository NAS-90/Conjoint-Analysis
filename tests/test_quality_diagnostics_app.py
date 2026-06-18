"""AppTest smoke check for the ACBC quality & diagnostics dashboard page.

Verifies the ``app.py`` module switch renders the new page end-to-end (fit +
cards + sliders + table) without raising — the Streamlit render path that the
pure ``analyze_responses`` test cannot cover. It runs a real (short) HB fit on
the synthetic demo data, so it is marked ``integration`` and is the heaviest
test in the suite.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

REPO_ROOT = Path(__file__).resolve().parent.parent
APP = REPO_ROOT / "app.py"


@pytest.mark.integration
def test_module_switch_renders_quality_page() -> None:
    at = AppTest.from_file(str(APP), default_timeout=180).run()
    assert not at.exception

    module = next(r for r in at.radio if r.label == "Module")
    module.set_value("ACBC data quality & diagnostics").run()
    assert not at.exception

    # New page title + the four diagnostic cards + the screen counters.
    assert any("ACBC data quality & diagnostics" in t.value for t in at.title)
    metric_labels = {m.label for m in at.metric}
    assert {"Holdout hit-rate", "Median individual RLH", "Price monotonicity", "Max attribute share"} <= metric_labels
    assert "Total flagged for removal" in metric_labels

    # The live-tuning sliders for the §8 screen are present.
    slider_labels = {s.label for s in at.slider}
    assert {"RLH removal threshold", "Speeding percentile", "Min tasks for straight-lining"} <= slider_labels
