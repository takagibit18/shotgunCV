import { NextResponse } from "next/server";

import { deleteRun, RunActionError } from "../../../../lib/run-actions";


type RouteContext = {
  params: Promise<{ runId: string }>;
};


export async function DELETE(_request: Request, context: RouteContext) {
  try {
    const { runId } = await context.params;
    return NextResponse.json(await deleteRun(runId));
  } catch (error) {
    if (error instanceof RunActionError) {
      return NextResponse.json({ error: error.message, code: error.code }, { status: error.status });
    }
    return NextResponse.json({ error: "Failed to delete run.", code: "delete_failed" }, { status: 500 });
  }
}
