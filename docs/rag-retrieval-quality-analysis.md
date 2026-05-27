# RAG Retrieval Quality Analysis

Date: 2026-05-27
Run: `baseline-formal-r3-full-raw-library-20260520`
Golden set: `fixtures/golden_rag_questions.json` (rag-golden-v1, 30 samples)
Reports: `baseline/rag-layered-20260527-comparison/`

## Setup

- 642 retrieval chunks from the run directory
- 25 answerable + 5 no_answer samples
- Evaluated with dense (bge-m3, 1024d), BM25 (k1=1.5, b=0.75), hybrid (vector=0.55, BM25=0.45)
- k values: 1, 3, 5, 10
- No search filters applied — all 642 chunks compete for every query

## Aggregate Metrics

| Metric | Dense | BM25 | Hybrid |
|--------|-------|------|--------|
| precision@1 | 0.0 | 0.0 | 0.0 |
| precision@3 | 0.0 | 0.0133 | 0.0 |
| precision@5 | 0.0 | 0.008 | 0.0 |
| precision@10 | 0.012 | 0.004 | 0.004 |
| recall@10 | 0.08 | 0.02 | 0.02 |
| nDCG@10 | 0.0285 | 0.0123 | 0.0074 |
| MRR | 0.0152 | 0.0133 | 0.0044 |
| Wall clock | 85.5s | 1.8s | 45.7s |

## Per-Case-Type Breakdown

| Case Type (count) | Mode | MRR | recall@10 |
|-------------------|------|-----|-----------|
| common_question (12) | dense | 0.0119 | 0.083 |
| | BM25 | 0.0 | 0.0 |
| | hybrid | 0.0 | 0.0 |
| multi_document (8) | dense | 0.0295 | 0.125 |
| | BM25 | 0.0417 | 0.0625 |
| | hybrid | 0.0139 | 0.0625 |
| stale_or_conflicting (5) | all | 0.0 | 0.0 |

## No-Answer Behavior (5 samples, threshold=0.8)

| Mode | Abstention Rate | Quality Gate |
|------|----------------|-------------|
| dense | 1.0 | passed |
| hybrid | 1.0 | passed |
| BM25 | 0.6 | failed (2 leaked) |

## Hit Distribution

Only 3 queries out of 25 had any hits at k=10 for dense, 1 for BM25, 1 for hybrid:

| Query | Mode | Hit Position | Expected Label |
|-------|------|-------------|----------------|
| rag-golden-010 | dense | 9th | jd-013-req-007 |
| rag-golden-026 | dense/hybrid | 7th/8th | candidate-profile |
| rag-golden-027 | dense | 8th | candidate-profile |
| rag-golden-016 | BM25 | 3rd–5th | JD profile jd-002 |

## Root Cause Analysis

### 1. No search filtering — 642 chunks compete globally (impact: highest)

`_sample_to_query_spec` in [evaluate_rag_layers.py](../scripts/evaluate_rag_layers.py) passes only `query_id` and `query` text. No `candidate_id`, `jd_id`, or `source_type` filters are passed.

`evaluate_labeled_retrieval_queries` in [metrics.py](../packages/py-core/src/shotguncv_core/rag/metrics.py) calls `retriever.search(query, limit=search_limit)` without any filter arguments.

**Why it matters**: in production, RAG queries are scoped by candidate/JD. Golden samples have metadata (`candidate_scope`, `jd_count`) that could narrow the search space dramatically. Searching across 642 chunks makes it nearly impossible for any specific chunk to surface in the top 10.

### 2. requirement_evidence chunks are structurally homogeneous

All requirement_evidence chunks share the same template: `requirement_text + evidence_status + evidence_refs`, all from a single artifact (`analyze/requirement_matrix.json`). See [documents.py](../packages/py-core/src/shotguncv_core/rag/documents.py).

**Why it matters**: the embedding model can't distinguish between "LangGraph/RAG pipeline evidence" and "generic CI/CD pipeline evidence" because all chunks talk about "technical experience/project evidence" in similar language. The dense embedding scores for these chunks cluster tightly, drowning out the correct one.

### 3. Natural language queries vs structured document IDs

Golden labels use structured identifiers (`jd-001-req-014`, `jd-012:gap-map`, `JD profile jd-002`), but queries are conversational Chinese questions.

- **Dense**: relies on bge-m3 to map Chinese queries to chunk text embeddings. Works only when the query's semantic fingerprint is distinctive enough to separate the target chunk from 641 others.
- **BM25**: relies on term overlap. Works only when the query tokens explicitly match chunk content — as shown by the single BM25 success ("数据分析/产品洞察岗位" → `JD profile jd-002`).

### 4. Cross-lingual semantic gap

Queries are Chinese; requirement_evidence chunk core content (`requirement_text`, `evidence_refs`) is often English or mixed. While bge-m3 supports multilingual embeddings, cross-lingual fine-grained semantic discrimination degrades at 1024 dimensions with 642 short-text candidates.

### 5. Hybrid fusion suppresses individual signals

Hybrid MRR (0.0044) is lower than both dense (0.0152) and BM25 (0.0133). The score normalization (`clamp` for vector, `score/(score+1)` for BM25) and current weights (0.55/0.45) cause the two signals to dilute each other rather than complement. Dense's `candidate-profile` hits get dragged down by BM25 noise; BM25's `JD profile` hits get dragged down by dense noise.

## Improvement Priorities

| Priority | Direction | Rationale |
|----------|-----------|-----------|
| **P0** | Add search filters to query specs | `_sample_to_query_spec` should extract `candidate_id`/`jd_id` from golden metadata and pass them to `retriever.search()`. This alone could shrink the candidate set from 642 to ~20–50 chunks per query. |
| **P0** | Enrich chunk text with distinguishing metadata | `_chunk_search_text` in [retrieval.py](../packages/py-core/src/shotguncv_core/rag/retrieval.py) should include JD title, requirement category, and other differentiating fields to give each chunk a more unique lexical/semantic signature. |
| **P1** | Tune hybrid weights | Grid search over `vector_weight`/`bm25_weight`, or adopt learning-to-rank fusion. Current 0.55/0.45 split is worse than either single mode. |
| **P1** | Align golden queries with chunk language | Rewrite queries to include English technical terms and specific identifiers that appear in expected chunks, improving both dense and BM25 hit rates. |
| **P2** | Add cross-encoder reranker | Apply a reranker to the top-50 first-stage results to improve top-k precision without changing the retrieval pipeline. |
| **P2** | Merge same-source_id chunks | Collapse multiple chunks from the same document into a single retrieval unit, so chunk splitting doesn't prevent document-level hit recognition. |
