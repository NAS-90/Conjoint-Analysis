"""Manual Section C feature setup for the standalone setup app.

The facilitator supplies a product noun plus six feature names.
The exported workbook preserves the template's Section A and ``bands`` rows,
adapts the product-specific Section A prompts, updates the top-factor options,
and replaces the example Section C rows with the six configured features and
reviewed prompts.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

import pandas as pd
import streamlit as st

from survey_views.theme import apply_base_theme, flow_header


BUNDLE_ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BUNDLE_ROOT.parent
SURVEY_TEMPLATE_WORKBOOK = PROJECT_ROOT / "survey_questions_template.xlsx"
ACTIVE_SURVEY_WORKBOOK = PROJECT_ROOT / "survey_questions.xlsx"
TEMPLATE_CANDIDATES = (
    SURVEY_TEMPLATE_WORKBOOK,
    BUNDLE_ROOT / "Input_template" / "survey_questions_template.xlsx",
    BUNDLE_ROOT / "input_template" / "survey_questions_template.xlsx",
)
SHEET_NAME = "Survey_questions"
TEMPLATE_COLUMNS = ["section", "id", "prompt", "input_type", "options", "help"]
FEATURE_COUNT = 6

FEATURE_SETUP_COMPLETE_KEY = "feature_setup_complete"
FEATURE_SETUP_SAVED_PATH_KEY = "feature_setup_saved_path"

_STEP_KEY = "feature_setup_step"
_ENTRY_VALUES_KEY = "feature_setup_entry_values"
_PRODUCT_KEY = "feature_setup_product"
_FEATURE_KEY_PREFIX = "feature_setup_feature"
_PROMPT_KEY_PREFIX = "feature_setup_prompt"
_PROMPT_SOURCE_KEY_PREFIX = "feature_setup_prompt_source"
_STEP_FEATURES = "features"
_STEP_PROMPTS = "prompts"
_TOP_FACTOR_ID = "top_factor"
_PRODUCT_PROMPT_IDS = {
    "purchase_timing",
    "current_brand",
    "usage",
    "top_factor",
}
_PHONE_TERM = re.compile(r"\b(?:smartphone|phone)\b", flags=re.IGNORECASE)


@dataclass(frozen=True)
class FeatureEntry:
    """One Section C feature with a generated or reviewed prompt."""

    feature_name: str
    prompt_text: str | None = None

    @property
    def feature_id(self) -> str:
        """Return the normalized machine-readable identifier."""
        return normalize_feature_id(self.feature_name)

    @property
    def prompt(self) -> str:
        """Return the Section C wording to write to the workbook."""
        if self.prompt_text is None:
            return default_feature_prompt(self.feature_id)
        return self.prompt_text.strip()


def _template_path() -> Path | None:
    """Return the first existing template path, if any."""
    for path in TEMPLATE_CANDIDATES:
        if path.exists():
            return path
    return None


def load_template_frame(template_path: Path | None = None) -> pd.DataFrame:
    """Read and validate the original ``Survey_questions`` template."""
    path = template_path or _template_path()
    if path is None:
        raise FileNotFoundError(
            "Could not find survey_questions_template.xlsx."
        )

    frame = pd.read_excel(path, sheet_name=SHEET_NAME, dtype=object).fillna("")
    missing = [column for column in TEMPLATE_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError(f"Survey template is missing columns: {', '.join(missing)}")
    return frame


def normalize_feature_id(feature_name: str) -> str:
    """Convert a feature label to the template's lowercase snake-case style."""
    normalized = re.sub(r"[^a-z0-9]+", "_", str(feature_name).casefold())
    return normalized.strip("_")


def default_feature_prompt(feature_id: str) -> str:
    """Return the editable default prompt for a normalized feature id."""
    return f"A much better {feature_id}."


def validate_feature_entries(entries: list[FeatureEntry], product_name: str) -> None:
    """Validate the product noun and the six Section C feature definitions."""
    if not str(product_name).strip():
        raise ValueError("Enter a product name or type.")
    if len(entries) != FEATURE_COUNT:
        raise ValueError(f"Exactly {FEATURE_COUNT} features are required.")

    feature_ids: list[str] = []
    for entry in entries:
        if not entry.feature_name.strip():
            raise ValueError("Every feature needs a name.")
        feature_id = entry.feature_id
        if not feature_id:
            raise ValueError(
                f"Feature '{entry.feature_name}' does not produce a usable id."
            )
        if not entry.prompt:
            raise ValueError(f"Feature '{feature_id}' needs a prompt.")
        feature_ids.append(feature_id)

    duplicates = sorted(
        feature_id for feature_id in set(feature_ids) if feature_ids.count(feature_id) > 1
    )
    if duplicates:
        raise ValueError(f"Feature ids must be unique: {', '.join(duplicates)}")


def _replace_product_term(prompt: object, product_name: str) -> str:
    """Replace standalone phone/smartphone terms with the configured product."""
    return _PHONE_TERM.sub(str(product_name).strip(), str(prompt))


def _feature_options(entries: list[FeatureEntry]) -> str:
    """Return the feature labels in the template's semicolon-separated style."""
    return "; ".join(entry.feature_name.strip() for entry in entries)


def build_survey_questions_frame(
    entries: list[FeatureEntry],
    product_name: str,
    template_frame: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Preserve non-C template rows and append six configured Section C rows."""
    validate_feature_entries(entries, product_name)
    template = (
        load_template_frame()
        if template_frame is None
        else template_frame.copy(deep=True).fillna("")
    )

    missing = [column for column in TEMPLATE_COLUMNS if column not in template.columns]
    if missing:
        raise ValueError(f"Survey template is missing columns: {', '.join(missing)}")

    section = template["section"].astype(str).str.strip().str.casefold()
    output = template.loc[section != "c"].copy()
    output_ids = output["id"].astype(str).str.strip().str.casefold()
    output_sections = output["section"].astype(str).str.strip().str.casefold()

    replaced_ids: set[str] = set()
    for question_id in _PRODUCT_PROMPT_IDS:
        mask = (output_sections == "a") & (output_ids == question_id)
        if int(mask.sum()) != 1:
            raise ValueError(
                f"Expected one Section A row with id '{question_id}' in the template."
            )
        row_index = output.index[mask][0]
        output.at[row_index, "prompt"] = _replace_product_term(
            output.at[row_index, "prompt"], product_name
        )
        replaced_ids.add(question_id)

    if replaced_ids != _PRODUCT_PROMPT_IDS:
        raise ValueError("Not all product-specific Section A prompts were updated.")

    top_factor_mask = (output_sections == "a") & (output_ids == _TOP_FACTOR_ID)
    if int(top_factor_mask.sum()) != 1:
        raise ValueError("Expected one Section A row with id 'top_factor'.")
    output.at[output.index[top_factor_mask][0], "options"] = _feature_options(entries)

    c_rows: list[dict[str, str]] = []
    for entry in entries:
        row = {column: "" for column in template.columns}
        row["section"] = "C"
        row["id"] = entry.feature_id
        row["prompt"] = entry.prompt.strip()
        c_rows.append(row)

    return pd.concat(
        [output, pd.DataFrame(c_rows, columns=template.columns)],
        ignore_index=True,
    )


def save_survey_questions_workbook(
    frame: pd.DataFrame,
    target: Path = ACTIVE_SURVEY_WORKBOOK,
) -> Path:
    """Save the workbook where the respondent survey reads it by default."""
    target.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(target, engine="openpyxl") as writer:
        frame.to_excel(writer, sheet_name=SHEET_NAME, index=False)
    return target


def _feature_key(index: int) -> str:
    return f"{_FEATURE_KEY_PREFIX}_{index}"


def _prompt_key(index: int) -> str:
    return f"{_PROMPT_KEY_PREFIX}_{index}"


def _prompt_source_key(index: int) -> str:
    return f"{_PROMPT_SOURCE_KEY_PREFIX}_{index}"


def _entry_values() -> dict[str, object]:
    """Return durable Step 1 values that survive hidden Streamlit widgets."""
    saved = st.session_state.get(_ENTRY_VALUES_KEY)
    if not isinstance(saved, dict):
        return {"product_name": "", "features": [""] * FEATURE_COUNT}

    features = saved.get("features", [])
    if not isinstance(features, list):
        features = []
    normalized_features = [
        str(value or "") for value in (features + [""] * FEATURE_COUNT)[:FEATURE_COUNT]
    ]
    return {
        "product_name": str(saved.get("product_name", "") or ""),
        "features": normalized_features,
    }


def _save_entry_values(product_name: str, entries: list[FeatureEntry]) -> None:
    """Copy Step 1 widget values into durable session state before Step 2."""
    st.session_state[_ENTRY_VALUES_KEY] = {
        "product_name": str(product_name).strip(),
        "features": [entry.feature_name.strip() for entry in entries],
    }


def _hydrate_entry_widgets() -> None:
    """Restore Step 1 widget keys from durable values before rendering inputs."""
    saved = _entry_values()
    product_name = str(saved["product_name"]).strip()
    if product_name and _PRODUCT_KEY not in st.session_state:
        st.session_state[_PRODUCT_KEY] = product_name

    features = saved["features"]
    if not isinstance(features, list):
        return
    for index, feature_name in enumerate(features[:FEATURE_COUNT]):
        key = _feature_key(index)
        if feature_name and key not in st.session_state:
            st.session_state[key] = feature_name


def _product_value() -> str:
    if _PRODUCT_KEY in st.session_state:
        value = str(st.session_state.get(_PRODUCT_KEY, "") or "").strip()
        if value or st.session_state.get(_STEP_KEY) != _STEP_PROMPTS:
            return value
    return str(_entry_values()["product_name"]).strip()


def _feature_value(index: int) -> str:
    key = _feature_key(index)
    if key in st.session_state:
        value = str(st.session_state.get(key, "") or "").strip()
        if value or st.session_state.get(_STEP_KEY) != _STEP_PROMPTS:
            return value

    features = _entry_values()["features"]
    if isinstance(features, list) and index < len(features):
        return str(features[index] or "").strip()
    return ""


def _prompt_value(index: int, feature_id: str) -> str:
    value = st.session_state.get(_prompt_key(index))
    if value is None:
        return default_feature_prompt(feature_id)
    return str(value).strip()


def _entry_complete(index: int) -> bool:
    return bool(_feature_value(index))


def _visible_feature_count() -> int:
    visible = 1
    for index in range(FEATURE_COUNT):
        if _entry_complete(index):
            visible = min(FEATURE_COUNT, index + 2)
    return visible


def _collect_entries(include_prompts: bool = True) -> list[FeatureEntry]:
    entries = []
    for index in range(FEATURE_COUNT):
        feature_name = _feature_value(index)
        if feature_name:
            feature_id = normalize_feature_id(feature_name)
            prompt_text = (
                _prompt_value(index, feature_id)
                if include_prompts and feature_id
                else None
            )
            entries.append(
                FeatureEntry(feature_name=feature_name, prompt_text=prompt_text)
            )
    return entries


def _reset_form() -> None:
    st.session_state.pop(_STEP_KEY, None)
    st.session_state.pop(_ENTRY_VALUES_KEY, None)
    st.session_state.pop(_PRODUCT_KEY, None)
    for index in range(FEATURE_COUNT):
        st.session_state.pop(_feature_key(index), None)
        st.session_state.pop(_prompt_key(index), None)
        st.session_state.pop(_prompt_source_key(index), None)
    st.session_state.pop(FEATURE_SETUP_COMPLETE_KEY, None)
    st.session_state.pop(FEATURE_SETUP_SAVED_PATH_KEY, None)


def _render_feature_block(index: int) -> None:
    """Render one feature-name input."""
    with st.container(border=True):
        st.text_input(
            f"Feature {index + 1}",
            key=_feature_key(index),
            placeholder="e.g. Camera",
        )


def _ensure_prompt_defaults(entries: list[FeatureEntry]) -> None:
    """Set prompt defaults, refreshing them when a feature id changes."""
    for index, entry in enumerate(entries):
        prompt_key = _prompt_key(index)
        source_key = _prompt_source_key(index)
        if st.session_state.get(source_key) != entry.feature_id:
            st.session_state[prompt_key] = default_feature_prompt(entry.feature_id)
            st.session_state[source_key] = entry.feature_id


def _render_prompt_review(entries: list[FeatureEntry]) -> list[FeatureEntry]:
    """Render editable Section C prompts after all feature ids are known."""
    _ensure_prompt_defaults(entries)
    st.subheader("Review prompts")
    reviewed_entries: list[FeatureEntry] = []
    for index, entry in enumerate(entries):
        with st.container(border=True):
            st.caption(f"id: {entry.feature_id}")
            st.text_area(
                f"Prompt {index + 1}",
                key=_prompt_key(index),
                height=80,
            )
        reviewed_entries.append(
            FeatureEntry(
                feature_name=entry.feature_name,
                prompt_text=_prompt_value(index, entry.feature_id),
            )
        )
    return reviewed_entries


def _render_export_controls(entries: list[FeatureEntry], product_name: str) -> None:
    """Render save controls for the reviewed prompt page."""
    reviewed_entries = _render_prompt_review(entries)

    try:
        validate_feature_entries(reviewed_entries, product_name)
    except ValueError as exc:
        st.error(str(exc))
        return

    if st.button("Save setup workbook", type="primary"):
        try:
            frame = build_survey_questions_frame(reviewed_entries, product_name)
            target = save_survey_questions_workbook(frame)
        except (FileNotFoundError, ValueError) as exc:
            st.error(str(exc))
            return
        st.session_state[FEATURE_SETUP_COMPLETE_KEY] = True
        st.session_state[FEATURE_SETUP_SAVED_PATH_KEY] = str(target)
        st.rerun()


def _render_feature_entry_page() -> None:
    """Render page 1: product and feature-name entry."""
    _hydrate_entry_widgets()
    flow_header(
        1,
        2,
        "Fill the feature blanks",
        "Name the product, then enter six features.",
    )
    st.text_input(
        "Product name or type",
        key=_PRODUCT_KEY,
        placeholder="e.g. tractor",
        help="Use a singular product noun without an article.",
    )

    product_name = _product_value()
    if not product_name:
        st.caption("Enter the product name to begin the feature setup.")
        return

    for index in range(_visible_feature_count()):
        _render_feature_block(index)

    entries = _collect_entries(include_prompts=False)
    st.progress(
        len(entries) / FEATURE_COUNT,
        text=f"Features complete: {len(entries)}/{FEATURE_COUNT}",
    )

    if len(entries) != FEATURE_COUNT:
        st.caption("Fill the current feature to unlock the next feature.")
        return

    try:
        validate_feature_entries(entries, product_name)
    except ValueError as exc:
        st.error(str(exc))
        return

    if st.button("Next: review prompts", type="primary"):
        _save_entry_values(product_name, entries)
        _ensure_prompt_defaults(entries)
        st.session_state[_STEP_KEY] = _STEP_PROMPTS
        st.rerun()


def _render_prompt_review_page() -> None:
    """Render page 2: prompt review and workbook export."""
    flow_header(
        2,
        2,
        "Modify the prompts",
        "Review each generated prompt, edit wording if needed, then save.",
    )
    product_name = _product_value()
    entries = _collect_entries(include_prompts=False)

    try:
        validate_feature_entries(entries, product_name)
    except ValueError as exc:
        st.error(str(exc))
        if st.button("Back to feature blanks"):
            st.session_state[_STEP_KEY] = _STEP_FEATURES
            st.rerun()
        return

    if st.button("Back to feature blanks"):
        st.session_state[_STEP_KEY] = _STEP_FEATURES
        st.rerun()

    _render_export_controls(entries, product_name)


def _render_saved_state() -> None:
    saved_path = st.session_state.get(FEATURE_SETUP_SAVED_PATH_KEY)
    if saved_path:
        st.success(f"Saved feature setup workbook: {saved_path}")
        path = Path(str(saved_path))
        if path.exists():
            st.download_button(
                "Download saved xlsx",
                data=path.read_bytes(),
                file_name=path.name,
                mime=(
                    "application/vnd.openxmlformats-officedocument."
                    "spreadsheetml.sheet"
                ),
                type="primary",
            )

    if st.button("Start feature setup over"):
        _reset_form()
        st.rerun()


def render_feature_setup() -> None:
    """Render the six-feature manual setup page."""
    apply_base_theme()

    if st.session_state.get(FEATURE_SETUP_COMPLETE_KEY):
        flow_header(
            2,
            2,
            "Setup workbook saved",
            "Download the workbook or start over.",
        )
        _render_saved_state()
        return

    step = st.session_state.get(_STEP_KEY, _STEP_FEATURES)
    if step == _STEP_PROMPTS:
        _render_prompt_review_page()
    else:
        _render_feature_entry_page()

    if st.button("Clear all entries"):
        _reset_form()
        st.rerun()
