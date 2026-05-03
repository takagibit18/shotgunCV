import { NextResponse } from "next/server";

import { patchRunDraft, RunActionError } from "../../../../../lib/run-actions";


type RouteContext = {
  params: Promise<{ runId: string }>;
};


export async function PATCH(request: Request, context: RouteContext) {
  try {
    const { runId } = await context.params;
    const formData = await request.formData();
    const cvFiles = formData.getAll("cvFiles").filter((item): item is File => item instanceof File);
    const jdFiles = formData.getAll("jdFiles").filter((item): item is File => item instanceof File);
    const jdFileDisplayNames = formData
      .getAll("jdFileDisplayNames")
      .filter((item): item is string => typeof item === "string");
    const jdTexts = formData.getAll("jdTexts").filter((item): item is string => typeof item === "string");
    const jdTextDisplayNames = formData
      .getAll("jdTextDisplayNames")
      .filter((item): item is string => typeof item === "string");
    return NextResponse.json(
      await patchRunDraft(runId, {
        candidateId: stringValue(formData.get("candidateId")),
        label: stringValue(formData.get("label")),
        cvFiles,
        jdFiles,
        jdFileDisplayNames,
        jdTexts,
        jdTextDisplayNames,
      }),
    );
  } catch (error) {
    if (error instanceof RunActionError) {
      return NextResponse.json({ error: error.message, code: error.code }, { status: error.status });
    }
    return NextResponse.json({ error: "Failed to update draft.", code: "draft_update_failed" }, { status: 500 });
  }
}


function stringValue(value: FormDataEntryValue | null): string | undefined {
  return typeof value === "string" ? value : undefined;
}
