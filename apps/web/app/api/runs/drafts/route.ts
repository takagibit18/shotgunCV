import { NextResponse } from "next/server";

import { createRunDraft, DraftCreationError } from "../../../../lib/upload-drafts";


export async function POST(request: Request) {
  try {
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
    const result = await createRunDraft({
      cvFiles,
      jdFiles,
      jdFileDisplayNames,
      jdTexts,
      jdTextDisplayNames,
    });
    return NextResponse.json(result);
  } catch (error) {
    if (error instanceof DraftCreationError) {
      return NextResponse.json({ error: error.message, code: error.code }, { status: 400 });
    }
    return NextResponse.json({ error: "创建投递草稿失败。", code: "write_failed" }, { status: 500 });
  }
}
