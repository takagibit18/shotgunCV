import { NextResponse } from "next/server";

import { deleteRun, RunActionError } from "../../../../lib/run-actions";
import { loadRunStatusSnapshot } from "../../../../lib/runs";


type RouteContext = {
  params: Promise<{ runId: string }>;
};

export async function GET(_request: Request, context: RouteContext) {
  try {
    const { runId } = await context.params;
    const snapshot = await loadRunStatusSnapshot(runId);
    return NextResponse.json({
      ...snapshot,
      updatedAt: new Date().toISOString(),
    });
  } catch {
    return NextResponse.json({ error: "读取运行状态失败，请稍后重试。", code: "run_status_read_failed" }, { status: 500 });
  }
}


export async function DELETE(_request: Request, context: RouteContext) {
  try {
    const { runId } = await context.params;
    return NextResponse.json(await deleteRun(runId));
  } catch (error) {
    if (error instanceof RunActionError) {
      return NextResponse.json({ error: error.message, code: error.code }, { status: error.status });
    }
    return NextResponse.json({ error: "删除运行批次失败。", code: "delete_failed" }, { status: 500 });
  }
}
