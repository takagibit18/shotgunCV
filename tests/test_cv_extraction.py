from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from shotguncv_core.cv_extraction import (
    CvExtractionResult,
    ExtractionBlock,
    PageExtractionResult,
    TechCorrection,
    build_blocks_from_text,
    decide_page_source,
    identify_cv_sections,
    merge_page_results_to_blocks,
    normalize_tech_stack,
    post_process_cv_blocks,
    run_cv_extraction_pipeline,
    score_text_quality,
)


# ---------------------------------------------------------------------------
# score_text_quality
# ---------------------------------------------------------------------------


def test_score_empty_text_is_zero() -> None:
    assert score_text_quality("") == 0.0
    assert score_text_quality("   ") == 0.0


def test_score_clean_text_is_high() -> None:
    text = "Bachelor of Computer Science at Central University. Built Python agent systems."
    score = score_text_quality(text)
    assert score > 0.5, f"Expected > 0.5, got {score}"


def test_score_text_with_control_chars_is_low() -> None:
    text = "Resume\x00\x01\x02\x03\x04\x05\x06 text"
    score = score_text_quality(text)
    assert score < 0.85, f"Expected < 0.85 with control chars, got {score}"


def test_score_text_with_replacement_chars_reduces_quality() -> None:
    clean = "名称计算机语言编程系统设计算法"
    corrupted = "名�称�计�算�机�语�言�编�程�系�统�设�计�算�法"
    clean_score = score_text_quality(clean)
    corrupted_score = score_text_quality(corrupted)
    assert corrupted_score < clean_score, f"Corrupted ({corrupted_score}) should be < clean ({clean_score})"


def test_score_good_text_beats_bad_text() -> None:
    good = "Python FastAPI Docker PostgreSQL"
    bad = "\x00\x01\x02\x03\x04\x05"
    assert score_text_quality(good) > score_text_quality(bad)


def test_score_normal_chinese_text_is_high() -> None:
    """Normal Chinese text with common bigrams should score well."""
    text = (
        "教育经历 中央民族大学 计算机科学与技术 本科 "
        "项目经历 MergeWarden 代码审查与调试 Agent "
        "专业技能 Python 工程化 使用 Python 异步编程"
    )
    score = score_text_quality(text)
    assert score > 0.70, f"Normal Chinese text should score > 0.70, got {score}"


def test_score_cjk_semantic_corruption_is_low() -> None:
    """CMap-corrupted CJK text with scrambled bigrams should score lower."""
    # Simulating CMap corruption: valid CJK chars but scrambled glyph mapping
    corrupted = (
        "计鲸机吴学与技术本租中央民旋大学自然浩言处途"
        "项且经历专亚技熊实习工作背景教肯经万自我评估"
        "求积意向计算杨科字与人工资能代玛审查与测诗"
        "软伟工程学乎统架构设什开发运绯团队合竹构通"
        "MergeWarden Code Review Agent Python FastAPI Docker"
    )
    clean = (
        "计算机科学与技术本科中央民族大学自然语言处理"
        "项目经历专业技能实习工作背景教育经历自我评估"
        "求职意向计算机科学与人工智能代码审查与测试"
        "软件工程系统架构设计开发运维团队合作沟通"
        "MergeWarden Code Review Agent Python FastAPI Docker"
    )
    corrupted_score = score_text_quality(corrupted)
    clean_score = score_text_quality(clean)
    assert corrupted_score < clean_score, (
        f"Corrupted CJK ({corrupted_score}) should be < clean CJK ({clean_score})"
    )


def test_cjk_bigram_hit_rate_normal() -> None:
    from shotguncv_core.cv_extraction import _cjk_bigram_hit_rate

    text = "中央民族大学计算机科学与技术本科教育经历项目经历专业技能Python工程化"
    hit = _cjk_bigram_hit_rate(text)
    assert hit > 0.15, f"Normal Chinese hit rate should be > 0.15, got {hit}"


def test_cjk_bigram_hit_rate_corrupted() -> None:
    from shotguncv_core.cv_extraction import _cjk_bigram_hit_rate

    # Characters with scrambled neighbors — 30+ CJK chars needed to trigger check
    corrupted = (
        "计鲸机吴学与技术本租中央民旋大学自然浩言处途"
        "项且经历专亚技熊实习工作背景教肯经万自我评估"
        "求积意向计算杨科字与人工资能代玛审查与测诗"
        "软伟工程学乎统架构设什开发运绯团队合竹构通"
    )
    hit = _cjk_bigram_hit_rate(corrupted)
    assert hit < 0.30, f"Corrupted CJK hit rate should be < 0.30, got {hit}"


def test_cjk_bigram_hit_rate_too_short_returns_1() -> None:
    from shotguncv_core.cv_extraction import _cjk_bigram_hit_rate

    short = "计算机"  # Only 3 CJK chars, < 30 minimum
    hit = _cjk_bigram_hit_rate(short)
    assert hit == 1.0, f"Short text should return 1.0 (not judged), got {hit}"


# ---------------------------------------------------------------------------
# Page-level fallback (decide_page_source)
# ---------------------------------------------------------------------------


def test_native_high_quality_no_ocr_triggered() -> None:
    """Native text high quality → no OCR needed."""
    native_text = "Education\nBachelor of Computer Science\nSkills\nPython, FastAPI, Docker"
    result = decide_page_source(
        native_text=native_text,
        native_score=0.70,
        ocr_text="",
        ocr_score=0.0,
    )
    assert result.source == "native"
    assert result.ocr_used is False
    assert result.ocr_triggered is False


def test_native_low_quality_triggers_ocr_and_uses_ocr_when_better() -> None:
    """Native text low quality + OCR better → use OCR."""
    native_text = "\x00\x01\x02\x03"
    ocr_text = "Education Bachelor of Computer Science"
    result = decide_page_source(
        native_text=native_text,
        native_score=0.10,
        ocr_text=ocr_text,
        ocr_score=0.75,
    )
    assert result.ocr_triggered is True
    assert result.ocr_used is True
    assert result.source == "ocr"
    assert result.text == ocr_text


def test_native_low_quality_ocr_not_better_enough_keeps_native() -> None:
    """OCR triggered but not better enough → keep native."""
    native_text = "Some garbled text"
    ocr_text = "Slightly better garbled"
    result = decide_page_source(
        native_text=native_text,
        native_score=0.30,
        ocr_text=ocr_text,
        ocr_score=0.35,
    )
    assert result.ocr_triggered is True
    assert result.ocr_used is False
    assert result.source == "native"


# ---------------------------------------------------------------------------
# ExtractionBlock
# ---------------------------------------------------------------------------


def test_build_blocks_has_required_fields() -> None:
    text = "## Skills\nPython, FastAPI\n\n## Education\nBachelor degree"
    blocks = build_blocks_from_text(text, page=1, source="native", quality_score=0.9)
    for block in blocks:
        assert block.text
        assert block.page == 1
        assert block.source == "native"
        assert isinstance(block.quality_score, float)
        assert block.block_type in ("heading", "paragraph", "unknown")


def test_build_blocks_classifies_headings() -> None:
    text = "专业技能\nPython, FastAPI, Docker, LangGraph"
    blocks = build_blocks_from_text(text, page=1, source="native", quality_score=0.9)
    headings = [b for b in blocks if b.block_type == "heading"]
    assert any("专业技能" in h.text for h in headings)


def test_build_blocks_merges_fragmentary_lines() -> None:
    text = "A\nB\nC\nLong enough text here with actual content"
    blocks = build_blocks_from_text(text, page=1, source="native", quality_score=0.9)
    # Very short lines "A", "B", "C" should be merged rather than standalone blocks
    assert len(blocks) <= 3  # Not 4 individual blocks


# ---------------------------------------------------------------------------
# CV Section identification
# ---------------------------------------------------------------------------


def make_test_blocks() -> list[ExtractionBlock]:
    lines = [
        ("基本信息", "heading"),
        ("中央民族大学 计算机科学与技术", "paragraph"),
        ("专业技能", "heading"),
        ("Python, FastAPI, Docker, LangGraph", "paragraph"),
        ("项目经历", "heading"),
        ("MergeWarden — Code review agent", "paragraph"),
        ("ShotgunCV — Resume ops pipeline", "paragraph"),
    ]
    blocks: list[ExtractionBlock] = []
    for text, btype in lines:
        blocks.append(
            ExtractionBlock(
                text=text, page=1, source="native", quality_score=0.9,
                block_type=btype,
            )
        )
    return blocks


def test_section_heading_matches_aliases() -> None:
    blocks = make_test_blocks()
    result = identify_cv_sections(blocks)
    sections_found = {b.section for b in result if b.section is not None}
    assert "basic_info" in sections_found
    assert "skills" in sections_found
    assert "projects" in sections_found


def test_heading_following_blocks_inherit_section() -> None:
    blocks = make_test_blocks()
    result = identify_cv_sections(blocks)
    # Block 3: "Python, FastAPI, Docker, LangGraph" — should inherit "skills"
    skills_paragraphs = [
        b for b in result
        if b.section == "skills" and b.block_type != "heading"
    ]
    assert len(skills_paragraphs) >= 1
    assert any("Python" in b.text for b in skills_paragraphs)


def test_unknown_heading_resets_section_to_none() -> None:
    blocks = [
        ExtractionBlock(text="专业技能", page=1, source="native", quality_score=0.9, block_type="heading"),
        ExtractionBlock(text="Python", page=1, source="native", quality_score=0.9, block_type="paragraph"),
        ExtractionBlock(text="某个不认识的标题", page=1, source="native", quality_score=0.9, block_type="heading"),
        ExtractionBlock(text="Next line should be None", page=1, source="native", quality_score=0.9, block_type="paragraph"),
    ]
    result = identify_cv_sections(blocks)
    assert result[0].section == "skills"
    assert result[1].section == "skills"
    assert result[2].section is None  # unknown heading
    assert result[3].section is None  # inherited None


# ---------------------------------------------------------------------------
# Tech stack normalization
# ---------------------------------------------------------------------------


def test_fastapi_ocr_fix() -> None:
    block = ExtractionBlock(
        text="FastAPl, Docker, PostgreSQI", page=1, source="ocr",
        quality_score=0.7, block_type="paragraph", section="skills",
    )
    _, corrections, skills = normalize_tech_stack([block])
    norms = {c.normalized for c in corrections}
    assert "FastAPI" in norms
    assert "PostgreSQL" in norms


def test_postgresql_ocr_fix() -> None:
    block = ExtractionBlock(
        text="PostgreSQI and TypeScrlpt", page=1, source="ocr",
        quality_score=0.7, block_type="paragraph", section="skills",
    )
    _, corrections, skills = normalize_tech_stack([block])
    norm_map = {c.original.lower(): c.normalized for c in corrections}
    assert norm_map.get("postgresqi") == "PostgreSQL"
    assert norm_map.get("typescrlpt") == "TypeScript"


def test_corrections_have_metadata() -> None:
    block = ExtractionBlock(
        text="FastAPl, LangGrapn, Qdrani", page=2, source="ocr",
        quality_score=0.7, block_type="paragraph", section="skills",
    )
    _, corrections, _ = normalize_tech_stack([block])
    for c in corrections:
        assert c.original
        assert c.normalized
        assert c.confidence >= 0.70, f"Confidence too low for {c.original}"
        assert c.block_index == 0
        assert c.page == 2


def test_confidence_below_threshold_not_applied() -> None:
    # A token that won't match anything well
    block = ExtractionBlock(
        text="XyzzyUnknownToken", page=1, source="native",
        quality_score=0.9, block_type="paragraph", section="skills",
    )
    _, corrections, _ = normalize_tech_stack([block])
    assert len(corrections) == 0


def test_known_tech_terms_detected() -> None:
    block = ExtractionBlock(
        text="Python FastAPI Docker Kubernetes LangGraph RAG PyTorch",
        page=1, source="native", quality_score=0.9,
        block_type="paragraph", section="skills",
    )
    _, _, skills = normalize_tech_stack([block])
    assert "Python" in skills
    assert "FastAPI" in skills
    assert "Docker" in skills
    assert "Kubernetes" in skills
    assert "LangGraph" in skills


def test_tech_normalization_only_in_relevant_sections() -> None:
    """Tech normalization should only apply to skills/projects/experience sections."""
    edu_block = ExtractionBlock(
        text="Studied FastAPI and Python at university",
        page=1, source="native", quality_score=0.9,
        block_type="paragraph", section="education",
    )
    _, corrections, _ = normalize_tech_stack([edu_block])
    # education section — should NOT trigger tech corrections
    assert len(corrections) == 0


# ---------------------------------------------------------------------------
# Integration: full pipeline
# ---------------------------------------------------------------------------


def test_merge_page_results_to_blocks() -> None:
    pages = [
        PageExtractionResult(
            page=1, text="专业技能\nPython\n\n项目经历\nMergeWarden",
            source="native", quality_score=0.9, ocr_used=False,
            native_text="专业技能\nPython\n\n项目经历\nMergeWarden",
            ocr_text="", native_score=0.9, ocr_score=0.0, ocr_triggered=False,
        ),
    ]
    blocks = merge_page_results_to_blocks(pages)
    assert len(blocks) >= 1
    for b in blocks:
        assert b.page == 1
        assert b.source == "native"


def test_run_cv_extraction_pipeline() -> None:
    pages = [
        PageExtractionResult(
            page=1, text="专业技能\nPython, FastAPI\n\n项目经历\nMergeWarden Agent",
            source="native", quality_score=0.85, ocr_used=False,
            native_text="专业技能\nPython, FastAPI\n\n项目经历\nMergeWarden Agent",
            ocr_text="", native_score=0.85, ocr_score=0.0, ocr_triggered=False,
        ),
    ]
    result = run_cv_extraction_pipeline(pages)
    assert isinstance(result, CvExtractionResult)
    assert len(result.blocks) >= 1
    assert len(result.pages) == 1
    assert "Python" in result.normalized_skills or "FastAPI" in result.normalized_skills
    assert result.plain_text
    assert result.markdown


def test_cv_extraction_result_to_plain_serializable() -> None:
    pages = [
        PageExtractionResult(
            page=1, text="Skills\nPython", source="native", quality_score=0.9,
            ocr_used=False, native_text="Skills\nPython", ocr_text="",
            native_score=0.9, ocr_score=0.0, ocr_triggered=False,
        ),
    ]
    result = run_cv_extraction_pipeline(pages)
    plain = result.to_plain()
    assert "blocks" in plain
    assert "pages" in plain
    assert "corrections" in plain
    assert "normalized_skills" in plain
    assert plain["pages"][0]["source"] == "native"


# ---------------------------------------------------------------------------
# Backward compatibility
# ---------------------------------------------------------------------------


def test_cv_extraction_result_plain_text() -> None:
    pages = [
        PageExtractionResult(
            page=1, text="Line 1\nLine 2", source="native", quality_score=0.9,
            ocr_used=False, native_text="Line 1\nLine 2", ocr_text="",
            native_score=0.9, ocr_score=0.0, ocr_triggered=False,
        ),
    ]
    result = run_cv_extraction_pipeline(pages)
    text = result.plain_text
    assert "Line 1" in text
    assert "Line 2" in text


def test_page_extraction_result_quality_score_threshold() -> None:
    """Pages with native_score >= 0.35 should NOT trigger OCR."""
    result = decide_page_source(
        native_text="Good text here", native_score=0.45,
        ocr_text="", ocr_score=0.0,
    )
    assert result.ocr_triggered is False
    assert result.ocr_used is False
    assert result.source == "native"
