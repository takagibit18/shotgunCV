from __future__ import annotations

import re
import base64
import json
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib import request


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


@dataclass(slots=True)
class InputExtractionOptions:
    ocr_provider: str = "local_ocr"
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
        text = _extract_pdf_text(path)
        quality_warning = _pdf_text_quality_warning(text)
        if quality_warning is not None:
            return _extract_pdf_with_image_fallback(path, options, quality_warning)
        return InputDocument(
            source_type="file",
            source_value=str(path),
            media_type="application/pdf",
            text=text,
            extraction_status="extracted",
            extraction_provider="local_pdf",
            original_name=path.name,
            size_bytes=path.stat().st_size,
        )
    if suffix in IMAGE_EXTENSIONS:
        return _extract_image_document(path, suffix, options)
    raise InputExtractionError(f"Unsupported input type `{path.suffix}` for `{path}`.")


def _safe_extract_document(path: Path, options: InputExtractionOptions) -> InputDocument:
    try:
        return _extract_document(path, options)
    except InputExtractionError as exc:
        return _unparseable_document(path, str(exc))


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
            ocr_text = _extract_image_text_with_ocr(path, options.ocr_languages).strip()
            if ocr_text:
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
            ocr_error = "OCR returned empty text."
        else:
            ocr_error = "OCR provider is disabled."
    except Exception as exc:
        ocr_error = str(exc).strip() or exc.__class__.__name__

    if options.vision_enabled and options.vision_provider != "disabled":
        try:
            vision_text = _extract_image_text_with_vision(path, options, ocr_error).strip()
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
    debug_token_hits = sum(
        stripped.lower().count(token)
        for token in ("execute_tools", "submit_debug", "hit_rate", "offset/limit", "diff", "> analyze")
    )
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
    if debug_token_hits >= 3:
        return "PDF text extraction appears to contain tool/debug noise instead of document text."
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


def _extract_image_text_with_ocr(path: Path, languages: str) -> str:
    try:
        from PIL import Image  # type: ignore[import-not-found]
        import pytesseract  # type: ignore[import-not-found]
    except Exception as exc:
        raise RuntimeError("Tesseract OCR requires Pillow, pytesseract, and the Tesseract executable.") from exc
    with Image.open(path) as image:
        return str(pytesseract.image_to_string(image, lang=languages))


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
