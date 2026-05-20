from __future__ import annotations


def build_system_prompt(expect_json: bool) -> str:
    base = (
        "你是简历投递策略助手。必须使用简体中文进行自然语言输出。"
        "禁止输出英文完整句子。仅允许必要的英文缩写、字段键名、ID。"
    )
    if expect_json:
        return (
            base
            + "你必须只输出一个合法 JSON 对象。不要输出 Markdown 代码块、前后缀说明或多余文本。"
            + "JSON 的键名保持要求，值中的自然语言必须是简体中文。"
        )
    return base + "只输出纯文本，不要添加额外解释。"
