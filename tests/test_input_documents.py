from __future__ import annotations

from pathlib import Path

import pytest

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


def test_collects_image_with_text_sidecar(tmp_path: Path) -> None:
    image_path = tmp_path / "jd.png"
    sidecar_path = tmp_path / "jd.md"
    image_path.write_bytes(b"not a real image")
    sidecar_path.write_text("Title: AI PM\nBody:\n- Own LLM product metrics", encoding="utf-8")

    documents = collect_input_documents([image_path])

    assert documents[0].media_type == "image/png"
    assert documents[0].extraction_status == "sidecar"
    assert documents[0].text.startswith("Title: AI PM")


def test_image_without_sidecar_raises_actionable_error(tmp_path: Path) -> None:
    image_path = tmp_path / "resume.jpg"
    image_path.write_bytes(b"not a real image")

    with pytest.raises(InputExtractionError, match="Tesseract"):
        collect_input_documents([image_path], options=InputExtractionOptions(vision_enabled=False))


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
    monkeypatch.setattr("shotguncv_core.inputs._extract_image_text_with_ocr", lambda path, languages: "OCR Resume Text")

    documents = collect_input_documents([image_path], options=InputExtractionOptions(vision_enabled=False))

    assert documents[0].text == "OCR Resume Text"
    assert documents[0].extraction_status == "ocr"
    assert documents[0].extraction_provider == "local_ocr"
    assert documents[0].extraction_error == ""


def test_image_empty_ocr_uses_vision_fallback(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    image_path = tmp_path / "jd.png"
    image_path.write_bytes(b"image")
    monkeypatch.setattr("shotguncv_core.inputs._extract_image_text_with_ocr", lambda path, languages: "")
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
        lambda path, languages: (_ for _ in ()).throw(RuntimeError("tesseract missing")),
    )
    monkeypatch.setattr(
        "shotguncv_core.inputs._extract_image_text_with_vision",
        lambda path, options, ocr_error: (_ for _ in ()).throw(RuntimeError("missing OPENAI_API_KEY")),
    )

    with pytest.raises(InputExtractionError) as excinfo:
        collect_input_documents([image_path], options=InputExtractionOptions(vision_enabled=True))

    message = str(excinfo.value)
    assert str(image_path) in message
    assert "tesseract missing" in message
    assert "missing OPENAI_API_KEY" in message
    assert "Install Tesseract" in message


def test_no_vision_fallback_does_not_call_vision(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    image_path = tmp_path / "resume.png"
    image_path.write_bytes(b"image")
    monkeypatch.setattr("shotguncv_core.inputs._extract_image_text_with_ocr", lambda path, languages: "")

    def _unexpected_vision_call(path, options, ocr_error):  # type: ignore[no-untyped-def]
        raise AssertionError("vision fallback should be disabled")

    monkeypatch.setattr("shotguncv_core.inputs._extract_image_text_with_vision", _unexpected_vision_call)

    with pytest.raises(InputExtractionError, match="Vision fallback is disabled"):
        collect_input_documents([image_path], options=InputExtractionOptions(vision_enabled=False))
