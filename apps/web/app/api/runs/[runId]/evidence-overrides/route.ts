import { NextResponse } from "next/server";

import {
  saveUserEvidenceOverride,
  type UserEvidenceOverrideAction,
} from "../../../../../lib/runs";


type RouteContext = {
  params: Promise<{ runId: string }>;
};

const ACTIONS: UserEvidenceOverrideAction[] = [
  "confirm_existing",
  "supplement_material",
  "mark_unsatisfied",
  "skip_requirement",
];


export async function POST(request: Request, context: RouteContext) {
  try {
    const { runId } = await context.params;
    const payload = (await request.json()) as {
      jdId?: string;
      requirementId?: string;
      action?: UserEvidenceOverrideAction;
      note?: string;
    };
    if (!payload.jdId || !payload.requirementId || !payload.action || !ACTIONS.includes(payload.action)) {
      return NextResponse.json(
        { error: "证据确认信息不完整。", code: "invalid_evidence_override" },
        { status: 400 },
      );
    }
    const artifact = await saveUserEvidenceOverride(runId, {
      jdId: payload.jdId,
      requirementId: payload.requirementId,
      action: payload.action,
      note: payload.note,
    });
    return NextResponse.json({
      runId,
      savedCount: artifact.overrides.length,
      artifact: {
        schemaVersion: artifact.schema_version,
        overrideCount: artifact.overrides.length,
      },
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "保存证据确认失败。";
    return NextResponse.json({ error: message, code: "evidence_override_failed" }, { status: 500 });
  }
}
