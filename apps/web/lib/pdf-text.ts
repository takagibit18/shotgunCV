type PdfQuality = "readable" | "scanned" | "empty";


export async function extractPdfText(buffer: Buffer): Promise<{ text: string; quality: PdfQuality }> {
  try {
    const pdfParse = await loadPdfParse();
    const result = await pdfParse(buffer);
    const text = String(result?.text ?? "");
    return { text, quality: classifyPdfText(text) };
  } catch {
    return { text: "", quality: "empty" };
  }
}


async function loadPdfParse(): Promise<(buffer: Buffer) => Promise<{ text?: string }>> {
  const dynamicImport = new Function("specifier", "return import(specifier)") as (specifier: string) => Promise<unknown>;
  const module = (await dynamicImport("pdf-parse")) as { default?: unknown };
  const parser = module.default ?? module;
  if (typeof parser !== "function") {
    throw new Error("pdf-parse is not callable");
  }
  return parser as (buffer: Buffer) => Promise<{ text?: string }>;
}


function classifyPdfText(text: string): PdfQuality {
  const visibleChars = Array.from(text).filter((char) => !/\s/.test(char) && char.trim()).length;
  if (visibleChars >= 50) {
    return "readable";
  }
  if (visibleChars > 0) {
    return "scanned";
  }
  return "empty";
}
