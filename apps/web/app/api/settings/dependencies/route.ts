import { NextResponse } from "next/server";

import { checkPythonDependencies, installPythonDependency, type InstallPackageName } from "../../../../lib/python-env";


const ALLOWED_PACKAGES = new Set<InstallPackageName>(["fitz", "pytesseract"]);


export async function GET() {
  return NextResponse.json(await checkPythonDependencies());
}


export async function POST(request: Request) {
  const payload = (await request.json().catch(() => ({}))) as { package?: string };
  if (!payload.package || !ALLOWED_PACKAGES.has(payload.package as InstallPackageName)) {
    return NextResponse.json({ error: "不支持的依赖安装请求。", code: "unsupported_package" }, { status: 400 });
  }
  const result = await installPythonDependency(payload.package as InstallPackageName);
  return NextResponse.json(result, { status: result.success ? 200 : 500 });
}
