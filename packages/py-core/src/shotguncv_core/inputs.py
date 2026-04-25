from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


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


def collect_input_documents(sources: Iterable[Path]) -> list[InputDocument]:
    documents: list[InputDocument] = []
    for source in sources:
        documents.extend(_collect_from_source(Path(source)))
    return documents


def _collect_from_source(source: Path) -> list[InputDocument]:
    if source.is_dir():
        return [_extract_document(path) for path in _iter_supported_files(source)]
    if source.is_file():
        return [_extract_document(source)]
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


def _extract_document(path: Path) -> InputDocument:
    suffix = path.suffix.lower()
    if suffix in TEXT_EXTENSIONS:
        return InputDocument(
            source_type="file",
            source_value=str(path),
            media_type=_text_media_type(suffix),
            text=path.read_text(encoding="utf-8"),
            extraction_status="extracted",
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
        )
    if suffix in IMAGE_EXTENSIONS:
        sidecar = _find_sidecar(path)
        if sidecar is None:
            raise InputExtractionError(
                f"Image input `{path}` requires a same-name .txt or .md sidecar because OCR is not enabled."
            )
        return InputDocument(
            source_type="file",
            source_value=str(path),
            media_type=_image_media_type(suffix),
            text=sidecar.read_text(encoding="utf-8"),
            extraction_status="sidecar",
        )
    raise InputExtractionError(f"Unsupported input type `{path.suffix}` for `{path}`.")


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
