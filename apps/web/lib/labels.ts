export const STATUS_LABELS: Record<string, string> = {
  draft: "草稿",
  queued: "排队中",
  running: "运行中",
  done: "已完成",
  failed: "失败",
  partial_failed: "部分未完成",
  "ingest-ready": "待导入",
};

export const FILTER_STATUS_LABELS: Record<string, string> = {
  draft: STATUS_LABELS.draft,
  queued: STATUS_LABELS.queued,
  running: STATUS_LABELS.running,
  done: STATUS_LABELS.done,
  failed: STATUS_LABELS.failed,
  partial_failed: STATUS_LABELS.partial_failed,
};

export const STAGE_LABELS: Record<string, string> = {
  ingest: "解析输入",
  analyze: "结构化分析",
  generate: "生成简历",
  evaluate: "匹配评分",
  plan: "投递策略",
  report: "报告",
};
