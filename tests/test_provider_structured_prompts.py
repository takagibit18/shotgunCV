from __future__ import annotations

import pytest


def test_structured_json_parser_rejects_non_object_payload() -> None:
    from shotguncv_agents.structured import parse_json_object

    with pytest.raises(ValueError, match="JSON object"):
        parse_json_object("[1, 2, 3]")


def test_provider_system_prompt_keeps_json_and_chinese_constraints() -> None:
    from shotguncv_agents.prompts import build_system_prompt

    prompt = build_system_prompt(expect_json=True)

    assert "JSON" in prompt
    assert "简体中文" in prompt
    assert "Markdown" in prompt
