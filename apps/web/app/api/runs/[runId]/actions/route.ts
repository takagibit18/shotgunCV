import { NextResponse } from "next/server";

import { RunActionError, startRunAction } from "../../../../../lib/run-actions";


type RouteContext = {
  params: Promise<{ runId: string }>;
};


export async function POST(request: Request, context: RouteContext) {
  try {
    const { runId } = await context.params;
    const payload = (await request.json()) as { action?: "run" | "retry_full" | "resume_failed" };
    if (!payload.action || !["run", "retry_full", "resume_failed"].includes(payload.action)) {
      return NextResponse.json({ error: "Unsupported run action.", code: "unsupported_action" }, { status: 400 });
    }
    return NextResponse.json(await startRunAction(runId, payload.action));
  } catch (error) {
    if (error instanceof RunActionError) {
      return NextResponse.json({ error: error.message, code: error.code }, { status: error.status });
    }
    return NextResponse.json({ error: "Failed to start run action.", code: "run_action_failed" }, { status: 500 });
  }
}
