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

    module = next(r for r in at.radio if r.label.startswith("分析模块"))
    module.set_value("ACBC 数据质量与诊断").run()
    assert not at.exception

    # New page title + the four diagnostic cards + the screen counters.
    assert any("数据质量与诊断" in t.value for t in at.title)
    metric_labels = {m.label for m in at.metric}
    assert {"Holdout 命中率", "个体 RLH 中位数", "价格单调性", "最大属性占比"} <= metric_labels
    assert "建议剔除合计" in metric_labels

    # The live-tuning sliders for the §8 screen are present.
    slider_labels = {s.label for s in at.slider}
    assert {"RLH 剔除阈值", "speeding 分位", "直线作答最少任务数"} <= slider_labels
