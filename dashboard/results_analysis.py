"""Conjoint *results* analysis — the substantive read-out of a fielded survey.

A pure (Streamlit-free) twin of :func:`dashboard.quality_diagnostics.analyze_responses`,
but pointed at *business results* rather than data-quality diagnostics:

* attribute importance + part-worth utilities (composed from the existing
  MNL + HB engine in :mod:`conjoint.acbc.estimate`);
* **willingness-to-pay** — both the *stated* Part C bands (which the quality
  pipeline ignores) and a *derived* monetary $/util read-off from the price
  part-worths;
* **purchase likelihood** — the B5 calibration probabilities;
* **respondent segments** — the Part A background answer distributions.

:func:`analyze_survey_results` returns one immutable :class:`SurveyResults`
bundle the dashboard renders. It is deterministic given ``seed`` and never
touches a workbook — the caller injects the band labels (``amount_bands``) and
price labels (``price_labels``) so the module stays presentation-agnostic.
"""

from __future__ import annotations

import re
from collections import OrderedDict
from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np
import pandas as pd

from conjoint.acbc import estimate
from conjoint.acbc.responses import (
    ITEM_COL,
    RESPONDENT_COL,
    RESPONSE_VALUE_COL,
    STAGE_BACKGROUND,
    STAGE_CALIBRATION,
    STAGE_COL,
    STAGE_TOURNAMENT,
    STAGE_WTP,
    TASK_ID_COL,
)
from dashboard import hb_settings

LevelUtilities = "OrderedDict[str, OrderedDict[str, float]]"


# ---------------------------------------------------------------------------
# Result bundles
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class WtpBand:
    """One Part C amount band + its representative dollar value (if parseable)."""

    code: str
    label: str
    representative_usd: float | None


@dataclass(frozen=True)
class FeatureWtp:
    """Stated WTP for one Part C feature, aggregated across respondents."""

    feature_id: str
    n_respondents: int
    band_counts: "OrderedDict[str, int]"
    modal_band: str
    share_paid: float  # fraction choosing any band above the cheapest
    mean_usd: float | None
    median_usd: float | None


@dataclass(frozen=True)
class WtpSummary:
    band_order: tuple[str, ...]
    bands: tuple[WtpBand, ...]
    features: "OrderedDict[str, FeatureWtp]"


@dataclass(frozen=True)
class DerivedWtp:
    """Monetary WTP derived from the price part-worths (utility-per-dollar)."""

    available: bool
    note: str
    price_attribute: str | None
    usd_per_util: float | None
    per_attribute: pd.DataFrame | None  # attribute, level, utility, usd_vs_worst


@dataclass(frozen=True)
class CalibrationSummary:
    n_concepts: int
    n_respondents: int
    mean_probability: float
    mean_probability_pct: float
    distribution: "OrderedDict[int, int]"  # 0..5 -> count
    per_respondent_mean: pd.DataFrame  # respondent, mean_prob, n_concepts


@dataclass(frozen=True)
class BackgroundSummary:
    n_respondents: int
    questions: "OrderedDict[str, OrderedDict[str, int]]"  # question_id -> answer -> count


@dataclass(frozen=True)
class SurveyResults:
    """Everything the results dashboard needs from one fit of a response frame."""

    n_respondents: int
    n_tournament_tasks: int
    importance: pd.DataFrame
    level_utilities: "OrderedDict[str, OrderedDict[str, float]]"
    rescaled_utilities: "OrderedDict[str, OrderedDict[str, float]]"
    hb_utilities: pd.DataFrame
    level_map: "OrderedDict[str, tuple[str, ...]]"
    rhat_max: float
    wtp: WtpSummary | None
    derived_wtp: DerivedWtp
    calibration: CalibrationSummary | None
    background: BackgroundSummary | None


# ---------------------------------------------------------------------------
# Dollar parsing helpers
# ---------------------------------------------------------------------------
def _dollar_amounts(text: object) -> list[float]:
    """Every dollar figure in a label, e.g. ``"$600 – $1 200"`` → ``[600, 1200]``."""
    amounts: list[float] = []
    for chunk in re.findall(r"\$[\s \xa0]*([0-9][0-9,.\s \xa0]*)", str(text)):
        cleaned = re.sub(r"[,\s \xa0]", "", chunk).rstrip(".")
        if cleaned:
            try:
                amounts.append(float(cleaned))
            except ValueError:
                continue
    return amounts


def parse_band_usd(label: object) -> float | None:
    """Representative dollars for a WTP band label (``None`` when unparseable).

    ``"Up to $100 more"`` → ``100``; ``"$400 or more"`` → ``400``; a "nothing"
    style label → ``0``; anything else → ``None`` (so means degrade gracefully).
    """
    if label is None:
        return None
    text = str(label).strip()
    if not text:
        return None
    amounts = _dollar_amounts(text)
    if amounts:
        return amounts[0]
    if any(word in text.lower() for word in ("nothing", "none", "no extra", "free")):
        return 0.0
    return None


def _price_level_usd(label: object) -> float | None:
    """Representative dollars for a price *tier* label (midpoint of a range)."""
    amounts = _dollar_amounts(label)
    if not amounts:
        return None
    if len(amounts) >= 2:
        return float(sum(amounts[:2]) / 2.0)
    return float(amounts[0])


# ---------------------------------------------------------------------------
# Stage parsers (each pure + individually testable)
# ---------------------------------------------------------------------------
def summarize_wtp(
    df: pd.DataFrame, bands: Sequence[tuple[str, str]] | None
) -> WtpSummary | None:
    """Aggregate stated Part C willingness-to-pay across respondents."""
    wtp = df[df[STAGE_COL] == STAGE_WTP]
    if wtp.empty:
        return None

    band_pairs = list(bands or [])
    if band_pairs:
        band_order = tuple(str(code) for code, _ in band_pairs)
        label_by_code = {str(code): str(label) for code, label in band_pairs}
    else:  # no workbook bands — fall back to observed codes, no $ values
        band_order = tuple(dict.fromkeys(wtp[RESPONSE_VALUE_COL].astype(str)))
        label_by_code = {code: code for code in band_order}

    band_objs = tuple(
        WtpBand(code, label_by_code.get(code, code), parse_band_usd(label_by_code.get(code, code)))
        for code in band_order
    )
    usd_by_code = {band.code: band.representative_usd for band in band_objs}
    rank = {code: index for index, code in enumerate(band_order)}

    features: "OrderedDict[str, FeatureWtp]" = OrderedDict()
    for feature_id, block in wtp.groupby(ITEM_COL, sort=False):
        codes = block[RESPONSE_VALUE_COL].astype(str)
        counts = OrderedDict((code, int((codes == code).sum())) for code in band_order)
        modal = max(counts, key=counts.get) if counts else ""
        share_paid = float(codes.map(lambda c: rank.get(c, 0) > 0).mean())
        usd_values = [usd_by_code[c] for c in codes if usd_by_code.get(c) is not None]
        mean_usd = float(np.mean(usd_values)) if usd_values else None
        median_usd = float(np.median(usd_values)) if usd_values else None
        features[str(feature_id)] = FeatureWtp(
            str(feature_id), int(len(codes)), counts, modal, share_paid, mean_usd, median_usd
        )
    return WtpSummary(band_order, band_objs, features)


def derived_monetary_wtp(
    level_utilities: Mapping[str, Mapping[str, float]],
    price_attribute: str,
    price_labels: Mapping[str, str] | None,
) -> DerivedWtp:
    """Translate part-worths into dollars via the price utility slope.

    ``usd_per_util = |Δ$| / |Δutility|`` across the price tiers; every other
    level is then valued as ``(utility − worst_level_utility) × usd_per_util``.
    Degrades to ``available=False`` (with a note) when price is missing or its
    labels carry no parseable dollar figures — never raises.
    """
    if price_attribute not in level_utilities:
        return DerivedWtp(False, f"no '{price_attribute}' attribute to anchor dollars", None, None, None)

    price_levels = level_utilities[price_attribute]
    labels = dict(price_labels or {})
    usd_by_level = {
        code: usd
        for code in price_levels
        if (usd := _price_level_usd(labels.get(code, code))) is not None
    }
    if len(usd_by_level) < 2:
        return DerivedWtp(
            False, "fewer than two price tiers carry a $ value", price_attribute, None, None
        )

    usd = np.array([usd_by_level[c] for c in usd_by_level])
    util = np.array([price_levels[c] for c in usd_by_level])
    delta_util = float(util.max() - util.min())
    if delta_util <= 1e-9:
        return DerivedWtp(False, "price part-worths are flat", price_attribute, None, None)
    usd_per_util = float((usd.max() - usd.min()) / delta_util)

    rows: list[dict[str, object]] = []
    for attribute, per_level in level_utilities.items():
        if attribute == price_attribute:
            continue
        worst = min(per_level.values())
        for level, value in per_level.items():
            rows.append(
                {
                    "attribute": attribute,
                    "level": level,
                    "utility": float(value),
                    "usd_vs_worst": float((value - worst) * usd_per_util),
                }
            )
    per_attribute = pd.DataFrame(rows, columns=["attribute", "level", "utility", "usd_vs_worst"])
    return DerivedWtp(True, "", price_attribute, usd_per_util, per_attribute)


def summarize_calibration(df: pd.DataFrame) -> CalibrationSummary | None:
    """Aggregate B5 purchase-probability (0..5) across respondents."""
    cal = df[df[STAGE_COL] == STAGE_CALIBRATION].copy()
    if cal.empty:
        return None
    cal["_prob"] = pd.to_numeric(cal[RESPONSE_VALUE_COL], errors="coerce")
    cal = cal.dropna(subset=["_prob"])
    if cal.empty:
        return None

    distribution = OrderedDict((i, int((cal["_prob"] == i).sum())) for i in range(6))
    per_respondent_mean = (
        cal.groupby(RESPONDENT_COL)["_prob"]
        .agg(["mean", "count"])
        .reset_index()
        .rename(columns={"mean": "mean_prob", "count": "n_concepts"})
    )
    mean_probability = float(cal["_prob"].mean())
    n_concepts = int(cal.groupby(RESPONDENT_COL)[TASK_ID_COL].nunique().max())
    return CalibrationSummary(
        n_concepts=n_concepts,
        n_respondents=int(cal[RESPONDENT_COL].nunique()),
        mean_probability=mean_probability,
        mean_probability_pct=mean_probability / 5.0 * 100.0,
        distribution=distribution,
        per_respondent_mean=per_respondent_mean,
    )


def summarize_background(df: pd.DataFrame) -> BackgroundSummary | None:
    """Per-question Part A answer distributions (multi-answers split on ``;``)."""
    bg = df[df[STAGE_COL] == STAGE_BACKGROUND]
    if bg.empty:
        return None
    questions: "OrderedDict[str, OrderedDict[str, int]]" = OrderedDict()
    for question_id, block in bg.groupby(ITEM_COL, sort=False):
        counts: "OrderedDict[str, int]" = OrderedDict()
        for raw in block[RESPONSE_VALUE_COL]:
            if raw is None or (isinstance(raw, float) and pd.isna(raw)):
                continue
            for part in str(raw).split(";"):
                answer = part.strip()
                if answer:
                    counts[answer] = counts.get(answer, 0) + 1
        questions[str(question_id)] = counts
    return BackgroundSummary(int(bg[RESPONDENT_COL].nunique()), questions)


# ---------------------------------------------------------------------------
# Main entry — compose the engine + stage parsers
# ---------------------------------------------------------------------------
def analyze_survey_results(
    df: pd.DataFrame,
    *,
    amount_bands: Sequence[tuple[str, str]] | None = None,
    price_labels: Mapping[str, str] | None = None,
    price_attribute: str = "price",
    hb_iter: int = hb_settings.HB_ITERATIONS,
    seed: int = hb_settings.HB_SEED,
) -> SurveyResults:
    """Fit MNL + HB and assemble importance / part-worths / WTP / calibration.

    Pure and deterministic given ``seed`` (no Streamlit). Raises if there are no
    Tournament rows to fit — the caller is expected to guard that.
    """
    mnl = estimate.fit_from_responses(df)
    level_utilities = estimate.beta_to_level_utilities(mnl.beta, mnl.column_names, mnl.level_map)
    importance = estimate.attribute_importance(mnl)
    rescaled = estimate.rescale_zero_centered_diffs(level_utilities)

    hb = estimate.fit_hb(
        df,
        n_iter=hb_iter,
        burn_in=hb_iter // 2,
        thinning=10,
        n_chains=2,
        seed=seed,
    )
    hb_utilities = estimate.hb_to_utilities(hb)
    level_map = OrderedDict((attr, tuple(levels)) for attr, levels in hb.level_map.items())
    rhat_max = float(np.nanmax(hb.rhat)) if hb.rhat.size else float("nan")

    tournament = df[df[STAGE_COL] == STAGE_TOURNAMENT]
    n_tasks = int(tournament.groupby([RESPONDENT_COL, TASK_ID_COL]).ngroups)

    return SurveyResults(
        n_respondents=int(tournament[RESPONDENT_COL].nunique()),
        n_tournament_tasks=n_tasks,
        importance=importance,
        level_utilities=level_utilities,
        rescaled_utilities=rescaled,
        hb_utilities=hb_utilities,
        level_map=level_map,
        rhat_max=rhat_max,
        wtp=summarize_wtp(df, amount_bands),
        derived_wtp=derived_monetary_wtp(level_utilities, price_attribute, price_labels),
        calibration=summarize_calibration(df),
        background=summarize_background(df),
    )
