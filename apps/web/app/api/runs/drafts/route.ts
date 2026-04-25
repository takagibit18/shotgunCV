import { NextResponse } from "next/server";

import { createRunDraft, DraftCreationError } from "../../../../lib/upload-drafts";


export async function POST(request: Request) {
  try {
    const formData = await request.formData();
    const candidateId = String(formData.get("candidateId") ?? "");
    const labelValue = formData.get("label");
    const cvFiles = formData.getAll("cvFiles").filter((item): item is File => item instanceof File);
    const jdFiles = formData.getAll("jdFiles").filter((item): item is File => item instanceof File);
    const result = await createRunDraft({
      candidateId,
      label: typeof labelValue === "string" ? labelValue : "",
      cvFiles,
      jdFiles,
    });
    return NextResponse.json(result);
  } catch (error) {
    if (error instanceof DraftCreationError) {
      return NextResponse.json({ error: error.message, code: error.code }, { status: 400 });
    }
    return NextResponse.json({ error: "Failed to create draft run.", code: "write_failed" }, { status: 500 });
  }
}
