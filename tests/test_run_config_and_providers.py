from __future__ import annotations

import json
from pathlib import Path
from urllib.error import HTTPError

import pytest

from shotguncv_cli.main import run
from shotguncv_agents.providers import OpenAIAnalyzeProvider, _chat_completion, _classify_cluster
from shotguncv_core.llm_observability import build_llm_summary
from shotguncv_core.pipeline import analyze_run, evaluate_run, generate_run, ingest_run


ROOT = Path(__file__).resolve().parents[1]


def test_cli_ingest_writes_default_openai_run_config(tmp_path: Path) -> None:
    run_dir = tmp_path / "cli-run"
    resume_path = ROOT / "fixtures" / "candidates" / "base_resume.md"
    jd_path = ROOT / "fixtures" / "jds" / "sample_batch.txt"

    exit_code, output = run(
        [
            "ingest",
            "--run-dir",
            str(run_dir),
            "--candidate-id",
            "cand-001",
            "--candidate-resume",
            str(resume_path),
            "--jd-file",
            str(jd_path),
        ]
    )

    assert exit_code == 0, output
    config_payload = json.loads((run_dir / "config" / "run_config.json").read_text(encoding="utf-8"))
    assert config_payload["analyzer"]["provider"] == "openai"
    assert config_payload["generator"]["provider"] == "openai"
    assert config_payload["judge"]["provider"] == "openai"
    assert config_payload["planner"]["provider"] == "openai"
    assert config_payload["openai"]["api_key_env"] == "OPENAI_API_KEY"
    assert config_payload["openai"]["env_file"] == ".env"


def test_cli_ingest_snapshots_explicit_run_config(tmp_path: Path) -> None:
    run_dir = tmp_path / "cli-run"
    resume_path = ROOT / "fixtures" / "candidates" / "base_resume.md"
    jd_path = ROOT / "fixtures" / "jds" / "sample_batch.txt"
    source_config = tmp_path / "openai-config.json"
    source_config.write_text(
        json.dumps(
            {
                "generator": {"provider": "openai", "model": "gpt-5.4-mini"},
                "judge": {"provider": "openai", "model": "gpt-5.4-mini"},
                "openai": {"base_url": "https://api.openai.com/v1", "api_key_env": "OPENAI_API_KEY"},
                "run_metadata": {"label": "internal-openai"},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    exit_code, output = run(
        [
            "ingest",
            "--run-dir",
            str(run_dir),
            "--candidate-id",
            "cand-001",
            "--candidate-resume",
            str(resume_path),
            "--jd-file",
            str(jd_path),
            "--config",
            str(source_config),
        ]
    )

    assert exit_code == 0, output
    snapshot_payload = json.loads((run_dir / "config" / "run_config.json").read_text(encoding="utf-8"))
    assert snapshot_payload["generator"]["provider"] == "openai"
    assert snapshot_payload["judge"]["provider"] == "openai"
    assert snapshot_payload["run_metadata"]["label"] == "internal-openai"


def test_classify_cluster_derives_generic_slug_and_falls_back_to_general() -> None:
    assert _classify_cluster("Senior Sales Manager", ["Own enterprise pipeline", "Coordinate regional forecasting"]) == (
        "senior-sales-manager"
    )
    assert _classify_cluster("   ", []) == "general"
    assert _classify_cluster("Legal Counsel", ["Draft commercial contracts"]) not in {"ai-product", "ai-operations"}


def test_openai_analyze_provider_derives_cluster_when_payload_omits_it(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "candidate_profile": {
            "experiences": ["Built reporting workflows"],
            "projects": ["Quarterly planning automation"],
            "skills": ["Python"],
            "industry_tags": ["Operations"],
            "strengths": ["Structured execution"],
            "constraints": [],
            "preferences": ["Generalist roles"],
            "core_claims": ["Delivered internal tools"],
            "verified_evidence": ["Delivered internal tools"],
            "missing_evidence_areas": [],
            "preferred_role_tracks": ["Operations analyst"],
        },
        "jd_profiles": [
            {
                "jd_id": "jd-001",
                "title": "Operations Analyst",
                "company": "Example Co",
                "responsibilities": ["Own KPI reporting"],
                "requirements": ["Excel", "SQL"],
                "keywords": ["excel", "sql"],
                "seniority": "mid",
                "bonuses": [],
                "risk_signals": [],
                "source_type": "text",
                "source_value": "Operations Analyst at Example Co",
            }
        ],
        "evidence_map": {},
    }
    monkeypatch.setattr("urllib.request.urlopen", _fake_openai_urlopen([json.dumps(payload, ensure_ascii=False)]))

    feedback = OpenAIAnalyzeProvider(
        model="gpt-5.4-mini",
        base_url="https://api.openai.com/v1",
        api_key="test-key",
        run_dir=tmp_path,
    ).analyze(
        candidate_id="cand-001",
        candidate_resume_path="resume.md",
        resume_text="- Built reporting workflows",
        jd_inputs=[
            {
                "source_type": "text",
                "source_value": "Operations Analyst at Example Co",
                "content": "=== JD ===\nTitle: Operations Analyst\nCompany: Example Co\nBody:\n- Own KPI reporting\n- Excel and SQL",
            }
        ],
    )

    assert feedback.jd_profiles[0].cluster == "operations-analyst"


def test_cli_generate_fails_with_helpful_message_when_run_config_missing(tmp_path: Path) -> None:
    exit_code, output = run(["generate", "--run-dir", str(tmp_path / "missing-run")])
    assert exit_code == 1
    assert "run_config.json" in output
    assert "ingest" in output.lower()


def test_generate_run_uses_openai_generator_from_run_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    run_dir = _prepare_analyzed_run(tmp_path)
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text("OPENAI_API_KEY=test-key\n", encoding="utf-8")
    _write_run_config(
        run_dir,
        {
            "generator": {"provider": "openai", "model": "gpt-5.4-mini"},
            "judge": {"provider": "deterministic", "model": ""},
            "openai": {"base_url": "https://api.openai.com/v1", "api_key_env": "OPENAI_API_KEY", "env_file": str(dotenv_path)},
            "run_metadata": {"label": "openai-generate"},
        },
    )
    monkeypatch.setattr("urllib.request.urlopen", _fake_openai_urlopen(["中文岗位摘要 1", "中文岗位摘要 2"]))

    generation = generate_run(run_dir)

    assert [variant.summary for variant in generation.variants] == ["中文岗位摘要 1", "中文岗位摘要 2"]
    assert all(variant.variant_type == "jd-specific" for variant in generation.variants)


def test_chat_completion_writes_success_log_and_usage(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "urllib.request.urlopen",
        _fake_openai_urlopen_payloads(
            [
                {
                    "choices": [{"message": {"content": "中文岗位摘要"}}],
                    "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
                }
            ]
        ),
    )

    result = _chat_completion(
        base_url="https://api.openai.com/v1",
        api_key="test-secret-key",
        model="gpt-5.4-mini",
        prompt="请输出中文摘要",
        expect_json=False,
        stage="generate",
        operation="generate.jd_summary",
        run_dir=tmp_path,
    )

    assert result.response_text == "中文岗位摘要"
    assert result.usage.prompt_tokens == 11
    records = _read_jsonl(tmp_path / "logs" / "llm_calls.jsonl")
    assert len(records) == 1
    assert records[0]["stage"] == "generate"
    assert records[0]["operation"] == "generate.jd_summary"
    assert records[0]["status"] == "success"
    assert records[0]["usage"] == {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18}
    assert records[0]["request_messages"][0]["role"] == "system"
    assert records[0]["request_messages"][1]["role"] == "user"


def test_chat_completion_records_retry_then_success(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "urllib.request.urlopen",
        _fake_openai_urlopen_payloads(
            [
                {
                    "choices": [{"message": {"content": "English summary only"}}],
                    "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
                },
                {
                    "choices": [{"message": {"content": "中文摘要通过校验"}}],
                    "usage": {"prompt_tokens": 6, "completion_tokens": 4, "total_tokens": 10},
                },
            ]
        ),
    )

    result = _chat_completion(
        base_url="https://api.openai.com/v1",
        api_key="test-secret-key",
        model="gpt-5.4-mini",
        prompt="请输出中文摘要",
        expect_json=False,
        stage="generate",
        operation="generate.jd_summary",
        run_dir=tmp_path,
    )

    assert result.response_text == "中文摘要通过校验"
    records = _read_jsonl(tmp_path / "logs" / "llm_calls.jsonl")
    assert [record["attempt"] for record in records] == [1, 2]
    assert [record["status"] for record in records] == ["failure", "success"]
    assert all(record["operation"] == "generate.jd_summary" for record in records)
    assert records[0]["error_type"] == "ValueError"
    assert "language check failed" in records[0]["error_message"]


def test_chat_completion_summary_uses_zero_tokens_when_usage_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "urllib.request.urlopen",
        _fake_openai_urlopen_payloads(
            [
                {
                    "choices": [
                        {
                            "message": {
                                "content": "{\"role_fit\":0.7,\"evidence_quality\":0.6,\"persuasiveness\":0.8,\"interview_pressure_risk\":0.2,\"application_worthiness\":\"apply\",\"must_fix_issues\":[],\"evidence_citations\":[\"Built prompt service\"],\"rewrite_opportunities\":[\"Add metrics\"],\"decision_rationale\":\"整体匹配。\"}"
                            }
                        }
                    ]
                }
            ]
        ),
    )

    result = _chat_completion(
        base_url="https://api.openai.com/v1",
        api_key="test-secret-key",
        model="gpt-5.4-mini",
        prompt="请输出 JSON",
        expect_json=True,
        json_language_fields={"decision_rationale"},
        stage="evaluate",
        operation="evaluate.assess",
        run_dir=tmp_path,
    )

    build_llm_summary(tmp_path)

    assert result.response_text.startswith("{")
    summary = json.loads((tmp_path / "logs" / "llm_summary.json").read_text(encoding="utf-8"))
    assert summary["totals"]["prompt_tokens"] == 0
    assert summary["totals"]["completion_tokens"] == 0
    assert summary["totals"]["total_tokens"] == 0
    assert summary["by_stage"]["evaluate"]["call_count"] == 1


def test_chat_completion_logs_failure_without_leaking_sensitive_headers(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def _boom(req, timeout=0):  # type: ignore[no-untyped-def]
        raise HTTPError(req.full_url, 401, "bad api key", None, None)

    monkeypatch.setattr("urllib.request.urlopen", _boom)

    with pytest.raises(HTTPError):
        _chat_completion(
            base_url="https://api.openai.com/v1",
            api_key="test-secret-key",
            model="gpt-5.4-mini",
            prompt="请输出中文摘要",
            expect_json=False,
            stage="generate",
            operation="generate.jd_summary",
            run_dir=tmp_path,
        )

    records = _read_jsonl(tmp_path / "logs" / "llm_calls.jsonl")
    assert len(records) == 1
    assert records[0]["status"] == "failure"
    assert records[0]["error_type"] == "HTTPError"
    serialized = json.dumps(records[0], ensure_ascii=False)
    assert "Authorization" not in serialized
    assert "test-secret-key" not in serialized


def test_evaluate_run_uses_openai_judge_rationale_from_run_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    run_dir = _prepare_analyzed_run(tmp_path)
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text("OPENAI_API_KEY=test-key\n", encoding="utf-8")
    _write_run_config(
        run_dir,
        {
            "generator": {"provider": "deterministic", "model": ""},
            "judge": {"provider": "openai", "model": "gpt-5.4-mini"},
            "openai": {"base_url": "https://api.openai.com/v1", "api_key_env": "OPENAI_API_KEY", "env_file": str(dotenv_path)},
            "run_metadata": {"label": "openai-evaluate"},
        },
    )
    generate_run(run_dir)
    monkeypatch.setattr(
        "urllib.request.urlopen",
        _fake_openai_urlopen(
            [
                "璇勫鐞嗙敱 1",
                "{\"role_fit\":0.81,\"evidence_quality\":0.78,\"persuasiveness\":0.75,\"interview_pressure_risk\":0.31,\"application_worthiness\":\"apply\",\"must_fix_issues\":[],\"evidence_citations\":[\"e1\"],\"rewrite_opportunities\":[\"r1\"],\"decision_rationale\":\"ok\"}",
                "璇勫鐞嗙敱 2",
                "{\"role_fit\":0.81,\"evidence_quality\":0.78,\"persuasiveness\":0.75,\"interview_pressure_risk\":0.31,\"application_worthiness\":\"apply\",\"must_fix_issues\":[],\"evidence_citations\":[\"e1\"],\"rewrite_opportunities\":[\"r1\"],\"decision_rationale\":\"ok\"}",
            ]
        ),
    )

    evaluation = evaluate_run(run_dir)

    assert len(evaluation.scorecards) == 2
    assert any(card.judge_rationale for card in evaluation.scorecards)


def test_evaluate_run_accepts_english_evidence_and_rewrite_text_in_judge_json(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    run_dir = _prepare_analyzed_run(tmp_path)
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text("OPENAI_API_KEY=test-key\n", encoding="utf-8")
    _write_run_config(
        run_dir,
        {
            "generator": {"provider": "deterministic", "model": ""},
            "judge": {"provider": "openai", "model": "gpt-5.4-mini"},
            "openai": {"base_url": "https://api.openai.com/v1", "api_key_env": "OPENAI_API_KEY", "env_file": str(dotenv_path)},
            "run_metadata": {"label": "openai-evaluate-english-json"},
        },
    )
    generate_run(run_dir)
    monkeypatch.setattr(
        "urllib.request.urlopen",
        _fake_openai_urlopen(
            [
                "中文评审理由 1",
                "{\"role_fit\":0.81,\"evidence_quality\":0.78,\"persuasiveness\":0.75,\"interview_pressure_risk\":0.31,\"application_worthiness\":\"apply\",\"must_fix_issues\":[],\"evidence_citations\":[\"Built prompt routing service for internal ops\"],\"rewrite_opportunities\":[\"Add metrics story to top bullet\"],\"decision_rationale\":\"整体较匹配，建议投递。\"}",
                "中文评审理由 2",
                "{\"role_fit\":0.81,\"evidence_quality\":0.78,\"persuasiveness\":0.75,\"interview_pressure_risk\":0.31,\"application_worthiness\":\"apply\",\"must_fix_issues\":[],\"evidence_citations\":[\"Built prompt routing service for internal ops\"],\"rewrite_opportunities\":[\"Add metrics story to top bullet\"],\"decision_rationale\":\"整体较匹配，建议投递。\"}",
            ]
        ),
    )

    evaluation = evaluate_run(run_dir)

    assert len(evaluation.llm_assessments) == len(evaluation.scorecards)
    assert all("llm_assessment_missing" not in card.guardrail_flags for card in evaluation.scorecards)
    assert any(
        assessment.evidence_citations == ["Built prompt routing service for internal ops"]
        for assessment in evaluation.llm_assessments
    )


def test_generate_run_raises_clear_error_when_openai_api_key_missing(tmp_path: Path) -> None:
    run_dir = _prepare_analyzed_run(tmp_path)
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text("OTHER_KEY=abc\n", encoding="utf-8")
    _write_run_config(
        run_dir,
        {
            "generator": {"provider": "openai", "model": "gpt-5.4-mini"},
            "judge": {"provider": "deterministic", "model": ""},
            "openai": {"base_url": "https://api.openai.com/v1", "api_key_env": "MISSING_OPENAI_KEY", "env_file": str(dotenv_path)},
            "run_metadata": {"label": "openai-generate"},
        },
    )

    with pytest.raises(RuntimeError) as excinfo:
        generate_run(run_dir)

    message = str(excinfo.value)
    assert "generate" in message
    assert "openai" in message.lower()
    assert "gpt-5.4-mini" in message
    assert "MISSING_OPENAI_KEY" in message
    assert str(dotenv_path) in message


def test_generate_run_does_not_fallback_to_system_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    run_dir = _prepare_analyzed_run(tmp_path)
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text("OTHER_KEY=abc\n", encoding="utf-8")
    _write_run_config(
        run_dir,
        {
            "generator": {"provider": "openai", "model": "gpt-5.4-mini"},
            "judge": {"provider": "deterministic", "model": ""},
            "openai": {"base_url": "https://api.openai.com/v1", "api_key_env": "OPENAI_API_KEY", "env_file": str(dotenv_path)},
            "run_metadata": {"label": "openai-generate"},
        },
    )
    monkeypatch.setenv("OPENAI_API_KEY", "system-key-should-not-be-used")

    with pytest.raises(RuntimeError) as excinfo:
        generate_run(run_dir)

    message = str(excinfo.value)
    assert "OPENAI_API_KEY" in message
    assert str(dotenv_path) in message


def test_generate_run_uses_default_model_when_config_and_env_model_empty(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    run_dir = _prepare_analyzed_run(tmp_path)
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text("OPENAI_API_KEY=test-key\n", encoding="utf-8")
    _write_run_config(
        run_dir,
        {
            "generator": {"provider": "openai", "model": ""},
            "judge": {"provider": "deterministic", "model": ""},
            "openai": {"base_url": None, "api_key_env": "OPENAI_API_KEY", "env_file": str(dotenv_path)},
            "run_metadata": {"label": "openai-generate-default-model"},
        },
    )
    capture: dict[str, str] = {}
    monkeypatch.setattr(
        "urllib.request.urlopen",
        _fake_openai_urlopen_capture(messages=["中文岗位摘要 1", "中文岗位摘要 2"], capture=capture),
    )

    generate_run(run_dir)

    assert capture["last_model"] == "gpt-5.4-mini"
    assert capture["last_url"] == "https://api.openai.com/v1/chat/completions"
    assert capture["last_system_prompt"]


def test_generate_run_uses_openai_compatible_base_url_and_model_from_env_when_config_model_empty(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    run_dir = _prepare_analyzed_run(tmp_path)
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text(
        "OPENAI_API_KEY=test-key\nOPENAI_MODEL=deepseek-chat\nOPENAI_BASE_URL=https://openrouter.ai/api/v1\n",
        encoding="utf-8",
    )
    _write_run_config(
        run_dir,
        {
            "generator": {"provider": "openai", "model": ""},
            "judge": {"provider": "deterministic", "model": ""},
            "openai": {"base_url": None, "api_key_env": "OPENAI_API_KEY", "env_file": str(dotenv_path)},
            "run_metadata": {"label": "openai-compatible"},
        },
    )
    capture: dict[str, str] = {}
    monkeypatch.setattr(
        "urllib.request.urlopen",
        _fake_openai_urlopen_capture(messages=["中文岗位摘要 1", "中文岗位摘要 2"], capture=capture),
    )

    generate_run(run_dir)

    assert capture["last_model"] == "deepseek-chat"
    assert capture["last_url"] == "https://openrouter.ai/api/v1/chat/completions"


def test_generate_run_accepts_openai_compatible_provider_alias(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    run_dir = _prepare_analyzed_run(tmp_path)
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text("OPENAI_API_KEY=test-key\nOPENAI_MODEL=qwen-max\n", encoding="utf-8")
    _write_run_config(
        run_dir,
        {
            "generator": {"provider": "openai-compatible", "model": ""},
            "judge": {"provider": "deterministic", "model": ""},
            "openai": {"base_url": None, "api_key_env": "OPENAI_API_KEY", "env_file": str(dotenv_path)},
            "run_metadata": {"label": "openai-compatible-alias"},
        },
    )
    capture: dict[str, str] = {}
    monkeypatch.setattr(
        "urllib.request.urlopen",
        _fake_openai_urlopen_capture(messages=["中文岗位摘要 1", "中文岗位摘要 2"], capture=capture),
    )

    generate_run(run_dir)
    assert capture["last_model"] == "qwen-max"


def test_generate_run_env_overrides_model_and_base_url_over_run_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    run_dir = _prepare_analyzed_run(tmp_path)
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text(
        "OPENAI_API_KEY=test-key\nOPENAI_MODEL=env-model\nOPENAI_BASE_URL=https://env.example.com/v1\n",
        encoding="utf-8",
    )
    _write_run_config(
        run_dir,
        {
            "generator": {"provider": "openai", "model": "config-model"},
            "judge": {"provider": "deterministic", "model": ""},
            "openai": {"base_url": "https://config.example.com/v1", "api_key_env": "OPENAI_API_KEY", "env_file": str(dotenv_path)},
            "run_metadata": {"label": "env-overrides"},
        },
    )
    capture: dict[str, str] = {}
    monkeypatch.setattr(
        "urllib.request.urlopen",
        _fake_openai_urlopen_capture(messages=["中文岗位摘要 1", "中文岗位摘要 2"], capture=capture),
    )

    generate_run(run_dir)
    assert capture["last_model"] == "env-model"
    assert capture["last_url"] == "https://env.example.com/v1/chat/completions"


def test_generate_run_ignores_env_provider_override_when_run_config_is_deterministic(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    run_dir = _prepare_analyzed_run(tmp_path)
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text(
        "SHOTGUNCV_GENERATOR_PROVIDER=openai\nOPENAI_API_KEY=test-key\nOPENAI_MODEL=override-provider-model\n",
        encoding="utf-8",
    )
    _write_run_config(
        run_dir,
        {
            "generator": {"provider": "deterministic", "model": ""},
            "judge": {"provider": "deterministic", "model": ""},
            "openai": {"base_url": None, "api_key_env": "OPENAI_API_KEY", "env_file": str(dotenv_path)},
            "run_metadata": {"label": "provider-override"},
        },
    )

    def _unexpected_openai_call(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("deterministic provider should not be overridden by .env")

    monkeypatch.setattr("urllib.request.urlopen", _unexpected_openai_call)

    generation = generate_run(run_dir)
    assert generation.variants[0].summary.startswith("LLM Product Engineer variant focused on")


def test_evaluate_run_ignores_env_provider_override_when_run_config_is_deterministic(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    run_dir = _prepare_analyzed_run(tmp_path)
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text(
        "SHOTGUNCV_JUDGE_PROVIDER=openai\nOPENAI_API_KEY=test-key\nOPENAI_MODEL=override-judge-model\n",
        encoding="utf-8",
    )
    _write_run_config(
        run_dir,
        {
            "generator": {"provider": "deterministic", "model": ""},
            "judge": {"provider": "deterministic", "model": ""},
            "openai": {"base_url": None, "api_key_env": "OPENAI_API_KEY", "env_file": str(dotenv_path)},
            "run_metadata": {"label": "judge-provider-override"},
        },
    )
    generate_run(run_dir)

    def _unexpected_openai_call(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("deterministic judge should not be overridden by .env")

    monkeypatch.setattr("urllib.request.urlopen", _unexpected_openai_call)

    evaluation = evaluate_run(run_dir)
    assert evaluation.scorecards[0].judge_rationale.startswith("jd-specific variant aligns")


def test_evaluate_run_uses_resolved_runtime_provider_and_model_in_fallback_scorecards(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    run_dir = _prepare_analyzed_run(tmp_path)
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text(
        "OPENAI_API_KEY=test-key\nOPENAI_MODEL=qwen-eval-model\nOPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1\n",
        encoding="utf-8",
    )
    _write_run_config(
        run_dir,
        {
            "generator": {"provider": "deterministic", "model": ""},
            "judge": {"provider": "openai-compatible", "model": ""},
            "openai": {"base_url": None, "api_key_env": "OPENAI_API_KEY", "env_file": str(dotenv_path)},
            "run_metadata": {"label": "openai-compatible-evaluate-fallback"},
        },
    )
    generate_run(run_dir)
    monkeypatch.setattr(
        "urllib.request.urlopen",
        _fake_openai_urlopen(
            [
                "中文评审理由 1",
                "not-json-response",
                "中文评审理由 2",
                "not-json-response",
            ]
        ),
    )

    evaluation = evaluate_run(run_dir)
    failures = json.loads((run_dir / "evaluate" / "llm_failures.json").read_text(encoding="utf-8"))

    assert failures
    assert all(item["provider"] == "openai-compatible" for item in failures)
    assert all(item["model"] == "qwen-eval-model" for item in failures)
    assert any(card.final_decision_source == "guardrail-fallback" for card in evaluation.scorecards)
    assert all(card.provider == "openai-compatible" for card in evaluation.scorecards)
    assert all(card.model == "qwen-eval-model" for card in evaluation.scorecards)


def _prepare_analyzed_run(tmp_path: Path) -> Path:
    run_dir = tmp_path / "run"
    ingest_run(
        run_dir=run_dir,
        candidate_id="cand-001",
        candidate_resume_path=ROOT / "fixtures" / "candidates" / "base_resume.md",
        jd_sources=[ROOT / "fixtures" / "jds" / "sample_batch.txt"],
    )
    analyze_run(run_dir)
    return run_dir


def _write_run_config(run_dir: Path, payload: dict[str, object]) -> None:
    config_dir = run_dir / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "run_config.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _fake_openai_urlopen(messages: list[str]):
    responses = iter(messages)

    class _Response:
        def __init__(self, content: str) -> None:
            self._payload = json.dumps({"choices": [{"message": {"content": content}}]}, ensure_ascii=False).encode("utf-8")

        def read(self) -> bytes:
            return self._payload

        def __enter__(self) -> "_Response":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    def _urlopen(req, timeout=0):  # type: ignore[no-untyped-def]
        if timeout == 0:
            raise HTTPError("https://api.openai.com/v1/chat/completions", 500, "missing timeout", None, None)
        return _Response(next(responses))

    return _urlopen


def _fake_openai_urlopen_capture(messages: list[str], capture: dict[str, str]):
    responses = iter(messages)

    class _Response:
        def __init__(self, content: str) -> None:
            self._payload = json.dumps({"choices": [{"message": {"content": content}}]}, ensure_ascii=False).encode("utf-8")

        def read(self) -> bytes:
            return self._payload

        def __enter__(self) -> "_Response":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    def _urlopen(req, timeout=0):  # type: ignore[no-untyped-def]
        payload = json.loads(req.data.decode("utf-8"))
        capture["last_model"] = payload["model"]
        capture["last_url"] = req.full_url
        capture["last_system_prompt"] = payload["messages"][0]["content"]
        if timeout == 0:
            raise HTTPError("https://api.openai.com/v1/chat/completions", 500, "missing timeout", None, None)
        return _Response(next(responses))

    return _urlopen


def _fake_openai_urlopen_payloads(payloads: list[dict[str, object]]):
    responses = iter(payloads)

    class _Response:
        def __init__(self, payload: dict[str, object]) -> None:
            self._payload = json.dumps(payload, ensure_ascii=False).encode("utf-8")

        def read(self) -> bytes:
            return self._payload

        def __enter__(self) -> "_Response":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    def _urlopen(req, timeout=0):  # type: ignore[no-untyped-def]
        if timeout == 0:
            raise HTTPError("https://api.openai.com/v1/chat/completions", 500, "missing timeout", None, None)
        return _Response(next(responses))

    return _urlopen


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
