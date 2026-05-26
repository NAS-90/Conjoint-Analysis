"""Build the P1 Foundation Update PPTX from the 12 rendered slide PNGs.

Each slide is a 1280x720 render laid out as a single full-bleed picture on a
16:9 slide. Speaker notes are attached per slide so the presenter can rehearse
in PowerPoint / Keynote without re-typing the talking points.

Regenerate the PNGs from presentation/refactor_report.html, then run:
    python3 build_pptx.py
"""

from pathlib import Path

from pptx import Presentation
from pptx.util import Inches, Pt

HERE = Path(__file__).parent

SLIDES = [
    {
        "image": "slide_01.png",
        "title": "1 · Title — Making the tool usable, by everyone",
        "notes": (
            "This is a Phase 1 progress update. Before we layer customer "
            "preferences onto the tool, the foundation has to be solid. Two "
            "things this update delivers: one clean data engine, and a "
            "one-click setup the whole team can run."
        ),
    },
    {
        "image": "slide_02.png",
        "title": "2 · Where this fits",
        "notes": (
            "Quick map of the project. The tool today tells you how alike two "
            "products are using only their technical specs. Our 3-month goal is "
            "to also weigh in what customers care about. The work is split into "
            "four phases; we are in P1, the foundation. This update covers my "
            "two P1 jobs: get the tool running for everyone, and lay the "
            "groundwork for Module 1, the universal data engine."
        ),
    },
    {
        "image": "slide_03.png",
        "title": "3 · How the tool works (60-second primer)",
        "notes": (
            "Primer for anyone non-technical. A messy Excel goes in - prices "
            "with currency symbols, ranges like 61-70, Yes/No text. A 'data "
            "tidier' cleans it into plain numbers. Then math measures the gaps; "
            "small gaps mean similar products, likely competitors. Everything "
            "depends on that middle step - and that is the part we rebuilt."
        ),
    },
    {
        "image": "slide_04.png",
        "title": "4 · Problem 1 — the same work, written three times",
        "notes": (
            "The first problem was duplication. Three teammates had each "
            "written their own near-identical data tidier - about 90, 115 and "
            "99 lines, all doing basically the same job. Changing one rule "
            "meant editing three files and hoping you did not miss one. A bug "
            "fixed in one copy stayed alive in the others."
        ),
    },
    {
        "image": "slide_05.png",
        "title": "5 · Problem 2 — the rules were welded into the code",
        "notes": (
            "The second problem was rigidity. The code only accepted one exact "
            "format. The product name was hardcoded to one column, so the phone "
            "data - which uses a different column - jammed it. It also only "
            "matched exact spellings: 'Numeric' worked, lowercase 'numeric' "
            "silently dropped the whole column. A new product category meant "
            "editing source code, which breaks the project's core promise of "
            "working for any product."
        ),
    },
    {
        "image": "slide_06.png",
        "title": "6 · Problem 3 — one chef, no recipe",
        "notes": (
            "The third problem: only the original author could run it. No list "
            "of what to install, no setup guide, results piled up loose and got "
            "overwritten. A new teammate was stuck at step zero. This is exactly "
            "the P1 task 'get the tool running for everyone' - and it was not "
            "met yet."
        ),
    },
    {
        "image": "slide_07.png",
        "title": "7 · The fix, in one idea",
        "notes": (
            "The fix in one idea: let the program read a form instead of being "
            "rewritten. You describe each column once, right in the "
            "spreadsheet, and the code adapts itself to any product - no "
            "programmer needed."
        ),
    },
    {
        "image": "slide_08.png",
        "title": "8 · Improvement 1 — three tidiers became one (Module 1)",
        "notes": (
            "First improvement: the three tidiers became one shared engine. The "
            "two old files shrank to about a dozen lines each - they now just "
            "point at the engine. Fix it once, everyone benefits. This is the "
            "start of Module 1, the Universal Preprocessor from the Exposé."
        ),
    },
    {
        "image": "slide_09.png",
        "title": "9 · Improvement 2 — it now works for any product",
        "notes": (
            "Second improvement: configurable and forgiving. You fill in a "
            "form, not the code. It tolerates spelling variants, finds the "
            "product-name column by itself, reads human messiness like 54,999 "
            "or 61-70, fixes small mistakes like blanks and duplicate headers, "
            "and writes a plain 'receipt' of what it did to every column. This "
            "backs the P1 task of defining one unified data schema."
        ),
    },
    {
        "image": "slide_10.png",
        "title": "10 · Improvement 3 — one command, and you're running",
        "notes": (
            "Third improvement: anyone can run it. A single command - ./run.sh "
            "- installs everything, rebuilds all three datasets, and opens the "
            "dashboard. It ships with an ingredient list (exact versions), a "
            "recipe card (setup guide), tidy per-dataset folders, and a fill-in "
            "template with dropdowns. This delivers the P1 task 'get the tool "
            "running for everyone.'"
        ),
    },
    {
        "image": "slide_11.png",
        "title": "11 · Phase 1 scorecard — asked vs. done",
        "notes": (
            "Scored against the Exposé's Phase 1 task list. Three tasks done: "
            "the pipeline runs on all three datasets with check reports; the "
            "tool runs for everyone via one command; a unified data schema "
            "template exists. One bonus: Module 1, officially a Phase 2 task, "
            "was started early as the universal engine."
        ),
    },
    {
        "image": "slide_12.png",
        "title": "12 · Summary & next",
        "notes": (
            "To summarize in plain terms: one tidy engine instead of three, "
            "works on any product set up in Excel, and anyone can run it with "
            "one command. Next, in Phase 2: formally land Module 1, then build "
            "Module 2 (auto-generate the questionnaire) and Module 3 (the "
            "customer-importance math) on top of this foundation. Thank you."
        ),
    },
]


def build() -> Path:
    prs = Presentation()
    # 16:9 = 13.333 x 7.5 inches (matches the 1280x720 renders)
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)

    blank_layout = prs.slide_layouts[6]  # Blank

    for spec in SLIDES:
        image_path = HERE / spec["image"]
        if not image_path.exists():
            raise FileNotFoundError(f"Missing render: {image_path}")

        slide = prs.slides.add_slide(blank_layout)
        slide.shapes.add_picture(
            str(image_path),
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

    out_path = HERE / "P1_Foundation_Update.pptx"
    prs.save(str(out_path))
    return out_path


if __name__ == "__main__":
    path = build()
    print(f"Wrote {path}")
