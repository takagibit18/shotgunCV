import { readdir, readFile, stat } from "node:fs/promises";
import path from "node:path";
import process from "node:process";

const WEB_ROOT = path.resolve(process.cwd());
const APP_ROOT = path.join(WEB_ROOT, "app");
const FIXTURE_ROOT = path.join(WEB_ROOT, "scripts", "__fixtures__");

const ALLOWED_ENGLISH = new Set([
  "ShotgunCV",
  "LLM",
  "JSON",
  "OpenAI",
  "API",
  "ID",
  "runId",
  "jd",
  "variant",
  "report",
  "markdown",
  "runs",
  "pipeline",
]);

const FORBIDDEN_TEXT_PATTERNS = [
  /Read-Only Viewer/i,
  /Back to runs/i,
  /Back to run detail/i,
  /Open report/i,
  /run detail/i,
  /Run Report/i,
  /Analyze(?!r)/,
  /Generate/,
  /Evaluate/,
  /Plan(?!ner)/,
  /untitled run/i,
  /final score/i,
  /gap count/i,
  /top reasons/i,
  /No top reasons captured/i,
  /No ranking explanations/i,
  /Legacy artifacts are still readable/i,
];

const FORBIDDEN_VARIANT_RENDER_PATTERNS = [
  /<h3>\{variant\.variant_id\}<\/h3>/,
  /<h3>\{item\.variantId\}<\/h3>/,
  /<h3>\{explanation\.variant_id\}<\/h3>/,
];

async function main() {
  const appFiles = await walk(APP_ROOT);
  const targetFiles = appFiles.filter((filePath) => filePath.endsWith(".tsx") || filePath.endsWith(".ts"));
  const violations = [];

  for (const filePath of targetFiles) {
    const content = await readFile(filePath, "utf-8");
    for (const pattern of FORBIDDEN_TEXT_PATTERNS) {
      if (pattern.test(content)) {
        violations.push(`${relative(filePath)}: 命中英文文案模式 ${pattern}`);
      }
    }
    for (const pattern of FORBIDDEN_VARIANT_RENDER_PATTERNS) {
      if (pattern.test(content)) {
        violations.push(`${relative(filePath)}: 命中原始 variant id 直接展示模式 ${pattern}`);
      }
    }
    violations.push(...checkQuotedEnglishTokens(content, filePath));
  }

  violations.push(...(await runFixtureChecks()));

  if (violations.length > 0) {
    console.error("中文主导检查失败：");
    for (const item of violations) {
      console.error(`- ${item}`);
    }
    process.exit(1);
  }

  console.log("中文主导检查通过");
}

function checkQuotedEnglishTokens(content, filePath) {
  const findings = [];
  const quoted = content.match(/["']([^"']{3,})["']/g) ?? [];
  for (const chunk of quoted) {
    const raw = chunk.slice(1, -1).trim();
    if (!raw) {
      continue;
    }
    if (raw.includes("\\u")) {
      continue;
    }
    const words = raw.match(/[A-Za-z]{3,}/g) ?? [];
    if (words.length === 0) {
      continue;
    }
    if (/^[a-z0-9\- ]+$/i.test(raw)) {
      continue;
    }
    const unknown = words.filter((word) => !ALLOWED_ENGLISH.has(word));
    const likelyUiText = /\s/.test(raw) || /[，。！？：；,.!?]/.test(raw);
    if (unknown.length > 0 && likelyUiText && /[\u4e00-\u9fff]/.test(raw) === false && /[/:{}.<>=_-]/.test(raw) === false) {
      findings.push(`${relative(filePath)}: 可疑英文文本 "${raw}"`);
    }
  }
  return findings;
}

async function runFixtureChecks() {
  const failures = [];
  const passFile = path.join(FIXTURE_ROOT, "zh-pass.tsx");
  const failFile = path.join(FIXTURE_ROOT, "zh-fail.tsx");

  const passContent = await readFile(passFile, "utf-8");
  const failContent = await readFile(failFile, "utf-8");

  const passViolations = [
    ...checkQuotedEnglishTokens(passContent, passFile),
    ...findPatternViolations(passContent, passFile),
  ];
  if (passViolations.length > 0) {
    failures.push(`fixtures 正例失败：${passViolations.join("; ")}`);
  }

  const failViolations = [
    ...checkQuotedEnglishTokens(failContent, failFile),
    ...findPatternViolations(failContent, failFile),
  ];
  if (failViolations.length === 0) {
    failures.push("fixtures 反例未被拦截：zh-fail.tsx");
  }
  return failures;
}

function findPatternViolations(content, filePath) {
  const hits = [];
  for (const pattern of FORBIDDEN_TEXT_PATTERNS) {
    if (pattern.test(content)) {
      hits.push(`${relative(filePath)} 命中 ${pattern}`);
    }
  }
  for (const pattern of FORBIDDEN_VARIANT_RENDER_PATTERNS) {
    if (pattern.test(content)) {
      hits.push(`${relative(filePath)} 命中 ${pattern}`);
    }
  }
  return hits;
}

async function walk(rootDir) {
  const entries = await readdir(rootDir, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    const fullPath = path.join(rootDir, entry.name);
    if (entry.isDirectory()) {
      files.push(...(await walk(fullPath)));
      continue;
    }
    if ((await stat(fullPath)).isFile()) {
      files.push(fullPath);
    }
  }
  return files;
}

function relative(filePath) {
  return path.relative(WEB_ROOT, filePath).replaceAll("\\", "/");
}

await main();
