from __future__ import annotations

import base64
import json
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence
from urllib import request

from shotguncv_core.cv_extraction import (
    ExtractionBlock,
    PageExtractionResult,
    _cjk_bigram_hit_rate,
    decide_page_source,
    score_text_quality,
)


TEXT_EXTENSIONS = {".txt", ".md", ".markdown"}
PDF_EXTENSIONS = {".pdf"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff"}
SUPPORTED_EXTENSIONS = TEXT_EXTENSIONS | PDF_EXTENSIONS | IMAGE_EXTENSIONS
SKIPPED_DIRECTORY_NAMES = {
    ".git",
    ".next",
    ".pytest_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
}


class InputExtractionError(ValueError):
    pass


@dataclass(slots=True)
class InputDocument:
    source_type: str
    source_value: str
    media_type: str
    text: str
    extraction_status: str
    extraction_provider: str = ""
    extraction_error: str = ""
    original_name: str = ""
    size_bytes: int = 0
    text_quality_status: str = "unchecked"
    text_quality_error: str = ""
    analysis_eligible: bool = True
    quality_score: float = 0.0


@dataclass(slots=True)
class InputExtractionOptions:
    ocr_provider: str = "local_ocr"
    ocr_engine: str = "rapidocr"  # "tesseract" | "rapidocr"
    vision_provider: str = "openai_vision"
    vision_model: str = "gpt-5.4-mini"
    ocr_languages: str = "eng+chi_sim"
    vision_enabled: bool = True
    openai_base_url: str = "https://api.openai.com/v1"
    openai_api_key: str = ""


def collect_input_documents(
    sources: Iterable[Path],
    options: InputExtractionOptions | None = None,
) -> list[InputDocument]:
    extraction_options = options or InputExtractionOptions()
    documents: list[InputDocument] = []
    for source in sources:
        documents.extend(_collect_from_source(Path(source), extraction_options))
    return documents


def _collect_from_source(source: Path, options: InputExtractionOptions) -> list[InputDocument]:
    if source.is_dir():
        paths = _iter_supported_files(source)
        if not paths:
            raise InputExtractionError(f"Input directory `{source}` does not contain supported input files.")
        return [_safe_extract_document(path, options) for path in paths]
    if source.is_file():
        if source.suffix.lower() not in SUPPORTED_EXTENSIONS:
            raise InputExtractionError(f"Unsupported input type `{source.suffix}` for `{source}`.")
        return [_safe_extract_document(source, options)]
    raise InputExtractionError(f"Input source `{source}` does not exist.")


def _iter_supported_files(directory: Path) -> list[Path]:
    paths: list[Path] = []
    for path in sorted(directory.rglob("*")):
        if any(part in SKIPPED_DIRECTORY_NAMES or part.startswith(".") for part in path.relative_to(directory).parts):
            continue
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
            if _is_image_sidecar(path):
                continue
            paths.append(path)
    return paths


def _extract_document(path: Path, options: InputExtractionOptions) -> InputDocument:
    suffix = path.suffix.lower()
    if suffix in TEXT_EXTENSIONS:
        return InputDocument(
            source_type="file",
            source_value=str(path),
            media_type=_text_media_type(suffix),
            text=path.read_text(encoding="utf-8"),
            extraction_status="extracted",
            extraction_provider="local_text",
            original_name=path.name,
            size_bytes=path.stat().st_size,
        )
    if suffix in PDF_EXTENSIONS:
        return _extract_pdf_document_page_level(path, options)
    if suffix in IMAGE_EXTENSIONS:
        return _extract_image_document(path, suffix, options)
    raise InputExtractionError(f"Unsupported input type `{path.suffix}` for `{path}`.")


def _safe_extract_document(path: Path, options: InputExtractionOptions) -> InputDocument:
    try:
        return _extract_document(path, options)
    except InputExtractionError as exc:
        return _unparseable_document(path, str(exc))


def _extract_pdf_document_page_level(path: Path, options: InputExtractionOptions) -> InputDocument:
    """Page-level PDF extraction with per-page quality scoring and selective OCR.

    Replaces the old document-level (all-or-nothing) fallback.
    """
    import fitz  # type: ignore[import-not-found]

    native_pages = _extract_pdf_pages_native(path)
    all_native_empty = all(not p.native_text.strip() for p in native_pages)

    # If every native page is empty, fall back to full-document OCR
    if all_native_empty:
        quality_warning = "PDF text extraction returned empty text."
        return _extract_pdf_with_image_fallback(path, options, quality_warning)

    # Page-level: native-first with selective OCR fallback.
    # pypdf is fast and free — use it as the primary source.
    # Only trigger OCR per page when native text quality is clearly bad.
    final_pages: list[PageExtractionResult] = []
    ocr_used_any = False

    for native_page in native_pages:
        page_num = native_page.page
        native_text = native_page.native_text
        native_score = native_page.native_score

        # Skip OCR if native text quality is good enough
        cjk_suspicious = _cjk_bigram_hit_rate(native_text) < 0.15
        if native_score >= 0.35 and not cjk_suspicious:
            final_pages.append(native_page)
            continue

        # Native quality below threshold or CJK-corrupted — trigger OCR
        ocr_text = ""
        ocr_score = 0.0
        try:
            page_img = _render_single_pdf_page(path, page_num)
            try:
                ocr_raw = _extract_image_text_with_ocr(page_img, options.ocr_languages, engine=options.ocr_engine)
                ocr_text = _normalize_extracted_text_for_ingest(ocr_raw).strip()
                ocr_score = score_text_quality(ocr_text) if ocr_text else 0.0
            finally:
                _cleanup_rendered_pdf_pages([page_img])
        except Exception:
            ocr_text = ""
            ocr_score = 0.0

        result = decide_page_source(
            native_text=native_text,
            native_score=native_score,
            ocr_text=ocr_text,
            ocr_score=ocr_score,
        )
        result.page = page_num
        if result.ocr_used:
            ocr_used_any = True
        final_pages.append(result)

    # Build final text
    final_text = "\n\n".join(p.text for p in final_pages if p.text.strip())

    # Determine extraction status
    if ocr_used_any:
        final_status = "ocr"
        final_provider = "local_pdf+ocr"
    else:
        final_status = "extracted"
        final_provider = "local_pdf"

    avg_score = round(sum(p.quality_score for p in final_pages) / max(1, len(final_pages)), 4)

    return InputDocument(
        source_type="file",
        source_value=str(path),
        media_type="application/pdf",
        text=final_text,
        extraction_status=final_status,
        extraction_provider=final_provider,
        original_name=path.name,
        size_bytes=path.stat().st_size,
        quality_score=avg_score,
    )


def _render_single_pdf_page(path: Path, page_num: int) -> Path:
    """Render one PDF page to a PNG image for OCR."""
    import fitz  # type: ignore[import-not-found]

    output_dir = Path(tempfile.mkdtemp(prefix="shotguncv-pdf-pages-"))
    document = fitz.open(str(path))
    try:
        page = document[page_num - 1]  # fitz is 0-indexed
        pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
        page_path = output_dir / f"{path.stem}-page-{page_num:03d}.png"
        pixmap.save(str(page_path))
    finally:
        document.close()
    return page_path


def _unparseable_document(path: Path, error: str) -> InputDocument:
    suffix = path.suffix.lower()
    if suffix in TEXT_EXTENSIONS:
        media_type = _text_media_type(suffix)
        provider = "local_text"
    elif suffix in PDF_EXTENSIONS:
        media_type = "application/pdf"
        provider = "local_pdf"
    elif suffix in IMAGE_EXTENSIONS:
        media_type = _image_media_type(suffix)
        provider = "local_ocr"
    else:
        media_type = "application/octet-stream"
        provider = ""
    return InputDocument(
        source_type="file",
        source_value=str(path),
        media_type=media_type,
        text="",
        extraction_status="unparseable",
        extraction_provider=provider,
        extraction_error=error,
        original_name=path.name,
        size_bytes=path.stat().st_size,
    )


def _extract_image_document(path: Path, suffix: str, options: InputExtractionOptions) -> InputDocument:
    media_type = _image_media_type(suffix)
    sidecar = _find_sidecar(path)
    try:
        if options.ocr_provider != "disabled":
            raw_ocr_text = _extract_image_text_with_ocr(path, options.ocr_languages, engine=options.ocr_engine)
            ocr_text = _normalize_extracted_text_for_ingest(raw_ocr_text)
            if ocr_text:
                quality_warning = _image_ocr_text_quality_warning(raw_ocr_text, ocr_text)
                if quality_warning is not None:
                    ocr_error = f"OCR text quality is too low: {quality_warning}"
                else:
                    return InputDocument(
                        source_type="file",
                        source_value=str(path),
                        media_type=media_type,
                        text=ocr_text,
                        extraction_status="ocr",
                        extraction_provider=options.ocr_provider,
                        original_name=path.name,
                        size_bytes=path.stat().st_size,
                    )
            else:
                ocr_error = "OCR returned empty text."
        else:
            ocr_error = "OCR provider is disabled."
    except Exception as exc:
        ocr_error = str(exc).strip() or exc.__class__.__name__

    if options.vision_enabled and options.vision_provider != "disabled":
        try:
            vision_text = _normalize_extracted_text_for_ingest(_extract_image_text_with_vision(path, options, ocr_error))
            if vision_text:
                return InputDocument(
                    source_type="file",
                    source_value=str(path),
                    media_type=media_type,
                    text=vision_text,
                    extraction_status="vision",
                    extraction_provider=options.vision_provider,
                    extraction_error=f"ocr: {ocr_error}",
                    original_name=path.name,
                    size_bytes=path.stat().st_size,
                )
            vision_error = "Vision provider returned empty text."
        except Exception as exc:
            vision_error = str(exc).strip() or exc.__class__.__name__
    else:
        vision_error = "Vision fallback is disabled."

    if sidecar is not None:
        return InputDocument(
            source_type="file",
            source_value=str(path),
            media_type=media_type,
            text=sidecar.read_text(encoding="utf-8"),
            extraction_status="sidecar",
            extraction_provider="sidecar",
            extraction_error=f"ocr: {ocr_error}; vision: {vision_error}",
            original_name=path.name,
            size_bytes=path.stat().st_size,
        )

    raise InputExtractionError(_format_image_extraction_error(path, ocr_error, vision_error))


def _normalize_extracted_text_for_ingest(text: str) -> str:
    normalized_lines: list[str] = []
    for raw_line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        line = _collapse_ocr_spaced_tokens(line)
        line = re.sub(r"[ \t]{2,}", " ", line).strip()
        line = _normalize_ocr_confusions(line)
        if _looks_like_ocr_job_metadata_line(line):
            continue
        if _looks_like_symbol_noise_line(line):
            continue
        normalized_lines.append(line)
    return "\n".join(normalized_lines).strip()


def _collapse_ocr_spaced_tokens(line: str) -> str:
    previous = None
    current = line
    while previous != current:
        previous = current
        current = re.sub(r"([\u4e00-\u9fff])\s+([\u4e00-\u9fff])", r"\1\2", current)
    return re.sub(
        r"(?<![A-Za-z])(?:[A-Za-z]\s+){2,}[A-Za-z](?![A-Za-z])",
        lambda match: re.sub(r"\s+", "", match.group(0)),
        current,
    )


def _normalize_ocr_confusions(line: str) -> str:
    replacements = {
        "技术驿动": "技术驱动",
        "校拙": "校招",
        "稿定性": "稳定性",
        "烈悉": "熟悉",
        "熬悉": "熟悉",
        "跟除新技术趋势": "跟踪新技术趋势",
        "跟院 Agent 抚术": "跟踪 Agent 技术",
        "抚术": "技术",
        "跟院": "跟踪",
    }
    normalized = line
    for source, target in replacements.items():
        normalized = normalized.replace(source, target)
    normalized = re.sub(r"^[¢]\s*", "- ", normalized)
    normalized = re.sub(r"(?<![A-Za-z])Al(?![a-z])", "AI", normalized)
    return re.sub(
        r"(?<![A-Za-z])A(?=\s*(?:赋能|工具|方案|技术|应用|驱动|系统|接口|Agent|App|APP|模型|功能))",
        "AI",
        normalized,
    )


def _looks_like_ocr_job_metadata_line(line: str) -> bool:
    text = line.strip().strip("-*•").strip()
    lowered = text.lower()
    if not text:
        return True
    if text in {"动化"}:
        return True
    if re.search(r"\b(published|posted)\b.*\b(ago|day|days|hour|hours|d|h)\b", lowered):
        return True
    if re.search(r"\busd\b|\$\s*\d|\b\d+\s*k\s*[-–]\s*\d+\s*k\b", lowered):
        return True
    recruitment_terms = ["校招", "春招", "招聘", "实习研发", "后端开发", "届国内", "届实习生"]
    location_terms = ["北京", "上海", "深圳", "shenzhen", "remote"]
    industry_terms = [
        "intelligent manufacturing",
        "industrial internet",
        "industrial automation",
        "智能制造",
        "工业互联网",
        "工业自动化",
    ]
    has_metadata_separator = "|" in text or "@" in text
    if has_metadata_separator and any(term in lowered for term in industry_terms):
        return True
    if has_metadata_separator and any(term in text for term in recruitment_terms):
        return True
    if has_metadata_separator and any(term in text or term in lowered for term in location_terms) and len(text) <= 80:
        return True
    if "/" in text and len(text) <= 40 and any(term in text for term in ["互联网", "工业", "动化", "智能制造"]):
        return True
    return False


def _looks_like_symbol_noise_line(line: str) -> bool:
    visible_chars = [char for char in line if not char.isspace()]
    if not visible_chars:
        return True
    content_chars = [char for char in visible_chars if char.isalnum() or "\u4e00" <= char <= "\u9fff"]
    return len(content_chars) == 0 or (len(visible_chars) >= 4 and len(content_chars) / len(visible_chars) < 0.35)


def _image_ocr_text_quality_warning(raw_text: str, clean_text: str) -> str | None:
    visible_chars = sum(1 for char in clean_text if char.isprintable() and not char.isspace())
    content_chars = sum(1 for char in clean_text if char.isalnum() or "\u4e00" <= char <= "\u9fff")
    raw_lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    symbol_noise_lines = sum(1 for line in raw_lines if _looks_like_symbol_noise_line(line))
    if visible_chars < 8 or content_chars < 8:
        return f"too little usable text ({visible_chars} visible chars)."
    if _looks_like_label_only_ocr_text(clean_text):
        return "only labels or section headings were extracted."
    if raw_lines and symbol_noise_lines / max(1, len(raw_lines)) > 0.35:
        return "too many symbol-noise lines."
    if content_chars / max(1, visible_chars) < 0.55:
        return "too much non-content symbol noise."
    return None


def _looks_like_label_only_ocr_text(text: str) -> bool:
    lines = [line.strip().strip(":：-") for line in text.splitlines() if line.strip()]
    if len(lines) < 3:
        return False
    label_terms = {
        "岗位职责",
        "任职要求",
        "职位标签",
        "教育",
        "学历",
        "福利",
        "薪资",
        "地点",
        "技能",
        "职责",
        "要求",
        "responsibilities",
        "requirements",
        "education",
        "benefits",
        "skills",
    }
    label_like = 0
    for line in lines:
        lowered = line.lower()
        if lowered in label_terms or (len(line) <= 4 and not re.search(r"[A-Za-z0-9]", line)):
            label_like += 1
    return label_like / len(lines) >= 0.8


def _text_media_type(suffix: str) -> str:
    if suffix in {".md", ".markdown"}:
        return "text/markdown"
    return "text/plain"


def _image_media_type(suffix: str) -> str:
    mapping = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".gif": "image/gif",
        ".bmp": "image/bmp",
        ".tif": "image/tiff",
        ".tiff": "image/tiff",
    }
    return mapping.get(suffix, "image/*")


def _extract_pdf_with_image_fallback(path: Path, options: InputExtractionOptions, quality_warning: str) -> InputDocument:
    try:
        page_images = _render_pdf_pages_to_images(path)
    except Exception as exc:
        render_error = str(exc).strip() or exc.__class__.__name__
        raise InputExtractionError(_format_pdf_extraction_error(path, quality_warning, render_error, "", "")) from exc

    try:
        try:
            if options.ocr_provider != "disabled":
                ocr_chunks = [_extract_image_text_with_ocr(image_path, options.ocr_languages).strip() for image_path in page_images]
                ocr_text = "\n\n".join(chunk for chunk in ocr_chunks if chunk)
                if ocr_text.strip():
                    return InputDocument(
                        source_type="file",
                        source_value=str(path),
                        media_type="application/pdf",
                        text=ocr_text,
                        extraction_status="ocr",
                        extraction_provider=options.ocr_provider,
                        extraction_error=f"PDF text extraction fallback: {quality_warning}",
                        original_name=path.name,
                        size_bytes=path.stat().st_size,
                    )
                ocr_error = "OCR returned empty text."
            else:
                ocr_error = "OCR provider is disabled."
        except Exception as exc:
            ocr_error = str(exc).strip() or exc.__class__.__name__

        if options.vision_enabled and options.vision_provider != "disabled":
            try:
                vision_chunks = [
                    _extract_image_text_with_vision(
                        image_path,
                        options,
                        f"PDF text extraction: {quality_warning}; OCR: {ocr_error}",
                    ).strip()
                    for image_path in page_images
                ]
                vision_text = "\n\n".join(chunk for chunk in vision_chunks if chunk)
                if vision_text.strip():
                    return InputDocument(
                        source_type="file",
                        source_value=str(path),
                        media_type="application/pdf",
                        text=vision_text,
                        extraction_status="vision",
                        extraction_provider=options.vision_provider,
                        extraction_error=f"PDF text extraction fallback: {quality_warning}; ocr: {ocr_error}",
                        original_name=path.name,
                        size_bytes=path.stat().st_size,
                    )
                vision_error = "Vision provider returned empty text."
            except Exception as exc:
                vision_error = str(exc).strip() or exc.__class__.__name__
        else:
            vision_error = "Vision fallback is disabled."

        raise InputExtractionError(_format_pdf_extraction_error(path, quality_warning, "", ocr_error, vision_error))
    finally:
        _cleanup_rendered_pdf_pages(page_images)


def _cleanup_rendered_pdf_pages(page_images: list[Path]) -> None:
    parents = {image_path.parent for image_path in page_images}
    for parent in parents:
        if parent.name.startswith("shotguncv-pdf-pages-"):
            shutil.rmtree(parent, ignore_errors=True)

def _find_sidecar(path: Path) -> Path | None:
    for suffix in (".txt", ".md"):
        candidate = path.with_suffix(suffix)
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def _is_image_sidecar(path: Path) -> bool:
    if path.suffix.lower() not in TEXT_EXTENSIONS:
        return False
    return any(path.with_suffix(suffix).exists() for suffix in IMAGE_EXTENSIONS)


def _extract_pdf_text(path: Path) -> str:
    try:
        from pypdf import PdfReader  # type: ignore[import-not-found]

        reader = PdfReader(str(path))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        if text.strip():
            return text
    except Exception:
        pass
    return _extract_pdf_literal_text(path.read_bytes())


def _extract_pdf_pages_native(path: Path) -> list[PageExtractionResult]:
    """Extract native text from each PDF page via pypdf, with scoring."""
    page_results: list[PageExtractionResult] = []
    try:
        from pypdf import PdfReader  # type: ignore[import-not-found]

        reader = PdfReader(str(path))
        for idx, page in enumerate(reader.pages, start=1):
            native_text = (page.extract_text() or "").strip()
            page_score = score_text_quality(native_text) if native_text else 0.0
            page_results.append(
                PageExtractionResult(
                    page=idx,
                    text=native_text,
                    source="native",
                    quality_score=page_score,
                    ocr_used=False,
                    native_text=native_text,
                    ocr_text="",
                    native_score=page_score,
                    ocr_score=0.0,
                    ocr_triggered=False,
                )
            )
        return page_results
    except Exception:
        pass

    # pypdf failed entirely — try literal extraction and split by page break marker
    raw = _extract_pdf_literal_text(path.read_bytes())
    # Simple split: treat each page as one block since literal extraction loses page boundaries
    page_score = score_text_quality(raw) if raw.strip() else 0.0
    return [
        PageExtractionResult(
            page=1,
            text=raw.strip(),
            source="native",
            quality_score=page_score,
            ocr_used=False,
            native_text=raw.strip(),
            ocr_text="",
            native_score=page_score,
            ocr_score=0.0,
            ocr_triggered=False,
        )
    ]


def _pdf_text_quality_warning(text: str) -> str | None:
    stripped = text.strip()
    if not stripped:
        return "PDF text extraction returned empty text."
    visible_chars = sum(1 for char in stripped if char.isprintable() and not char.isspace())
    replacement_chars = stripped.count("\ufffd")
    control_chars = sum(1 for char in stripped if ord(char) < 32 and char not in "\r\n\t")
    escaped_control_sequences = len(re.findall(r"\\\d{3}", stripped))
    lines = [line.strip() for line in stripped.splitlines() if line.strip()]
    single_char_lines = sum(1 for line in lines if len(line) == 1)
    average_line_length = visible_chars / max(1, len(lines))
    if visible_chars < 8:
        return f"PDF text extraction returned too little usable text ({visible_chars} visible chars)."
    if replacement_chars / max(1, len(stripped)) > 0.05:
        return "PDF text extraction produced too many replacement characters."
    if control_chars / max(1, len(stripped)) > 0.05:
        return "PDF text extraction produced too many control characters."
    if escaped_control_sequences >= 3:
        return f"PDF text extraction produced escaped control sequences ({escaped_control_sequences} matches)."
    if len(lines) >= 12 and single_char_lines / max(1, len(lines)) > 0.35 and average_line_length < 12:
        return "PDF text extraction produced fragmented low-information lines."
    if _cjk_bigram_hit_rate(stripped) < 0.08:
        return "PDF text extraction produced semantically corrupted CJK text (CJK bigram dictionary hit rate near zero)."
    return None


def _render_pdf_pages_to_images(path: Path) -> list[Path]:
    try:
        import fitz  # type: ignore[import-not-found]
    except Exception as exc:
        raise RuntimeError("PDF OCR fallback requires PyMuPDF.") from exc

    output_dir = Path(tempfile.mkdtemp(prefix="shotguncv-pdf-pages-"))
    page_paths: list[Path] = []
    document = fitz.open(str(path))
    try:
        for index, page in enumerate(document, start=1):
            pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            page_path = output_dir / f"{path.stem}-page-{index:03d}.png"
            pixmap.save(str(page_path))
            page_paths.append(page_path)
    finally:
        document.close()
    if not page_paths:
        raise RuntimeError("PDF renderer found no pages.")
    return page_paths


def _extract_pdf_literal_text(payload: bytes) -> str:
    text = payload.decode("latin-1", errors="ignore")
    literals = re.findall(r"\(([^()]*)\)\s*Tj", text)
    return "\n".join(_unescape_pdf_literal(item) for item in literals)


def _unescape_pdf_literal(value: str) -> str:
    return value.replace(r"\(", "(").replace(r"\)", ")").replace(r"\\", "\\")


def _extract_image_text_with_ocr(path: Path, languages: str, *, engine: str = "tesseract") -> str:
    """Dispatch to the configured OCR engine."""
    if engine == "rapidocr":
        return _extract_image_text_with_rapidocr(path)
    return _extract_image_text_with_tesseract(path, languages)


def _extract_image_text_with_tesseract(path: Path, languages: str) -> str:
    try:
        from PIL import Image  # type: ignore[import-not-found]
        import pytesseract  # type: ignore[import-not-found]
    except Exception as exc:
        raise RuntimeError("Tesseract OCR requires Pillow, pytesseract, and the Tesseract executable.") from exc
    with Image.open(path) as image:
        return str(pytesseract.image_to_string(image, lang=languages))


# Lazy-loaded RapidOCR singleton
_rapidocr_engine: object | None = None


def _get_rapidocr_engine() -> object:
    global _rapidocr_engine
    if _rapidocr_engine is None:
        from rapidocr_onnxruntime import RapidOCR  # type: ignore[import-not-found]

        _rapidocr_engine = RapidOCR()
    return _rapidocr_engine


def _extract_image_text_with_rapidocr(path: Path) -> str:
    """Extract text from an image using RapidOCR (ONNX-based, no GPU needed)."""
    engine = _get_rapidocr_engine()
    result, _ = engine(str(path))  # type: ignore[call-arg]
    if result is None or not result:
        return ""
    # result is list of [bbox, text, confidence] tuples
    # Group by Y-coordinate for line ordering
    lines: list[list[tuple[float, str]]] = []
    current_y = -1.0
    current_line: list[tuple[float, str]] = []
    for item in result:
        bbox = item[0]  # [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
        text = str(item[1])
        conf = float(item[2])
        y_center = (bbox[0][1] + bbox[2][1]) / 2
        if current_y < 0 or abs(y_center - current_y) < 8:
            current_line.append((bbox[0][0], text))
        else:
            lines.append(sorted(current_line, key=lambda t: t[0]))
            current_line = [(bbox[0][0], text)]
        current_y = y_center
    if current_line:
        lines.append(sorted(current_line, key=lambda t: t[0]))
    return "\n".join(" ".join(token for _, token in line) for line in lines)


def _extract_image_text_with_vision(path: Path, options: InputExtractionOptions, ocr_error: str) -> str:
    if not options.openai_api_key:
        raise RuntimeError("missing OPENAI_API_KEY for vision fallback")
    payload = json.dumps(
        {
            "model": options.vision_model or "gpt-5.4-mini",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "Extract all CV or job description text from this image. "
                                f"OCR failed first with: {ocr_error}. Return plain text only."
                            ),
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": _image_data_url(path)},
                        },
                    ],
                }
            ],
            "temperature": 0.0,
        }
    ).encode("utf-8")
    response = request.Request(
        url=f"{options.openai_base_url.rstrip('/')}/chat/completions",
        data=payload,
        headers={
            "Authorization": f"Bearer {options.openai_api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with request.urlopen(response, timeout=90) as handle:
        body = json.loads(handle.read().decode("utf-8"))
    return str(body["choices"][0]["message"]["content"]).strip()


def _image_data_url(path: Path) -> str:
    mime = _image_media_type(path.suffix.lower())
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _format_image_extraction_error(path: Path, ocr_error: str, vision_error: str) -> str:
    return (
        f"Image input `{path}` could not be extracted. "
        f"OCR error: {ocr_error}. "
        f"Vision fallback error: {vision_error}. "
        "Install Tesseract with required language packs, configure OPENAI_API_KEY/SHOTGUNCV_VISION_MODEL, "
        "or provide a same-name .txt or .md sidecar."
    )


def _format_pdf_extraction_error(
    path: Path,
    quality_warning: str,
    render_error: str,
    ocr_error: str,
    vision_error: str,
) -> str:
    parts = [
        f"PDF input `{path}` could not be extracted.",
        f"PDF text extraction issue: {quality_warning}",
    ]
    if render_error:
        parts.append(f"Render error: {render_error}.")
    if ocr_error:
        parts.append(f"OCR error: {ocr_error}.")
    if vision_error:
        parts.append(f"Vision fallback error: {vision_error}.")
    parts.append(
        "Install PyMuPDF and Tesseract with required language packs, configure OPENAI_API_KEY/SHOTGUNCV_VISION_MODEL, "
        "or provide a text or markdown CV sidecar."
    )
    return " ".join(parts)
