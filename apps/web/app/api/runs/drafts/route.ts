import { NextResponse } from "next/server";

import { createRunDraft, DraftCreationError } from "../../../../lib/upload-drafts";
import type { ExistingCvFileRef } from "../../../../lib/upload-drafts";


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
      candidateId: stringValue(formData.get("candidateId")),
      candidateDisplayName: stringValue(formData.get("candidateDisplayName")),
      cvFiles,
      existingCvFiles: parseExistingCvRefs(formData.get("existingCvRefs")),
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

function stringValue(value: FormDataEntryValue | null): string | undefined {
  return typeof value === "string" ? value : undefined;
}

function parseExistingCvRefs(value: FormDataEntryValue | null): ExistingCvFileRef[] {
  if (typeof value !== "string" || !value.trim()) {
    return [];
  }
  try {
    const parsed = JSON.parse(value) as unknown;
    if (!Array.isArray(parsed)) {
      return [];
    }
    return parsed
      .map((item) => {
        if (
          typeof item === "object" &&
          item !== null &&
          typeof (item as { sourceRunId?: unknown }).sourceRunId === "string" &&
          typeof (item as { storedRelativePath?: unknown }).storedRelativePath === "string"
        ) {
          return {
            sourceRunId: (item as { sourceRunId: string }).sourceRunId,
            storedRelativePath: (item as { storedRelativePath: string }).storedRelativePath,
          };
        }
        return null;
      })
      .filter((item): item is ExistingCvFileRef => item !== null);
  } catch {
    return [];
  }
}
