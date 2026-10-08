from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = REPO_ROOT / "assets" / "pubmed_ai_screening_output_prompt.md"
WORKFLOW_DOC = REPO_ROOT / "SKILL.md"
STANDARD_OUTPUT_FILES = (
    "SEARCH_SUMMARY.md",
    "SCREENING_TABLE.md",
    "DEEP_READING_SELECTION.md",
    "ABSTRACT_REVIEW.md",
    "FULL_TEXT_READING_PLAN.md",
)


def test_pubmed_ai_screening_output_prompt_defines_standard_package() -> None:
    text = TEMPLATE.read_text(encoding="utf-8")

    assert "downloadable zip package" in text
    assert "default zip package must contain exactly these five Markdown files" in text
    for filename in STANDARD_OUTPUT_FILES:
        assert f"`{filename}`" in text

    assert "paper_note_drafts/*.md" in text
    assert "not final `Papers/` notes" in text


def test_pubmed_ai_screening_output_prompt_uses_strict_read_depth_language() -> None:
    text = TEMPLATE.read_text(encoding="utf-8")

    assert "`pubmed_verified`" in text
    assert "This does not mean the abstract or full text was read." in text
    assert "`abstract_reviewed`" in text
    assert "abstract was actually available" in text
    assert "`full_text_reviewed`" in text
    assert "only when the full text was actually read" in text
    assert "Do not infer or assign `full_text_reviewed`" in text
    assert "Do not claim figure-level evidence unless figures were actually reviewed." in text
    assert "Do not invent citations, PMIDs, DOIs, authors, titles, abstracts" in text


def test_pubmed_ai_screening_output_prompt_blocks_repository_side_effects() -> None:
    text = TEMPLATE.read_text(encoding="utf-8")

    blocked_targets = (
        "`Papers/`",
        "Bookends",
        "PDFs",
        "raw data",
        "external AI APIs",
        "repository files outside the returned downloadable output package",
    )
    for target in blocked_targets:
        assert target in text

    assert "Do not write to, modify, or claim to update `Papers/`." in text
    assert "Do not call external AI APIs." in text


def test_pubmed_literature_workflow_documents_output_prompt_use() -> None:
    text = WORKFLOW_DOC.read_text(encoding="utf-8")

    assert "`assets/pubmed_ai_screening_output_prompt.md`" in text
    assert "`ABSTRACT_SCREENING_PACKET.md` or `pubmed_ai_handoff.zip`" in text
    assert "return a downloadable zip when supported" in text
    assert "review the returned zip or extracted Markdown files manually" in text
    assert "not final paper notes" in text
    assert "`full_text_reviewed` is allowed only after actual full-text reading" in text
