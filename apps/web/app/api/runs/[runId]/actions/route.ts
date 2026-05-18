import { NextResponse } from "next/server";

import { RunActionError, startRunAction } from "../../../../../lib/run-actions";


type RouteContext = {
  params: Promise<{ runId: string }>;
};


export async function POST(request: Request, context: RouteContext) {
  let runId = "";
  try {
    runId = (await context.params).runId;
    const payload = (await request.json()) as { action?: "run" | "retry_full" | "resume_failed" };
    if (!payload.action || !["run", "retry_full", "resume_failed"].includes(payload.action)) {
      return NextResponse.json({ error: "不支持的运行操作。", code: "unsupported_action" }, { status: 400 });
    }
    return NextResponse.json(await startRunAction(runId, payload.action));
  } catch (error) {
    if (error instanceof RunActionError) {
      return NextResponse.json({ error: error.message, code: error.code }, { status: error.status });
    }
    const message = error instanceof Error ? error.message : "未知错误";
    console.error("[run-action] 启动本地运行失败", { runId, message });
    return NextResponse.json(
      {
        error: `启动本地运行失败：${message}`,
        code: "run_action_failed",
        phase: "backend_processing",
      },
      { status: 500 },
    );
  }
}
