import { NextResponse } from "next/server";

import {
  loadLocalConfig,
  LocalConfigError,
  resetLocalConfig,
  saveLocalConfig,
  type LocalConfigPatch,
} from "../../../../lib/local-config";

export async function GET() {
  try {
    return NextResponse.json(await loadLocalConfig());
  } catch (error) {
    return localConfigErrorResponse(error);
  }
}

export async function PUT(request: Request) {
  try {
    const payload = (await request.json()) as LocalConfigPatch;
    return NextResponse.json(await saveLocalConfig(payload));
  } catch (error) {
    return localConfigErrorResponse(error);
  }
}

export async function POST() {
  try {
    return NextResponse.json(await resetLocalConfig());
  } catch (error) {
    return localConfigErrorResponse(error);
  }
}

function localConfigErrorResponse(error: unknown) {
  if (error instanceof LocalConfigError) {
    return NextResponse.json({ error: error.message, code: error.code }, { status: error.status });
  }
  return NextResponse.json({ error: "Failed to update local configuration.", code: "write_failed" }, { status: 500 });
}
