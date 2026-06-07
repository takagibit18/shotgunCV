const TOKEN_LABELS: Record<string, string> = {
  hard_gate_missing: "硬性要求缺少证据",
  needs_review: "需要复核",
  manual_review: "人工复核",
  preflight_gate: "前置检查",
  preflight: "前置检查",
  llm_assessment_missing: "模型评估结果缺失",
  apply: "建议投递",
  hold: "暂缓",
  skip: "跳过",
  review: "复核后决定",
  blocked: "已阻断",
  unknown: "未知",
};

const HYPHEN_TOKEN_LABELS: Record<string, string> = {
  "preflight-gate": "前置检查",
  "llm-primary": "主模型判断",
};

const WINDOWS_ABSOLUTE_PATH = /[A-Z]:\\[^\s`，。；;）)]+/gi;
const POSIX_ABSOLUTE_PATH = /(?:^|\s)\/(?:Users|home|tmp|var|mnt|opt|workspace|app|src)\/[^\s`，。；;）)]+/gi;
const RELATIVE_ARTIFACT_PATH = /\b(?:input_files|fixtures|runs|analyze|generate|evaluate|plan|report|review|config)[\\/][^\s`，。；;）)]+/gi;

export function formatDecisionLabel(value: string): string {
  const trimmed = value.trim();
  if (!trimmed) {
    return "未提供";
  }
  const labels: Record<string, string> = {
    ...TOKEN_LABELS,
    "建议优先投递": "建议优先投递",
    "建议优化后投递": "建议优化后投递",
    "建议立即投递": "建议立即投递",
    "强烈建议投递": "强烈建议投递",
    "推荐投递": "推荐投递",
    "优化后投递": "优化后投递",
  };
  return labels[trimmed] ?? sanitizeUserFacingText(trimmed);
}

export function formatGateStatusLabel(value: string): string {
  const labels: Record<string, string> = {
    pass: "通过",
    blocked: "阻断",
    needs_review: "需复核",
    legacy: "历史结果",
  };
  return labels[value] ?? sanitizeUserFacingText(value);
}

export function formatRunDisplayName(value: string | null | undefined): string {
  const trimmed = (value ?? "").trim();
  if (!trimmed || /^[a-z0-9][a-z0-9._-]*$/i.test(trimmed)) {
    return "未命名投递";
  }
  return sanitizeUserFacingText(trimmed);
}

export function sanitizeUserFacingText(value: string): string {
  if (!value) {
    return value;
  }

  let text = value
    .replace(/CLI 运行失败，退出码\s*\d+。输出：Input directory `?[^`。]+`? does not contain supported input files\.?/gi, "本地运行未完成：简历目录没有可识别文件。请重新上传可读取的简历，或补充手动文本后重试。")
    .replace(/CLI 运行失败，退出码\s*\d+。输出：At least one CV input must contain extractable text\.?/gi, "本地运行未完成：简历无法提取文本。请上传可复制的 PDF、Markdown 或文本简历，或补充手动文本后重试。")
    .replace(/(\d+)\s+JD input could not be parsed and was excluded\.?/gi, "$1 个岗位输入解析失败，已从本次评估中排除。请检查对应 JD 文本或文件后重试。")
    .replace(/Evaluation used fallback or scorecard data was incomplete\.?/gi, "评估使用备用结果，建议复核分数和证据。")
    .replace(/Evidence mapping is limited\.?/gi, "证据映射有限。")
    .replace(/Keep education and employer facts unchanged\.?/gi, "保持教育和雇主事实不变。")
    .replace(/Do not fabricate certificates\.?/gi, "不要编造证书。")
    .replace(/\bSource:\s*/gi, "证据来源：")
    .replace(/\bRun directory:\s*[^\n\r]+/gi, "本地运行目录已隐藏")
    .replace(/\bCandidate:\s*`?([^`\n\r]+)`?/gi, "候选人：$1")
    .replace(/\bApply decision:\s*/gi, "投递建议：")
    .replace(/\bWhy worth \/ not worth:\s*/gi, "判断依据：")
    .replace(/\bEvidence that holds:\s*/gi, "关键证据：")
    .replace(/\bInterview danger points:\s*/gi, "面试风险点：")
    .replace(/\bIf only revise 3 resume items:\s*/gi, "优先修改项：")
    .replace(/\bFinal score:\s*/gi, "最终得分：")
    .replace(/\bconfidence\b/gi, "置信度")
    .replace(/\bvia\b/gi, "依据");

  text = text
    .replace(WINDOWS_ABSOLUTE_PATH, "本地文件")
    .replace(POSIX_ABSOLUTE_PATH, " 本地文件")
    .replace(RELATIVE_ARTIFACT_PATH, "本地产物");

  text = text.replace(/\b[a-z]+(?:_[a-z0-9]+)+\b/g, (token) => TOKEN_LABELS[token] ?? token.replace(/_/g, " "));
  text = text.replace(/\b[a-z]+(?:-[a-z0-9]+)+\b/g, (token) => HYPHEN_TOKEN_LABELS[token] ?? token);
  text = text.replace(/：\s*:/g, "：").replace(/:\s*/g, "：");
  return text.replace(/\s+/g, " ").trim();
}

export function sanitizeUserFacingList(values: string[]): string[] {
  return values.map(sanitizeUserFacingText).filter(Boolean);
}
