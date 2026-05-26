"""Build M2 dataset audit PPTX from the 5 rendered slide PNGs.

Each slide is a 1280x720 image laid out as a single full-bleed picture on a
16:9 slide. Speaker notes are attached per slide so the presenter can rehearse
in PowerPoint / Keynote without re-typing the talking points.
"""

from pathlib import Path

from pptx import Presentation
from pptx.util import Inches, Pt

HERE = Path(__file__).parent
SLIDES = [
    {
        "image": "slide_1_overview.png",
        "title": "Dataset Audit — Overview",
        "notes": (
            "Two datasets in scope: smartphones (1020 x 11) and tractors (166 x 31). "
            "Their Feature_data schemas differ (5 cols vs 8 cols), which already blocks "
            "a unified pipeline. Five core issues will drive the rest of the deck: "
            "column misalignment, composite-field explosion, format inconsistency, "
            "tractor brand coverage, and schema mismatch."
        ),
    },
    {
        "image": "slide_2_column_misalignment.png",
        "title": "Issue #1 — Smartphone Column Misalignment (P0)",
        "notes": (
            "255 rows (25% of the smartphone dataset) have the wrong value written into "
            "the `os` column — values like 'No FM Radio' (192 rows), 'Bluetooth' (38), "
            "and 'Memory Card Not Supported' (6) leaked in from neighbouring columns. "
            "Root cause is an upstream CSV parser that shifted columns when a cell was "
            "empty. Impact: the distance matrix on `os` silently treats 'No FM Radio' "
            "as a third operating system, corrupting 25% of all pairwise distances."
        ),
    },
    {
        "image": "slide_3_composite_fields.png",
        "title": "Issue #2 — Composite-Field Explosion (P0)",
        "notes": (
            "Six smartphone columns each pack 3-5 independent dimensions into a single "
            "cell. Camera holds five numbers (3 rear MPs + lens count + front MP), "
            "display holds size + resolution + refresh rate + notch type, and so on. "
            "Distance cannot be computed on these raw strings, and conjoint OLS needs "
            "per-dimension features to estimate part-worth utilities. Fix is a regex "
            "parser per field — preprocessing_smartphones.py already exists, just needs "
            "extension. Estimated 1-2 days of work."
        ),
    },
    {
        "image": "slide_4_tractor_issues.png",
        "title": "Issue #3 — Tractor Coverage & Quality (P1)",
        "notes": (
            "Tractor data is structurally cleaner (31 atomic columns) but suffers from "
            "two issues. First, brand coverage: only Valtra and Massey Ferguson, both "
            "AGCO subsidiaries — no competitor benchmark for John Deere, Kubota, "
            "Case IH, or New Holland. Distance results are intra-AGCO only, not useful "
            "for blue-ocean analysis. Second, concrete errors: weight=0 in 4 rows, "
            "turning_radius missing in 9.6%, and the `product` column is a redundant "
            "pipe-concat of fields that already exist as independent columns."
        ),
    },
    {
        "image": "slide_5_priority_actions.png",
        "title": "Recommended Actions for M2",
        "notes": (
            "Six prioritized actions: two P0 (column re-parse + composite parser, owner "
            "yongheng), two P1 (schema template + tractor competitor data, team), two "
            "P2 (numeric error handling + format normalization). Suggested 2-week plan: "
            "Week 1 = P0 + schema lock-in + Nico alignment; Week 2 = competitor data + "
            "P2 polish + dashboard update. Four open questions for the team: 8-step "
            "pipeline confirmation, third product category, composite features in OLS, "
            "gap=0.8 threshold tuning."
        ),
    },
]


def build() -> Path:
    prs = Presentation()
    # 16:9 = 13.333 x 7.5 inches (matches our 1280x720 renders)
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)

    blank_layout = prs.slide_layouts[6]  # Blank

    for spec in SLIDES:
        slide = prs.slides.add_slide(blank_layout)
        slide.shapes.add_picture(
            str(HERE / spec["image"]),
            left=0,
            top=0,
            width=prs.slide_width,
            height=prs.slide_height,
        )

        notes_tf = slide.notes_slide.notes_text_frame
        notes_tf.text = spec["title"]
        p = notes_tf.add_paragraph()
        p.text = spec["notes"]
        for para in notes_tf.paragraphs:
            for run in para.runs:
                run.font.size = Pt(12)

    out_path = HERE / "M2_Dataset_Audit.pptx"
    prs.save(str(out_path))
    return out_path


if __name__ == "__main__":
    path = build()
    print(f"Wrote {path}")
