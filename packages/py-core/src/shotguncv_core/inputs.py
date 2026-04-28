from __future__ import annotations

import re
import base64
import json
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
        if not text.strip():
            raise InputExtractionError(
                f"PDF input `{path}` did not contain extractable text. "
                "Scanned PDFs are not OCRed in this version; provide a text or markdown sidecar."
            )
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
