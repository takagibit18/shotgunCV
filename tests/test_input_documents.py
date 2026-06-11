from __future__ import annotations

from pathlib import Path

import pytest

from shotguncv_core.cv_extraction import PageExtractionResult
from shotguncv_core.inputs import InputExtractionError, InputExtractionOptions, collect_input_documents


def test_collects_markdown_and_text_documents(tmp_path: Path) -> None:
    cv_path = tmp_path / "resume.md"
    jd_path = tmp_path / "jd.txt"
    cv_path.write_text("# Resume\n- Built LLM workflow tools", encoding="utf-8")
    jd_path.write_text("Title: Applied AI Engineer\nBody:\n- Build Python automation", encoding="utf-8")

    documents = collect_input_documents([cv_path, jd_path])

    assert [document.media_type for document in documents] == ["text/markdown", "text/plain"]
    assert documents[0].text.startswith("# Resume")
    assert documents[1].source_type == "file"
    assert documents[1].extraction_status == "extracted"


def test_collects_text_from_pdf_document(tmp_path: Path) -> None:
    pdf_path = tmp_path / "resume.pdf"
    pdf_path.write_bytes(
        b"%PDF-1.4\n"
        b"1 0 obj <<>> endobj\n"
        b"2 0 obj << /Length 44 >> stream\n"
        b"BT /F1 12 Tf 72 720 Td (PDF Resume Evidence) Tj ET\n"
        b"endstream endobj\n"
        b"trailer <<>>\n%%EOF\n"
    )

    documents = collect_input_documents([pdf_path])

    assert documents[0].media_type == "application/pdf"
    assert "PDF Resume Evidence" in documents[0].text


def test_pdf_with_low_quality_text_uses_ocr_fallback(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    pdf_path = tmp_path / "resume.pdf"
    page_image = tmp_path / "resume-page-1.png"
    pdf_path.write_bytes(b"%PDF-1.4 scanned")
    page_image.write_bytes(b"image")
    # Return one page with empty native text → triggers full-document OCR fallback
    empty_page = PageExtractionResult(
        page=1, text="", source="native", quality_score=0.0, ocr_used=False,
        native_text="", ocr_text="", native_score=0.0, ocr_score=0.0, ocr_triggered=False,
    )
    monkeypatch.setattr("shotguncv_core.inputs._extract_pdf_pages_native", lambda path: [empty_page])
    monkeypatch.setattr("shotguncv_core.inputs._render_pdf_pages_to_images", lambda path: [page_image])
    monkeypatch.setattr(
        "shotguncv_core.inputs._extract_image_text_with_ocr",
        lambda path, languages, **kw: "OCR PDF Resume Text",
    )

    documents = collect_input_documents([pdf_path], options=InputExtractionOptions(vision_enabled=False))

    assert documents[0].media_type == "application/pdf"
    assert documents[0].text == "OCR PDF Resume Text"
    assert documents[0].extraction_status == "ocr"
    assert documents[0].extraction_provider == "local_ocr"
    assert "PDF text extraction" in documents[0].extraction_error


def test_pdf_with_fragmented_junk_text_uses_ocr_fallback(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    pdf_path = tmp_path / "resume.pdf"
    page_image = tmp_path / "resume-page-1.png"
    pdf_path.write_bytes(b"%PDF-1.4 encoded")
    page_image.write_bytes(b"image")
    junk_text = (
        "> analyze -\n> execute_tools -\n> format -\n submit_review / submit_debug \n#\n$%\n 3 \n&'\n"
        "\\001\\002\\003\\004\\005\\006\\007985\\010\\011\\012\\013\\014\\015\\006\\016\\017\\020\\007\\021"
    )
    # Return one page with junk text (low quality) → triggers page-level OCR
    junk_page = PageExtractionResult(
        page=1, text=junk_text, source="native", quality_score=0.05, ocr_used=False,
        native_text=junk_text, ocr_text="", native_score=0.05, ocr_score=0.0, ocr_triggered=False,
    )
    monkeypatch.setattr("shotguncv_core.inputs._extract_pdf_pages_native", lambda path: [junk_page])
    monkeypatch.setattr("shotguncv_core.inputs._render_single_pdf_page", lambda path, page_num: page_image)
    monkeypatch.setattr(
        "shotguncv_core.inputs._extract_image_text_with_ocr",
        lambda path, languages, **kw: "Bachelor degree in Computer Science. Built Python Agent systems.",
    )

    documents = collect_input_documents([pdf_path], options=InputExtractionOptions(vision_enabled=False))

    assert documents[0].text.startswith("Bachelor degree")
    assert documents[0].extraction_status == "ocr"


def test_pdf_with_empty_ocr_uses_vision_fallback(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    pdf_path = tmp_path / "resume.pdf"
    page_image = tmp_path / "resume-page-1.png"
    pdf_path.write_bytes(b"%PDF-1.4 scanned")
    page_image.write_bytes(b"image")
    # All native pages empty → triggers full-document OCR → falls through to vision
    empty_page = PageExtractionResult(
        page=1, text="", source="native", quality_score=0.0, ocr_used=False,
        native_text="", ocr_text="", native_score=0.0, ocr_score=0.0, ocr_triggered=False,
    )
    monkeypatch.setattr("shotguncv_core.inputs._extract_pdf_pages_native", lambda path: [empty_page])
    monkeypatch.setattr("shotguncv_core.inputs._render_pdf_pages_to_images", lambda path: [page_image])
    monkeypatch.setattr("shotguncv_core.inputs._extract_image_text_with_ocr", lambda path, languages, **kw: "")
    monkeypatch.setattr(
        "shotguncv_core.inputs._extract_image_text_with_vision",
        lambda path, options, ocr_error: "Vision PDF Resume Text",
    )

    documents = collect_input_documents([pdf_path], options=InputExtractionOptions(vision_enabled=True))

    assert documents[0].text == "Vision PDF Resume Text"
    assert documents[0].extraction_status == "vision"
    assert documents[0].extraction_provider == "openai_vision"


def test_pdf_fallback_failure_records_unparseable_guidance(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    pdf_path = tmp_path / "resume.pdf"
    page_image = tmp_path / "resume-page-1.png"
    pdf_path.write_bytes(b"%PDF-1.4 scanned")
    page_image.write_bytes(b"image")
    # All native pages empty → triggers full-document OCR → OCR empty → vision disabled → unparseable
    empty_page = PageExtractionResult(
        page=1, text="", source="native", quality_score=0.0, ocr_used=False,
        native_text="", ocr_text="", native_score=0.0, ocr_score=0.0, ocr_triggered=False,
    )
    monkeypatch.setattr("shotguncv_core.inputs._extract_pdf_pages_native", lambda path: [empty_page])
    monkeypatch.setattr("shotguncv_core.inputs._render_pdf_pages_to_images", lambda path: [page_image])
    monkeypatch.setattr("shotguncv_core.inputs._extract_image_text_with_ocr", lambda path, languages, **kw: "")

    documents = collect_input_documents([pdf_path], options=InputExtractionOptions(vision_enabled=False))

    assert documents[0].media_type == "application/pdf"
    assert documents[0].extraction_status == "unparseable"
    assert "PDF text extraction" in documents[0].extraction_error
    assert "OCR returned empty text" in documents[0].extraction_error
    assert "Vision fallback is disabled" in documents[0].extraction_error


def test_collects_image_with_text_sidecar(tmp_path: Path) -> None:
    image_path = tmp_path / "jd.png"
    sidecar_path = tmp_path / "jd.md"
    image_path.write_bytes(b"not a real image")
    sidecar_path.write_text("Title: AI PM\nBody:\n- Own LLM product metrics", encoding="utf-8")

    documents = collect_input_documents([image_path])

    assert documents[0].media_type == "image/png"
    assert documents[0].extraction_status == "sidecar"
    assert documents[0].text.startswith("Title: AI PM")


def test_image_without_sidecar_records_unparseable_document(tmp_path: Path) -> None:
    image_path = tmp_path / "resume.jpg"
    image_path.write_bytes(b"not a real image")

    documents = collect_input_documents([image_path], options=InputExtractionOptions(vision_enabled=False))

    assert documents[0].extraction_status == "unparseable"
    assert documents[0].text == ""
    assert "OCR" in documents[0].extraction_error or "Tesseract" in documents[0].extraction_error


def test_directory_collection_keeps_unparseable_image_without_blocking_valid_inputs(tmp_path: Path) -> None:
    input_dir = tmp_path / "inputs"
    input_dir.mkdir()
    (input_dir / "resume.md").write_text("- Built workflow tools", encoding="utf-8")
    (input_dir / "scan.jpg").write_bytes(b"not a real image")

    documents = collect_input_documents([input_dir], options=InputExtractionOptions(vision_enabled=False))

    assert [Path(document.source_value).name for document in documents] == ["resume.md", "scan.jpg"]
    assert documents[0].extraction_status == "extracted"
    assert documents[1].extraction_status == "unparseable"
    assert documents[1].text == ""
    assert documents[1].extraction_error


def test_directory_collection_filters_supported_inputs(tmp_path: Path) -> None:
    input_dir = tmp_path / "inputs"
    hidden_dir = input_dir / ".next"
    hidden_dir.mkdir(parents=True)
    (input_dir / "a.md").write_text("A", encoding="utf-8")
    (input_dir / "b.txt").write_text("B", encoding="utf-8")
    (input_dir / "ignored.docx").write_text("ignored", encoding="utf-8")
    (hidden_dir / "hidden.md").write_text("hidden", encoding="utf-8")

    documents = collect_input_documents([input_dir])

    assert [Path(document.source_value).name for document in documents] == ["a.md", "b.txt"]


def test_directory_collection_does_not_duplicate_image_sidecars(tmp_path: Path) -> None:
    input_dir = tmp_path / "inputs"
    input_dir.mkdir()
    (input_dir / "jd.png").write_bytes(b"not a real image")
    (input_dir / "jd.md").write_text("Title: AI PM\nBody:\n- Own LLM product metrics", encoding="utf-8")

    documents = collect_input_documents([input_dir])

    assert len(documents) == 1
    assert Path(documents[0].source_value).name == "jd.png"
    assert documents[0].extraction_status == "sidecar"


def test_image_ocr_success_records_provider(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    image_path = tmp_path / "resume.png"
    image_path.write_bytes(b"image")
    monkeypatch.setattr("shotguncv_core.inputs._extract_image_text_with_ocr", lambda path, languages, **kw: "OCR Resume Text")

    documents = collect_input_documents([image_path], options=InputExtractionOptions(vision_enabled=False))

    assert documents[0].text == "OCR Resume Text"
    assert documents[0].extraction_status == "ocr"
    assert documents[0].extraction_provider == "local_ocr"
    assert documents[0].extraction_error == ""


def test_image_ocr_text_is_cleaned_before_ingest(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    image_path = tmp_path / "jd.png"
    image_path.write_bytes(b"image")
    monkeypatch.setattr(
        "shotguncv_core.inputs._extract_image_text_with_ocr",
        lambda path, languages, **kw: (
            "岗 位 职 责\n"
            "- 负 责 L L M 应 用 开 发 ， 建 设 R A G 评 估 流 程\n"
            "@@@ ###\n"
            "任 职 要 求\n"
            "- 熟 悉 P y t h o n 和 LangGraph"
        ),
    )

    documents = collect_input_documents([image_path], options=InputExtractionOptions(vision_enabled=False))

    assert "岗位职责" in documents[0].text
    assert "负责 LLM 应用开发" in documents[0].text
    assert "RAG 评估流程" in documents[0].text
    assert "Python 和 LangGraph" in documents[0].text
    assert "@@@ ###" not in documents[0].text


def test_low_quality_image_ocr_uses_vision_fallback(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    image_path = tmp_path / "jd.png"
    image_path.write_bytes(b"image")
    monkeypatch.setattr(
        "shotguncv_core.inputs._extract_image_text_with_ocr",
        lambda path, languages, **kw: "岗 位 职 责\n职 位 标 签\n教 育\n福 利\n@@@ ###",
    )
    monkeypatch.setattr(
        "shotguncv_core.inputs._extract_image_text_with_vision",
        lambda path, options, ocr_error: "岗位职责\n- 负责 LLM 应用开发\n任职要求\n- 熟悉 Python 和 RAG",
    )

    documents = collect_input_documents([image_path], options=InputExtractionOptions(vision_enabled=True))

    assert documents[0].text.startswith("岗位职责")
    assert documents[0].extraction_status == "vision"
    assert documents[0].extraction_provider == "openai_vision"
    assert "OCR text quality is too low" in documents[0].extraction_error


def test_low_quality_image_ocr_without_vision_is_unparseable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    image_path = tmp_path / "jd.png"
    image_path.write_bytes(b"image")
    monkeypatch.setattr(
        "shotguncv_core.inputs._extract_image_text_with_ocr",
        lambda path, languages, **kw: "岗 位 职 责\n职 位 标 签\n教 育\n福 利\n@@@ ###",
    )

    documents = collect_input_documents([image_path], options=InputExtractionOptions(vision_enabled=False))

    assert documents[0].text == ""
    assert documents[0].extraction_status == "unparseable"
    assert "OCR text quality is too low" in documents[0].extraction_error


def test_image_ocr_quality_ignores_blank_raw_lines(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    image_path = tmp_path / "jd.png"
    image_path.write_bytes(b"image")
    monkeypatch.setattr(
        "shotguncv_core.inputs._extract_image_text_with_ocr",
        lambda path, languages, **kw: "\n\n岗位职责\n\n- 负责 Agent 框架开发\n\n任职要求\n- 熟悉 Python 和 RAG\n\n",
    )

    documents = collect_input_documents([image_path], options=InputExtractionOptions(vision_enabled=False))

    assert documents[0].extraction_status == "ocr"
    assert "负责 Agent 框架开发" in documents[0].text


def test_image_ocr_normalizes_ai_confusions_and_filters_job_metadata(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    image_path = tmp_path / "jd.png"
    image_path.write_bytes(b"image")
    monkeypatch.setattr(
        "shotguncv_core.inputs._extract_image_text_with_ocr",
        lambda path, languages, **kw: (
            "Al 应用工程师\n"
            "Shenzhen | Intelligent manufacturing | Industrial automation | 26 届国内春招\n"
            "Published 16d ago\n"
            "USD 160K-300K\n"
            "北京 、 上海校拙 | 实习研发 - 后端开发 | 2027 届实习生招聘\n"
            "- 关注 AGI 前沿技术进展 , 技术驿动产品与体验进步\n"
            "- 开发全球领先的 Al Agent / Al APP\n"
            "- 探索并整合主流 Al 技术 ( 如大模型 、 图像识别 ) 到具体场景"
        ),
    )

    documents = collect_input_documents([image_path], options=InputExtractionOptions(vision_enabled=False))

    text = documents[0].text
    assert "AI 应用工程师" in text
    assert "技术驱动产品与体验进步" in text
    assert "AI Agent / AI APP" in text
    assert "主流 AI 技术" in text
    assert "Published" not in text
    assert "USD 160K-300K" not in text
    assert "26 届国内春招" not in text
    assert "校拙" not in text
    assert "2027 届实习生招聘" not in text


def test_image_ocr_repairs_single_letter_ai_and_common_chinese_typos(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    image_path = tmp_path / "jd.png"
    image_path.write_bytes(b"image")
    monkeypatch.setattr(
        "shotguncv_core.inputs._extract_image_text_with_ocr",
        lambda path, languages, **kw: (
            "岗位职责\n"
            "¢ Architect and develop scalable Al systems\n"
            "- 为其他产品或运营团队提供 A 赋能 : 开发内部 A 工具 、 技术接口或解决方案\n"
            "- 跟除新技术趋势 , 探索能提升团队效率的 A 方案\n"
            "- 跟院 Agent 抚术前沿进展 , 提出创新解决方案\n"
            "[ 半互联网 / 工业\n"
            "动化"
        ),
    )

    documents = collect_input_documents([image_path], options=InputExtractionOptions(vision_enabled=False))

    text = documents[0].text
    assert "- Architect and develop scalable AI systems" in text
    assert "AI 赋能" in text
    assert "内部 AI 工具" in text
    assert "AI 方案" in text
    assert "跟踪 Agent 技术前沿进展" in text
    assert "半互联网" not in text
    assert "工业 / 动化" not in text


def test_image_empty_ocr_uses_vision_fallback(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    image_path = tmp_path / "jd.png"
    image_path.write_bytes(b"image")
    monkeypatch.setattr("shotguncv_core.inputs._extract_image_text_with_ocr", lambda path, languages, **kw: "")
    monkeypatch.setattr(
        "shotguncv_core.inputs._extract_image_text_with_vision",
        lambda path, options, ocr_error: "Vision JD Text",
    )

    documents = collect_input_documents([image_path], options=InputExtractionOptions(vision_enabled=True))

    assert documents[0].text == "Vision JD Text"
    assert documents[0].extraction_status == "vision"
    assert documents[0].extraction_provider == "openai_vision"


def test_image_failure_reports_ocr_and_vision_guidance(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    image_path = tmp_path / "resume.png"
    image_path.write_bytes(b"image")
    monkeypatch.setattr(
        "shotguncv_core.inputs._extract_image_text_with_ocr",
        lambda path, languages, **kw: (_ for _ in ()).throw(RuntimeError("tesseract missing")),
    )
    monkeypatch.setattr(
        "shotguncv_core.inputs._extract_image_text_with_vision",
        lambda path, options, ocr_error: (_ for _ in ()).throw(RuntimeError("missing OPENAI_API_KEY")),
    )

    documents = collect_input_documents([image_path], options=InputExtractionOptions(vision_enabled=True))

    message = documents[0].extraction_error
    assert documents[0].extraction_status == "unparseable"
    assert str(image_path) in message
    assert "tesseract missing" in message
    assert "missing OPENAI_API_KEY" in message
    assert "Install Tesseract" in message


def test_no_vision_fallback_does_not_call_vision(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    image_path = tmp_path / "resume.png"
    image_path.write_bytes(b"image")
    monkeypatch.setattr("shotguncv_core.inputs._extract_image_text_with_ocr", lambda path, languages, **kw: "")

    def _unexpected_vision_call(path, options, ocr_error):  # type: ignore[no-untyped-def]
        raise AssertionError("vision fallback should be disabled")

    monkeypatch.setattr("shotguncv_core.inputs._extract_image_text_with_vision", _unexpected_vision_call)

    documents = collect_input_documents([image_path], options=InputExtractionOptions(vision_enabled=False))

    assert documents[0].extraction_status == "unparseable"
    assert "Vision fallback is disabled" in documents[0].extraction_error
