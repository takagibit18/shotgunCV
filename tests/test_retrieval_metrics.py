from __future__ import annotations

from shotguncv_core.rag.embeddings import deterministic_embedding
from shotguncv_core.rag.metrics import evaluate_labeled_retrieval_queries, evaluate_ranked_retrieval
from shotguncv_core.rag.retrieval import RetrievalResult, SmartRouterRetriever, build_smart_query_plan


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


def test_query_report_preserves_slice_metadata_for_observability() -> None:
    retriever = _FakeRetriever({"risk query": [_result("doc-a", "artifact.json", 0.9)]})

    report = evaluate_labeled_retrieval_queries(
        retriever=retriever,
        query_specs=[
            {
                "query_id": "slice-001",
                "query": "risk query",
                "case_type": "multi_document",
                "golden_layer": "core_high_info",
                "robustness_category": "cross_section",
                "expected_chunks": ["doc-a"],
            }
        ],
        k_values=[1],
    )

    query = report["queries"][0]
    assert query["case_type"] == "multi_document"
    assert query["golden_layer"] == "core_high_info"
    assert query["robustness_category"] == "cross_section"


def test_build_smart_query_plan_is_oracle_free_and_explainable() -> None:
    broad_hits = [
        _result("candidate-profile", "analyze/candidate_profile.json", 0.9, source_type="candidate_evidence"),
        _result("jd-005-req-013", "analyze/requirement_matrix.json", 0.8, source_type="requirement_evidence", jd_id="jd-005"),
        _result("jd-005:ranking", "review/post_run_review.json", 0.7, source_type="ranking_explanation", jd_id="jd-005"),
    ]

    plan = build_smart_query_plan(
        "这个人 AI agent 工具链像不像，同时有什么风险？",
        broad_hits=broad_hits,
        hybrid_hits=broad_hits,
        limit=5,
        enable_support_gate=True,
    )

    assert plan["strategy"] == "smart_router"
    assert plan["oracle_free"] is True
    assert "semantic_alias_pattern" in plan["reasons"]
    assert "risk_gap_intent" in plan["reasons"]
    assert "LangGraph" in plan["rewrite_terms"]
    assert plan["routes"][0]["name"] == "hybrid_anchor"
    assert "gap_context" in plan["decomposition_stages"]
    assert plan["routes"][-1]["name"] == "broad_fallback"
    assert all("expected_documents" not in route for route in plan["routes"])


def test_smart_query_plan_keeps_multiple_jd_contexts_for_complex_queries() -> None:
    broad_hits = [
        _result("jd-021-req-001", "analyze/requirement_matrix.json", 0.9, source_type="requirement_evidence", jd_id="jd-021"),
        _result("jd-021-req-002", "analyze/requirement_matrix.json", 0.8, source_type="requirement_evidence", jd_id="jd-021"),
        _result("jd-015-req-014", "analyze/requirement_matrix.json", 0.7, source_type="requirement_evidence", jd_id="jd-015"),
        _result("jd-019-req-002", "analyze/requirement_matrix.json", 0.6, source_type="requirement_evidence", jd_id="jd-019"),
    ]

    plan = build_smart_query_plan(
        "分别对比这些岗位的风险和证据",
        broad_hits=broad_hits,
        hybrid_hits=broad_hits,
        limit=10,
    )

    jd_contexts = [route for route in plan["routes"] if route["name"] == "jd_context"]
    assert plan["routes"][0]["limit"] == 5
    assert [route["filters"]["jd_id"] for route in jd_contexts] == ["jd-021", "jd-015", "jd-019"]
    assert all(route["retriever_mode"] == "hybrid" for route in jd_contexts)


def test_smart_query_plan_tunes_quota_for_cross_section_like_hits() -> None:
    broad_hits = [
        _result("candidate-profile", "analyze/candidate_profile.json", 0.9, source_type="candidate_evidence"),
        _result("jd-018-req-003", "analyze/requirement_matrix.json", 0.8, source_type="requirement_evidence", jd_id="jd-018"),
        _result("jd-018:ranking", "evaluate/ranking_explanations.json", 0.7, source_type="ranking_explanation", jd_id="jd-018"),
        _result("jd-027-req-007", "analyze/requirement_matrix.json", 0.6, source_type="requirement_evidence", jd_id="jd-027"),
    ]

    plan = build_smart_query_plan(
        "compare candidate background with job evidence",
        broad_hits=broad_hits,
        hybrid_hits=broad_hits,
        limit=10,
    )

    routes = {route["name"]: route for route in plan["routes"]}
    assert plan["route_quota_profile"] == "cross_section_like"
    assert routes["candidate_context"]["limit"] == 2
    assert routes["requirement_context"]["limit"] == 5
    assert all(route["limit"] == 4 for route in plan["routes"] if route["name"] == "jd_context")


def test_smart_query_plan_detects_cross_section_intent_from_query_text() -> None:
    broad_hits = [
        _result("candidate-profile", "analyze/candidate_profile.json", 0.9, source_type="candidate_evidence"),
        _result("jd-018-req-003", "analyze/requirement_matrix.json", 0.8, source_type="requirement_evidence", jd_id="jd-018"),
    ]

    plan = build_smart_query_plan(
        "Compare the candidate profile across JD evidence and explain overall fit",
        broad_hits=broad_hits,
        hybrid_hits=broad_hits,
        limit=10,
    )

    assert plan["route_quota_profile"] == "cross_section_like"
    assert "cross_section_intent" in plan["reasons"]


def test_smart_query_plan_adds_cross_jd_requirement_route_for_multi_document() -> None:
    broad_hits = [
        _result("jd-006-req-009", "analyze/requirement_matrix.json", 0.9, source_type="requirement_evidence", jd_id="jd-006"),
        _result("jd-020-req-002", "analyze/requirement_matrix.json", 0.86, source_type="requirement_evidence", jd_id="jd-020"),
        _result("jd-018-req-003", "analyze/requirement_matrix.json", 0.8, source_type="requirement_evidence", jd_id="jd-018"),
        _result("candidate-profile", "analyze/candidate_profile.json", 0.7, source_type="candidate_evidence"),
    ]

    plan = build_smart_query_plan("multi document requirement evidence", broad_hits=broad_hits, hybrid_hits=broad_hits, limit=10)

    routes = [route for route in plan["routes"] if route["name"] == "requirement_cross_jd_context"]
    assert routes
    assert "cross JD" in routes[0]["query"]
    assert routes[0]["filters"] == {"source_type": "requirement_evidence"}
    assert routes[0]["limit"] >= 6


def test_smart_query_plan_routes_ranking_intent_even_without_ranking_broad_hit() -> None:
    broad_hits = [
        _result("jd-024-req-010", "analyze/requirement_matrix.json", 0.9, source_type="requirement_evidence", jd_id="jd-024"),
        _result("candidate-profile", "analyze/candidate_profile.json", 0.8, source_type="candidate_evidence"),
    ]

    plan = build_smart_query_plan("What ranking decision rationale explains JD-024 fit?", broad_hits=broad_hits, hybrid_hits=broad_hits, limit=10)

    routes = {route["name"]: route for route in plan["routes"]}
    assert "ranking_context" in routes
    assert routes["ranking_context"]["filters"]["source_type"] == "ranking_explanation"
    assert "ranking_intent" in plan["reasons"]


def test_smart_query_plan_uses_stronger_gap_and_ranking_terms() -> None:
    broad_hits = [
        _result("jd-019:gap", "evaluate/gap_maps.json", 0.9, source_type="gap_map", jd_id="jd-019"),
        _result("jd-019:ranking", "evaluate/ranking_explanations.json", 0.8, source_type="ranking_explanation", jd_id="jd-019"),
    ]

    plan = build_smart_query_plan("risk evidence", broad_hits=broad_hits, hybrid_hits=broad_hits, limit=10)
    routes = {route["name"]: route for route in plan["routes"]}

    assert "supporting evidence" in routes["gap_context"]["query"]
    assert "missing requirement" in routes["gap_context"]["query"]
    assert "decision summary" in routes["ranking_context"]["query"]
    assert "negative signal" in routes["ranking_context"]["query"]


def test_jd_candidate_selection_uses_score_and_source_balance_not_frequency_only() -> None:
    broad_hits = [
        _result("jd-021-req-001", "analyze/requirement_matrix.json", 0.31, source_type="requirement_evidence", jd_id="jd-021"),
        _result("jd-021-req-002", "analyze/requirement_matrix.json", 0.3, source_type="requirement_evidence", jd_id="jd-021"),
        _result("jd-015-req-014", "analyze/requirement_matrix.json", 0.95, source_type="requirement_evidence", jd_id="jd-015"),
        _result("jd-015:gap", "evaluate/gap_maps.json", 0.9, source_type="gap_map", jd_id="jd-015"),
        _result("jd-019-req-002", "analyze/requirement_matrix.json", 0.8, source_type="requirement_evidence", jd_id="jd-019"),
    ]

    plan = build_smart_query_plan("compare evidence", broad_hits=broad_hits, hybrid_hits=broad_hits, limit=10)

    jd_contexts = [route for route in plan["routes"] if route["name"] == "jd_context"]
    assert [route["filters"]["jd_id"] for route in jd_contexts][:2] == ["jd-015", "jd-019"]


def test_smart_query_plan_uses_hybrid_for_default_and_fallback_routes() -> None:
    plan = build_smart_query_plan(
        "plain precise requirement query",
        broad_hits=[],
        hybrid_hits=[],
        limit=10,
    )

    assert plan["routes"] == [{"name": "broad", "query": "plain precise requirement query", "retriever_mode": "hybrid", "limit": 10}]

    routed_plan = build_smart_query_plan(
        "有没有工具链风险",
        broad_hits=[],
        hybrid_hits=[],
        limit=10,
    )
    assert routed_plan["routes"][-1]["name"] == "broad_fallback"
    assert routed_plan["routes"][-1]["retriever_mode"] == "hybrid"


def test_query_report_records_route_level_ablation_for_expected_labels() -> None:
    retriever = _PlanRetriever(
        [
            _result("doc-a", "artifact-a.json", 0.9),
            _result("doc-b", "artifact-b.json", 0.8),
        ],
        {
            "strategy": "smart_router",
            "oracle_free": True,
            "route_reports": [
                {
                    "name": "hybrid_anchor",
                    "added_results": [{"source_id": "doc-a", "artifact_path": "artifact-a.json"}],
                },
                {
                    "name": "gap_context",
                    "added_results": [{"source_id": "doc-b", "artifact_path": "artifact-b.json"}],
                },
            ],
        },
    )

    report = evaluate_labeled_retrieval_queries(
        retriever=retriever,
        query_specs=[{"query_id": "ablation-001", "query": "query", "expected_chunks": ["doc-a", "doc-b"]}],
        k_values=[1, 2],
    )

    assert report["queries"][0]["route_ablation"]["expected_label_stages"] == {
        "doc-a": "hybrid_anchor",
        "doc-b": "gap_context",
    }


def test_smart_router_report_includes_query_plan_observability() -> None:
    chunks = [
        _chunk("candidate-profile", "candidate_evidence", "Candidate has LangGraph agent workflow evidence."),
        _chunk("jd-005-req-013", "requirement_evidence", "JD requires tool calling and evaluation.", jd_id="jd-005"),
        _chunk("jd-005:gap", "gap_map", "Gap map lists weak production operation evidence.", jd_id="jd-005"),
        _chunk("jd-005:ranking", "ranking_explanation", "Ranking explanation flags risk.", jd_id="jd-005"),
    ]
    retriever = SmartRouterRetriever.from_chunks(
        chunks,
        embedding_model=_DeterministicEmbeddingModel(),
        broad_limit=4,
        enable_support_gate=True,
    )

    report = evaluate_labeled_retrieval_queries(
        retriever=retriever,
        query_specs=[
            {
                "query_id": "smart-001",
                "query": "这个人 AI agent 工具链像不像，同时有什么风险？",
                "expected_chunks": ["candidate-profile", "jd-005:gap"],
                "expected_documents": [
                    {"label": "candidate-profile", "role": "primary"},
                    {"label": "jd-005:gap", "role": "supporting"},
                ],
            }
        ],
        k_values=[1, 3],
    )

    query = report["queries"][0]
    assert query["query_plan"]["strategy"] == "smart_router"
    assert query["query_plan"]["oracle_free"] is True
    assert query["query_plan"]["broad_observation"]["hit_count"] == 4
    route_names = [route["name"] for route in query["query_plan"]["routes"]]
    assert route_names[0] == "hybrid_anchor"
    assert "rewrite" in route_names
    assert route_names[-1] == "broad_fallback"
    assert query["query_plan"]["route_reports"][0]["name"] == "hybrid_anchor"


def test_support_gate_blocks_overlap_only_strong_claims() -> None:
    chunks = [
        _chunk("candidate-profile", "candidate_evidence", "Built FastAPI services and backend APIs."),
    ]
    retriever = SmartRouterRetriever.from_chunks(
        chunks,
        embedding_model=_DeterministicEmbeddingModel(),
        broad_limit=3,
        enable_support_gate=True,
    )

    retriever.search("Does FastAPI prove the candidate is a senior backend architect?", limit=3)

    support_gate = retriever.last_query_plan["support_gate"]  # type: ignore[index]
    assert support_gate["triggered"] is True
    assert support_gate["support_status"] == "overlap_only"
    assert support_gate["blocked_generator"] is True


def test_support_gate_allows_direct_evidence_for_strong_claims() -> None:
    chunks = [
        _chunk("candidate-profile", "candidate_evidence", "Led model training, fine tuning, and production operations."),
    ]
    retriever = SmartRouterRetriever.from_chunks(
        chunks,
        embedding_model=_DeterministicEmbeddingModel(),
        broad_limit=3,
        enable_support_gate=True,
    )

    retriever.search("Can we prove model training and fine tuning experience?", limit=3)

    support_gate = retriever.last_query_plan["support_gate"]  # type: ignore[index]
    assert support_gate["triggered"] is True
    assert support_gate["support_status"] == "supported_candidate"
    assert support_gate["blocked_generator"] is False


class _FakeRetriever:
    def __init__(self, results_by_query: dict[str, list[RetrievalResult]]) -> None:
        self.results_by_query = results_by_query
        self.calls: list[dict[str, object]] = []

    def search(self, query: str, *, limit: int = 5, **filters: object) -> list[RetrievalResult]:
        self.calls.append({"query": query, "limit": limit, "filters": filters})
        return self.results_by_query[query][:limit]


class _PlanRetriever:
    def __init__(self, results: list[RetrievalResult], query_plan: dict[str, object]) -> None:
        self.results = results
        self.last_query_plan = query_plan

    def search(self, query: str, *, limit: int = 5, **filters: object) -> list[RetrievalResult]:
        return self.results[:limit]


def _result(
    source_id: str,
    artifact_path: str,
    score: float,
    *,
    source_type: str = "candidate_evidence",
    jd_id: str | None = None,
) -> RetrievalResult:
    return RetrievalResult(
        text=f"Evidence from {source_id} in {artifact_path}",
        metadata={
            "source_type": source_type,
            "source_id": source_id,
            "artifact_path": artifact_path,
            "provenance_summary": f"provenance {source_id}",
            **({"jd_id": jd_id} if jd_id else {}),
        },
        score=score,
    )


def _chunk(source_id: str, source_type: str, text: str, *, jd_id: str | None = None) -> dict[str, object]:
    return {
        "text": text,
        "metadata": {
            "source_type": source_type,
            "source_id": source_id,
            "artifact_path": "artifact.json",
            "provenance_summary": source_id,
            **({"jd_id": jd_id} if jd_id else {}),
        },
    }


class _DeterministicEmbeddingModel:
    def embed(self, text: str) -> list[float]:
        return deterministic_embedding(text)
