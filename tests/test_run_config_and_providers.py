from __future__ import annotations

import json
from pathlib import Path
from urllib.error import HTTPError

import pytest

from shotguncv_cli.main import run
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
    monkeypatch.setattr("urllib.request.urlopen", _fake_openai_urlopen(["岗位簇摘要", "岗位定制摘要", "岗位定制摘要"]))

    generation = generate_run(run_dir)

    assert generation.variants[0].summary == "岗位簇摘要"
    assert any(variant.summary == "岗位定制摘要" for variant in generation.variants)


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
                "评审理由 1",
                "{\"role_fit\":0.81,\"evidence_quality\":0.78,\"persuasiveness\":0.75,\"interview_pressure_risk\":0.31,\"application_worthiness\":\"apply\",\"must_fix_issues\":[],\"evidence_citations\":[\"证据1\"],\"rewrite_opportunities\":[\"优化点1\"],\"decision_rationale\":\"匹配度较好\"}",
                "评审理由 2",
                "{\"role_fit\":0.81,\"evidence_quality\":0.78,\"persuasiveness\":0.75,\"interview_pressure_risk\":0.31,\"application_worthiness\":\"apply\",\"must_fix_issues\":[],\"evidence_citations\":[\"证据1\"],\"rewrite_opportunities\":[\"优化点1\"],\"decision_rationale\":\"匹配度较好\"}",
                "评审理由 3",
                "{\"role_fit\":0.81,\"evidence_quality\":0.78,\"persuasiveness\":0.75,\"interview_pressure_risk\":0.31,\"application_worthiness\":\"apply\",\"must_fix_issues\":[],\"evidence_citations\":[\"证据1\"],\"rewrite_opportunities\":[\"优化点1\"],\"decision_rationale\":\"匹配度较好\"}",
                "评审理由 4",
                "{\"role_fit\":0.81,\"evidence_quality\":0.78,\"persuasiveness\":0.75,\"interview_pressure_risk\":0.31,\"application_worthiness\":\"apply\",\"must_fix_issues\":[],\"evidence_citations\":[\"证据1\"],\"rewrite_opportunities\":[\"优化点1\"],\"decision_rationale\":\"匹配度较好\"}",
                "评审理由 5",
                "{\"role_fit\":0.81,\"evidence_quality\":0.78,\"persuasiveness\":0.75,\"interview_pressure_risk\":0.31,\"application_worthiness\":\"apply\",\"must_fix_issues\":[],\"evidence_citations\":[\"证据1\"],\"rewrite_opportunities\":[\"优化点1\"],\"decision_rationale\":\"匹配度较好\"}",
                "评审理由 6",
                "{\"role_fit\":0.81,\"evidence_quality\":0.78,\"persuasiveness\":0.75,\"interview_pressure_risk\":0.31,\"application_worthiness\":\"apply\",\"must_fix_issues\":[],\"evidence_citations\":[\"证据1\"],\"rewrite_opportunities\":[\"优化点1\"],\"decision_rationale\":\"匹配度较好\"}",
            ]
        ),
    )

    evaluation = evaluate_run(run_dir)

    assert evaluation.scorecards[0].judge_rationale == "评审理由 1"
    assert any(card.judge_rationale == "评审理由 6" for card in evaluation.scorecards)


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
        _fake_openai_urlopen_capture(messages=["岗位簇摘要", "岗位定制摘要", "岗位定制摘要"], capture=capture),
    )

    generate_run(run_dir)

    assert capture["last_model"] == "gpt-5.4-mini"
    assert capture["last_url"] == "https://api.openai.com/v1/chat/completions"
    assert "简体中文" in capture["last_system_prompt"]


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
        _fake_openai_urlopen_capture(messages=["岗位簇摘要", "岗位定制摘要", "岗位定制摘要"], capture=capture),
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
        _fake_openai_urlopen_capture(messages=["岗位簇摘要", "岗位定制摘要", "岗位定制摘要"], capture=capture),
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
        _fake_openai_urlopen_capture(messages=["岗位簇摘要", "岗位定制摘要", "岗位定制摘要"], capture=capture),
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
    assert generation.variants[0].summary.startswith("ai-product cluster resume emphasizing")


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
    assert evaluation.scorecards[0].judge_rationale.startswith("cluster variant aligns")


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
