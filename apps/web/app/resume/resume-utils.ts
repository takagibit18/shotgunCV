export function formatStatus(status: string): string {
  const labels: Record<string, string> = {
    draft: "草稿",
    queued: "排队中",
    running: "运行中",
    done: "已完成",
    failed: "失败",
    "ingest-ready": "导入就绪",
  };
  return labels[status] ?? status;
}

export function formatFilterStatus(status: string): string {
  const labels: Record<string, string> = {
    draft: "草稿",
    queued: "排队中",
    running: "运行中",
    done: "已完成",
    failed: "失败",
  };
  return labels[status] ?? status;
}

export function formatGateStatus(status: string): string {
  const labels: Record<string, string> = {
    pass: "通过",
    blocked: "阻断",
    needs_review: "需复核",
    legacy: "历史产物",
  };
  return labels[status] ?? status;
}

export function buildStatusChip(status: string): string {
  const map: Record<string, string> = {
    done: "status-chip success",
    failed: "status-chip danger",
    running: "status-chip info",
    queued: "status-chip info",
  };
  return map[status] ?? "status-chip";
}

export function buildConstraintClassName(category: string): string {
  const map: Record<string, string> = {
    "禁止编造缺口": "status-chip danger",
    "待核实模拟补强": "status-chip warning",
  };
  return map[category] ?? "status-chip success";
}
