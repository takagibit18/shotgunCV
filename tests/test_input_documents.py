from __future__ import annotations

from pathlib import Path

import pytest

from shotguncv_core.inputs import InputExtractionError, collect_input_documents


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

    with pytest.raises(InputExtractionError, match="sidecar"):
        collect_input_documents([image_path])


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
