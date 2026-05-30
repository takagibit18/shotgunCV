from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from shotguncv_core.storage import load_json


@dataclass(frozen=True)
class Document:
    page_content: str
    metadata: dict[str, Any]


# source_types whose documents are short, self-contained semantic units.
# Splitting them creates unnecessary fragments that compete with each other in rankings.
_ATOMIC_SOURCE_TYPES: set[str] = {"requirement_evidence", "jd_description", "gap_map"}


def build_retrieval_chunks(run_dir: Path, run_id: str, candidate_id: str) -> list[dict[str, Any]]:
    documents = build_documents_from_run(run_dir, run_id, candidate_id)
    chunks: list[dict[str, Any]] = []
    for document in documents:
        source_type = str(document.metadata.get("source_type") or "")
        if source_type in _ATOMIC_SOURCE_TYPES:
            # Short, self-contained document — use as-is, don't split.
            text = document.page_content.strip()
            if not text:
                continue
            metadata = {**document.metadata, "chunk_index": 0}
            source_id = metadata["source_id"]
            chunk_id = _stable_id(f"{run_id}:{source_id}:0:{text[:64]}")
            chunks.append({"chunk_id": chunk_id, "text": text, "metadata": metadata})
        else:
            for index, text in enumerate(_split_text(document.page_content)):
                metadata = {**document.metadata, "chunk_index": index}
                source_id = metadata["source_id"]
                chunk_id = _stable_id(f"{run_id}:{source_id}:{index}:{text[:64]}")
                chunks.append({"chunk_id": chunk_id, "text": text, "metadata": metadata})
    return chunks


def build_documents_from_run(run_dir: Path, run_id: str, candidate_id: str) -> list[Document]:
    documents: list[Document] = []
    manifest = _read_json(run_dir / "ingest" / "manifest.json") or {}
    candidate = _read_json(run_dir / "analyze" / "candidate_profile.json") or {}
    jd_profiles = _read_json(run_dir / "analyze" / "jd_profiles.json") or []
    requirements = _read_json(run_dir / "analyze" / "requirement_matrix.json") or []
    gap_maps = _read_json(run_dir / "evaluate" / "gap_maps.json") or []
    variants = _read_json(run_dir / "generate" / "resume_variants.json") or []

    candidate_lines = []
    for field in ("core_claims", "verified_evidence", "experiences", "projects", "skills", "strengths"):
        candidate_lines.extend(str(item) for item in candidate.get(field, []) if str(item).strip())
    if candidate_lines:
        documents.append(
            _document(
                "\n".join(candidate_lines),
                source_type="candidate_evidence",
                source_id=f"{candidate_id}:candidate-profile",
                candidate_id=candidate_id,
                run_id=run_id,
                artifact_path="analyze/candidate_profile.json",
                provenance_summary="Candidate profile evidence extracted from analyze/candidate_profile.json.",
            )
        )

    for jd in jd_profiles:
        jd_id = str(jd.get("jd_id") or "")
        text = "\n".join(
            [
                str(jd.get("title") or ""),
                str(jd.get("company") or ""),
                *[str(item) for item in jd.get("responsibilities", [])],
                *[str(item) for item in jd.get("requirements", [])],
                *[str(item) for item in jd.get("must_have_requirements", [])],
            ]
        )
        documents.append(
            _document(
                text,
                source_type="jd_description",
                source_id=jd_id,
                candidate_id=candidate_id,
                jd_id=jd_id,
                run_id=run_id,
                artifact_path="analyze/jd_profiles.json",
                provenance_summary=f"JD profile {jd_id} from user-provided local artifacts.",
            )
        )

    for item in requirements:
        jd_id = str(item.get("jd_id") or "")
        requirement_id = str(item.get("requirement_id") or "")
        documents.append(
            _document(
                "\n".join(
                    [
                        str(item.get("requirement_text") or ""),
                        str(item.get("evidence_status") or ""),
                        "\n".join(str(ref) for ref in item.get("evidence_refs", [])),
                    ]
                ),
                source_type="requirement_evidence",
                source_id=requirement_id,
                candidate_id=candidate_id,
                jd_id=jd_id,
                run_id=run_id,
                artifact_path="analyze/requirement_matrix.json",
                provenance_summary=f"Requirement evidence {requirement_id} for {jd_id}.",
            )
        )

    for gap_map in gap_maps:
        jd_id = str(gap_map.get("jd_id") or "")
        gap_text = "\n".join(
            "\n".join(str(value) for value in item.values() if isinstance(value, (str, list)))
            for item in gap_map.get("items", [])
            if isinstance(item, dict)
        )
        if gap_text.strip():
            documents.append(
                _document(
                    gap_text,
                    source_type="gap_map",
                    source_id=f"{run_id}:{jd_id}:gap-map",
                    candidate_id=candidate_id,
                    jd_id=jd_id,
                    run_id=run_id,
                    artifact_path="evaluate/gap_maps.json",
                    provenance_summary=f"Gap map for {jd_id}.",
                )
            )

    for variant in variants:
        text = "\n".join(
            [
                str(variant.get("summary") or ""),
                *[str(item) for item in variant.get("emphasized_strengths", [])],
                *[str(item) for item in variant.get("safe_rewrites", [])],
                *[str(item) for item in variant.get("simulated_supplements", [])],
            ]
        )
        if text.strip():
            documents.append(
                _document(
                    text,
                    source_type="resume_variant",
                    source_id=str(variant.get("variant_id") or ""),
                    candidate_id=candidate_id,
                    jd_id=(variant.get("target_jd_ids") or [None])[0],
                    run_id=run_id,
                    artifact_path="generate/resume_variants.json",
                    provenance_summary=f"Resume variant {variant.get('variant_id')}.",
                )
            )

    for index, item in enumerate(manifest.get("jd_inputs", []) or []):
        text = str(item.get("content") or item.get("text") or "")
        if text.strip():
            documents.append(
                _document(
                    text,
                    source_type="jd_input",
                    source_id=f"{run_id}:jd-input:{index}",
                    candidate_id=candidate_id,
                    run_id=run_id,
                    artifact_path="ingest/manifest.json",
                    provenance_summary="Local user-provided JD input text from ingest manifest.",
                )
            )
    return documents


def _document(text: str, **metadata: Any) -> Document:
    clean = text.strip()
    return Document(page_content=clean, metadata=metadata)


def _split_text(text: str) -> list[str]:
    try:
        from langchain_text_splitters import RecursiveCharacterTextSplitter
    except ImportError:
        return _simple_split(text)
    splitter = RecursiveCharacterTextSplitter(chunk_size=900, chunk_overlap=120)
    return [chunk for chunk in splitter.split_text(text) if chunk.strip()]


def _simple_split(text: str, chunk_size: int = 900, overlap: int = 120) -> list[str]:
    clean = text.strip()
    if len(clean) <= chunk_size:
        return [clean] if clean else []
    chunks = []
    start = 0
    while start < len(clean):
        end = min(len(clean), start + chunk_size)
        chunks.append(clean[start:end].strip())
        if end == len(clean):
            break
        start = max(0, end - overlap)
    return [chunk for chunk in chunks if chunk]


def _read_json(path: Path) -> Any:
    return load_json(path) if path.exists() else None


def _stable_id(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
