from __future__ import annotations

from shotguncv_core.rag.metrics import evaluate_labeled_retrieval_queries, evaluate_ranked_retrieval
from shotguncv_core.rag.retrieval import RetrievalResult


def test_evaluate_ranked_retrieval_scores_standard_metrics() -> None:
    metrics = evaluate_ranked_retrieval(
        ranked_ids=["doc-a", "doc-b", "doc-c", "doc-d"],
        relevant_ids={"doc-b", "doc-d", "doc-e"},
        k_values=[1, 3, 4],
    )

    assert metrics["relevant_count"] == 3
    assert metrics["retrieved_count"] == 4
    assert metrics["precision_at_k"] == {"1": 0.0, "3": 1 / 3, "4": 0.5}
    assert metrics["recall_at_k"] == {"1": 0.0, "3": 1 / 3, "4": 2 / 3}
    assert metrics["mrr"] == 0.5
    assert round(metrics["ndcg_at_k"]["1"], 6) == 0.0
    assert round(metrics["ndcg_at_k"]["3"], 6) == round((1 / 1.584962500721156) / 2.1309297535714578, 6)
    assert round(metrics["ndcg_at_k"]["4"], 6) == round((1 / 1.584962500721156 + 1 / 2.321928094887362) / 2.1309297535714578, 6)


def test_evaluate_ranked_retrieval_handles_no_relevance_labels() -> None:
    metrics = evaluate_ranked_retrieval(
        ranked_ids=["doc-a", "doc-b"],
        relevant_ids=set(),
        k_values=[1, 5],
    )

    assert metrics["precision_at_k"] == {"1": 0.0, "5": 0.0}
    assert metrics["recall_at_k"] == {"1": 0.0, "5": 0.0}
    assert metrics["mrr"] == 0.0
    assert metrics["ndcg_at_k"] == {"1": 0.0, "5": 0.0}


def test_evaluate_ranked_retrieval_counts_duplicate_relevant_label_once() -> None:
    metrics = evaluate_ranked_retrieval(
        ranked_ids=["doc-a", "doc-a", "doc-a", "doc-b"],
        relevant_ids={"doc-a", "doc-b"},
        k_values=[3, 4],
    )

    assert metrics["precision_at_k"] == {"3": 1 / 3, "4": 0.5}
    assert metrics["recall_at_k"] == {"3": 0.5, "4": 1.0}
    assert metrics["mrr"] == 1.0
    assert round(metrics["ndcg_at_k"]["3"], 6) == round(1.0 / (1.0 + 1 / 1.584962500721156), 6)
    assert round(metrics["ndcg_at_k"]["4"], 6) == round((1.0 + 1 / 2.321928094887362) / (1.0 + 1 / 1.584962500721156), 6)


def test_evaluate_labeled_retrieval_queries_aggregates_query_metrics() -> None:
    retriever = _FakeRetriever(
        {
            "query one": [
                _result("unrelated", "plan/application_strategies.json", 0.9),
                _result("candidate_profile.experiences.0", "analyze/candidate_profile.json", 0.8),
                _result("jd-high-req-001", "analyze/requirement_matrix.json", 0.7),
            ],
            "query two": [
                _result("other", "review/post_run_review.json", 0.6),
            ],
        }
    )

    report = evaluate_labeled_retrieval_queries(
        retriever=retriever,
        query_specs=[
            {
                "jd_id": "jd-001",
                "query": "query one",
                "expected_chunks": ["candidate_profile.experiences.0", "jd-high-req-001"],
            },
            {
                "jd_id": "jd-002",
                "query": "query two",
                "expected_chunks": ["review/post_run_review.json"],
            },
        ],
        k_values=[1, 2, 3],
    )

    assert report["query_count"] == 2
    assert report["aggregate"]["precision_at_k"]["1"] == 0.5
    assert report["aggregate"]["recall_at_k"]["2"] == 0.75
    assert report["aggregate"]["mrr"] == 0.75
    assert report["queries"][0]["ranked_relevance"] == [False, True, True]
    assert report["queries"][1]["ranked_relevance"] == [True]
    assert report["queries"][0]["filters"] == {"jd_id": "jd-001"}
    assert report["queries"][1]["filters"] == {"jd_id": "jd-002"}
    assert retriever.calls == [
        {"query": "query one", "limit": 3, "filters": {"jd_id": "jd-001"}},
        {"query": "query two", "limit": 3, "filters": {"jd_id": "jd-002"}},
    ]


def test_evaluate_labeled_retrieval_queries_reports_weighted_multi_document_coverage() -> None:
    retriever = _FakeRetriever(
        {
            "multi doc": [
                _result("supporting-doc", "evaluate/gap_maps.json", 0.9),
                _result("unrelated", "plan/application_strategies.json", 0.8),
                _result("primary-doc", "analyze/requirement_matrix.json", 0.7),
            ],
        }
    )

    report = evaluate_labeled_retrieval_queries(
        retriever=retriever,
        query_specs=[
            {
                "query_id": "rag-golden-weighted",
                "query": "multi doc",
                "expected_chunks": ["primary-doc", "supporting-doc"],
                "expected_documents": [
                    {"label": "primary-doc", "role": "primary"},
                    {"label": "supporting-doc", "role": "supporting"},
                ],
            }
        ],
        k_values=[1, 3],
    )

    query = report["queries"][0]
    assert query["ranked_relevance"] == [True, False, True]
    assert query["evidence_coverage"] == {
        "expected_label_count": 2,
        "hit_label_count": 2,
        "missing_labels": [],
        "primary_expected_count": 1,
        "primary_hit_count": 1,
        "supporting_expected_count": 1,
        "supporting_hit_count": 1,
        "all_expected_hit": True,
        "all_primary_hit": True,
    }
    assert query["weighted_metrics"]["role_weights"] == {"primary-doc": 1.0, "supporting-doc": 0.5}
    assert query["weighted_metrics"]["weighted_recall_at_k"]["1"] == 1 / 3
    assert query["weighted_metrics"]["weighted_recall_at_k"]["3"] == 1.0
    assert query["weighted_metrics"]["weighted_ndcg_at_k"]["1"] == 0.5
    assert report["aggregate"]["weighted_recall_at_k"]["3"] == 1.0


def test_evaluate_labeled_retrieval_queries_decomposes_multi_document_searches() -> None:
    retriever = _FakeRetriever(
        {
            "multi doc primary evidence": [
                _result("primary-doc", "analyze/requirement_matrix.json", 0.9),
                _result("unrelated-primary", "analyze/requirement_matrix.json", 0.8),
            ],
            "multi doc supporting gap evidence": [
                _result("supporting-gap", "evaluate/gap_maps.json", 0.95),
            ],
        }
    )

    report = evaluate_labeled_retrieval_queries(
        retriever=retriever,
        query_specs=[
            {
                "query_id": "rag-golden-decomposed",
                "query": "multi doc",
                "case_type": "multi_document",
                "expected_chunks": ["primary-doc", "supporting-gap"],
                "expected_documents": [
                    {"label": "primary-doc", "role": "primary", "source_type": "requirement_evidence", "source_id": "jd-001-req-001"},
                    {"label": "supporting-gap", "role": "supporting", "source_type": "gap_map", "source_id": "jd-001:gap-map"},
                ],
                "query_decomposition": {
                    "strategy": "primary_then_related",
                    "stages": [
                        {
                            "name": "primary",
                            "query": "multi doc primary evidence",
                            "filters": {"source_type": "requirement_evidence"},
                            "limit": 2,
                        },
                        {
                            "name": "supporting",
                            "query": "multi doc supporting gap evidence",
                            "filters": {"source_type": "gap_map"},
                            "limit": 1,
                        },
                    ],
                },
            }
        ],
        k_values=[1, 3],
    )

    query = report["queries"][0]
    assert query["decomposition"]["strategy"] == "primary_then_related"
    assert [stage["name"] for stage in query["decomposition"]["stages"]] == ["primary", "supporting"]
    assert query["ranked_ids"] == ["primary-doc", "unrelated-primary", "supporting-gap"]
    assert query["evidence_coverage"]["all_primary_hit"] is True
    assert query["evidence_coverage"]["all_expected_hit"] is True
    assert report["aggregate"]["all_primary_hit_rate"] == 1.0
    assert report["aggregate"]["all_expected_hit_rate"] == 1.0
    assert retriever.calls == [
        {"query": "multi doc primary evidence", "limit": 2, "filters": {"source_type": "requirement_evidence"}},
        {"query": "multi doc supporting gap evidence", "limit": 1, "filters": {"source_type": "gap_map"}},
    ]


def test_decomposed_search_falls_back_to_fill_remaining_results() -> None:
    retriever = _FakeRetriever(
        {
            "multi doc primary evidence": [
                _result("primary-doc", "analyze/requirement_matrix.json", 0.9),
            ],
            "multi doc": [
                _result("primary-doc", "analyze/requirement_matrix.json", 0.9),
                _result("supporting-doc", "analyze/requirement_matrix.json", 0.8),
            ],
        }
    )

    report = evaluate_labeled_retrieval_queries(
        retriever=retriever,
        query_specs=[
            {
                "query_id": "rag-golden-decomposed-fallback",
                "query": "multi doc",
                "expected_chunks": ["primary-doc", "supporting-doc"],
                "expected_documents": [
                    {"label": "primary-doc", "role": "primary", "source_type": "requirement_evidence"},
                    {"label": "supporting-doc", "role": "supporting", "source_type": "requirement_evidence"},
                ],
                "query_decomposition": {
                    "strategy": "primary_then_related",
                    "stages": [
                        {
                            "name": "primary",
                            "query": "multi doc primary evidence",
                            "filters": {"source_type": "requirement_evidence"},
                            "limit": 1,
                        }
                    ],
                },
            }
        ],
        k_values=[1, 3],
    )

    query = report["queries"][0]
    assert [stage["name"] for stage in query["decomposition"]["stages"]] == ["primary", "fallback"]
    assert query["ranked_ids"] == ["primary-doc", "supporting-doc"]
    assert query["evidence_coverage"]["all_expected_hit"] is True
    assert retriever.calls == [
        {"query": "multi doc primary evidence", "limit": 1, "filters": {"source_type": "requirement_evidence"}},
        {"query": "multi doc", "limit": 3, "filters": {}},
    ]


class _FakeRetriever:
    def __init__(self, results_by_query: dict[str, list[RetrievalResult]]) -> None:
        self.results_by_query = results_by_query
        self.calls: list[dict[str, object]] = []

    def search(self, query: str, *, limit: int = 5, **filters: object) -> list[RetrievalResult]:
        self.calls.append({"query": query, "limit": limit, "filters": filters})
        return self.results_by_query[query][:limit]


def _result(source_id: str, artifact_path: str, score: float) -> RetrievalResult:
    return RetrievalResult(
        text=f"Evidence from {source_id} in {artifact_path}",
        metadata={
            "source_type": "candidate_evidence",
            "source_id": source_id,
            "artifact_path": artifact_path,
            "provenance_summary": f"provenance {source_id}",
        },
        score=score,
    )
