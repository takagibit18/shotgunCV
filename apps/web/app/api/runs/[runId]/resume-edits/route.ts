import { NextResponse } from "next/server";

import {
  saveUserResumeEdit,
  type ResumeFieldStatus,
} from "../../../../../lib/runs";


type RouteContext = {
  params: Promise<{ runId: string }>;
};

const FIELD_STATUSES: ResumeFieldStatus[] = ["confirmed", "to_verify"];


export async function POST(request: Request, context: RouteContext) {
  try {
    const { runId } = await context.params;
    const payload = (await request.json()) as {
      resumeId?: string;
      documentPatch?: unknown;
      fieldStatuses?: Record<string, ResumeFieldStatus>;
      reset?: boolean;
    };
    if (!payload.resumeId) {
      return NextResponse.json(
        { error: "简历编辑信息不完整。", code: "invalid_resume_edit" },
        { status: 400 },
      );
    }
    if (
      payload.fieldStatuses &&
      Object.values(payload.fieldStatuses).some((status) => !FIELD_STATUSES.includes(status))
    ) {
      return NextResponse.json(
        { error: "字段确认状态无效。", code: "invalid_resume_field_status" },
        { status: 400 },
      );
    }
    const documentPatch =
      payload.documentPatch && typeof payload.documentPatch === "object" && !Array.isArray(payload.documentPatch)
        ? payload.documentPatch
        : {};
    const artifact = await saveUserResumeEdit(runId, {
      resumeId: payload.resumeId,
      documentPatch,
      fieldStatuses: payload.fieldStatuses,
      reset: payload.reset,
    });
    return NextResponse.json({
      runId,
      savedCount: artifact.edits.length,
      artifact: {
        schemaVersion: artifact.schema_version,
        editCount: artifact.edits.length,
      },
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "保存简历编辑失败。";
    return NextResponse.json({ error: message, code: "resume_edit_failed" }, { status: 500 });
  }
}
