export const STATUS_LABELS: Record<string, string> = {
  draft: "草稿",
  queued: "排队中",
  running: "运行中",
  done: "已完成",
  failed: "失败",
  "ingest-ready": "导入就绪",
};

export const FILTER_STATUS_LABELS: Record<string, string> = {
  draft: STATUS_LABELS.draft,
  queued: STATUS_LABELS.queued,
  running: STATUS_LABELS.running,
  done: STATUS_LABELS.done,
  failed: STATUS_LABELS.failed,
};

export const STAGE_LABELS: Record<string, string> = {
  ingest: "导入",
  analyze: "分析",
  generate: "生成",
  evaluate: "评估",
  plan: "计划",
  report: "报告",
};
