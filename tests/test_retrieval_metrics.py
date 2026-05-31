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
