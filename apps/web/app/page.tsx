import React from "react";
import Link from "next/link";

import { STATUS_LABELS } from "../lib/labels";
import { listRuns, type RunSummary } from "../lib/runs";
import { Icon, type IconName } from "./AppShell";
import { HomeOnboardingGuide } from "./HomeOnboardingGuide";

const STAGE_TOTAL = 6;

const FEATURES: Array<{
  icon: IconName;
  title: string;
  body: string;
}> = [
  {
    icon: "briefcase",
    title: "从岗位反推简历策略",
    body: "从岗位描述中提炼要求，生成可执行的简历优化方向，让修改有明确依据。",
  },
  {
    icon: "shield-check",
    title: "本地优先，边界清晰",
    body: "网页用于状态定位、风险提示与结果查看，不替代本地执行流程。",
  },
  {
    icon: "check-square",
    title: "证据化评估结果",
    body: "输出评分摘要、差距分析、匹配度、风险项与下一步建议。",
  },
  {
    icon: "layers",
    title: "串联完整工作流",
    body: "将导入、分析、生成、评估、计划和报告串成完整流程。",
  },
];

const USAGE_STEPS = [
  "上传简历、补充材料和岗位描述，创建可复现的本地任务。",
  "按草稿命令执行本地流程，让系统生成结构化产物。",
  "回到 Web 查看证据、风险、差距和下一步优化策略。",
];

const FAQS = [
  {
    question: "首页会展示原始简历或岗位描述内容吗？",
    answer: "不会。首页只展示任务元数据、流程状态、风险提示和入口动作，避免暴露原始文本。",
  },
  {
    question: "网页会替代本地执行流程吗？",
    answer: "不会。网页是工作流入口和证据复核层，核心执行仍保持本地优先。",
  },
  {
    question: "第一次打开应该先做什么？",
    answer: "先创建投递草稿，再执行本地流程，最后复核评估和简历优化结果。",
  },
];

export default async function HomePage() {
  const runs = await listRuns();
  const totalRuns = runs.length;
  const activeRuns = runs.filter((run) => run.draftStatus === "running" || run.draftStatus === "queued").length;
  const draftRuns = runs.filter((run) => run.draftStatus === "draft" || run.draftStatus === "ingest-ready").length;
  const warningRuns = runs.filter((run) => run.runStatus?.quality_summary || run.runStatus?.error_summary).length;
  const doneRuns = runs.filter((run) => run.draftStatus === "done").length;
  const completionRate = totalRuns === 0 ? 0 : Math.round((doneRuns / totalRuns) * 100);
  const stageCoverage =
    totalRuns === 0
      ? 0
      : Math.round((runs.reduce((sum, run) => sum + run.completedStages.length, 0) / (totalRuns * STAGE_TOTAL)) * 100);
  const recentRuns = runs.slice(0, 3);

  return (
    <main className="landing-page">
      <LandingNav />

      <section className="landing-hero" aria-labelledby="landing-hero-title">
        <div className="landing-hero-copy">
          <span className="landing-badge">
            <Icon name="sparkle" />
            智能辅助
          </span>
          <h1 id="landing-hero-title">从岗位输入到证据化简历策略，一屏掌控</h1>
          <p className="landing-hero-lead">从岗位输入、投递草稿、本地执行到证据复核，帮助你高效完成简历优化与投递准备。</p>
          <p className="landing-hero-support">
            ShotgunCV 网页端保持本地优先：只展示任务产物、评分证据、风险提示和下一步动作，不暴露原始简历或岗位正文，只聚焦当前工作流。
          </p>
          <div className="landing-actions">
            <Link href="/upload" className="landing-button primary">
              立即开始
            </Link>
            <a href="#workflow" className="landing-button secondary">
              查看工作流
            </a>
            <Link href="/resume" className="landing-button ghost">
              查看简历优化
            </Link>
          </div>
        </div>

        <HeroShowcase
          totalRuns={totalRuns}
          activeRuns={activeRuns}
          warningRuns={warningRuns}
          draftRuns={draftRuns}
          completionRate={completionRate}
          stageCoverage={stageCoverage}
          recentRuns={recentRuns}
        />
      </section>

      <section id="features" className="landing-section landing-values" aria-labelledby="landing-features-title">
        <div className="landing-section-heading">
          <span className="landing-kicker">功能特色</span>
          <h2 id="landing-features-title">为什么用智能简历工作台</h2>
          <p>让简历优化从经验驱动，走向证据驱动；同时把风险、证据和下一步动作放在用户真正需要的位置。</p>
        </div>
        <div className="landing-feature-grid">
          {FEATURES.map((feature) => (
            <article className="landing-feature-card" key={feature.title}>
              <span className="landing-feature-icon" aria-hidden="true">
                <Icon name={feature.icon} />
              </span>
              <h3>{feature.title}</h3>
              <p>{feature.body}</p>
            </article>
          ))}
        </div>
      </section>

      <section id="usage" className="landing-section landing-usage" aria-labelledby="landing-usage-title">
        <div className="landing-section-heading compact">
          <span className="landing-kicker">使用方式</span>
          <h2 id="landing-usage-title">三步进入一轮完整简历工作流</h2>
        </div>
        <div className="landing-usage-strip">
          {USAGE_STEPS.map((step, index) => (
            <article className="landing-usage-item" key={step}>
              <span>{String(index + 1).padStart(2, "0")}</span>
              <p>{step}</p>
            </article>
          ))}
        </div>
      </section>

      <HomeOnboardingGuide totalRuns={totalRuns} draftRuns={draftRuns} activeRuns={activeRuns} />

      <section id="faq" className="landing-section landing-faq" aria-labelledby="landing-faq-title">
        <div className="landing-section-heading compact">
          <span className="landing-kicker">常见问题</span>
          <h2 id="landing-faq-title">保持入口清晰，也保持执行边界清晰</h2>
        </div>
        <div className="landing-faq-list">
          {FAQS.map((item) => (
            <article className="landing-faq-item" key={item.question}>
              <h3>{item.question}</h3>
              <p>{item.answer}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="landing-final-cta" aria-labelledby="landing-final-title">
        <h2 id="landing-final-title">准备开始你的第一轮简历工作流了吗？</h2>
        <p>从岗位输入开始，快速生成更清晰、更可执行的简历优化路径。</p>
        <div className="landing-actions">
          <Link href="/upload" className="landing-button primary">
            立即开始
          </Link>
          <a href="#workflow" className="landing-button secondary">
            查看工作流说明
          </a>
        </div>
      </section>
    </main>
  );
}

function LandingNav() {
  return (
    <header className="landing-nav">
      <Link href="/" className="landing-brand" aria-label="智能简历工作台">
        <span className="landing-brand-mark">
          <Icon name="ai" />
        </span>
        <strong>智能简历工作台</strong>
      </Link>
      <nav className="landing-nav-links" aria-label="首页导航">
        <a href="#features">功能特色</a>
        <a href="#workflow">工作流</a>
        <a href="#usage">使用方式</a>
        <a href="#faq">常见问题</a>
      </nav>
      <div className="landing-nav-actions">
        <Link href="/runs" className="landing-nav-secondary">
          打开运行队列
        </Link>
        <Link href="/upload" className="landing-nav-primary">
          立即开始
        </Link>
      </div>
    </header>
  );
}

function HeroShowcase({
  totalRuns,
  activeRuns,
  warningRuns,
  draftRuns,
  completionRate,
  stageCoverage,
  recentRuns,
}: {
  totalRuns: number;
  activeRuns: number;
  warningRuns: number;
  draftRuns: number;
  completionRate: number;
  stageCoverage: number;
  recentRuns: RunSummary[];
}) {
  const rows = recentRuns.length > 0 ? recentRuns : buildPreviewFallbackRows();
  const hasRuns = recentRuns.length > 0;

  return (
    <div className="landing-showcase" aria-label="智能简历工作台产品预览">
      <div className="landing-showcase-tabs" aria-hidden="true">
        <span className="active">AI 工作流</span>
        <span>证据复核</span>
        <span>本地执行</span>
      </div>
      <div className="landing-product-card">
        <div className="landing-product-left">
          <span className="landing-product-label">流程健康度</span>
          <strong>{totalRuns === 0 ? "等待首个任务" : `${totalRuns} 个任务已接入`}</strong>
          <div className="landing-pipeline-track" aria-label={`阶段覆盖 ${stageCoverage}%`}>
            {["ingest", "analyze", "generate", "evaluate", "plan", "report"].map((stage, index) => (
              <span key={stage} className={index < Math.max(1, Math.ceil((stageCoverage / 100) * STAGE_TOTAL)) ? "active" : ""} />
            ))}
          </div>
          <div className="landing-mini-stats">
            <MiniStat label="完成率" value={`${completionRate}%`} />
            <MiniStat label="草稿" value={draftRuns} />
            <MiniStat label="运行中" value={activeRuns} />
            <MiniStat label="风险" value={warningRuns} tone={warningRuns > 0 ? "warn" : "good"} />
          </div>
        </div>
        <div className="landing-product-right">
          {rows.map((run) => (
            <div className="landing-run-preview" key={run.runId}>
              <span>
                <strong>{run.label || run.runId}</strong>
                <small>{run.runId}</small>
              </span>
              <span className={buildStatusClassName(run.draftStatus)}>
                {STATUS_LABELS[run.draftStatus] ?? run.draftStatus}
              </span>
              <Link href={hasRuns ? `/runs/${run.runId}` : "/upload"}>{hasRuns ? "检查证据" : "创建草稿"}</Link>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function MiniStat({ label, value, tone = "neutral" }: { label: string; value: number | string; tone?: "neutral" | "good" | "warn" }) {
  return (
    <span className={`landing-mini-stat ${tone}`}>
      <small>{label}</small>
      <strong>{value}</strong>
    </span>
  );
}

function buildPreviewFallbackRows(): RunSummary[] {
  return [
    {
      runId: "draft-preview",
      label: "创建草稿后显示在这里",
      draftStatus: "draft",
      completedStages: [],
      lastModified: new Date("2026-05-17T08:00:00.000Z").toISOString(),
      analyzerProvider: "deterministic",
      generatorProvider: "openai",
      judgeProvider: "openai",
      plannerProvider: "openai",
      runStatus: null,
      stageStatuses: [],
      timeline: [],
      draft: null,
    },
  ];
}

function buildStatusClassName(status: string): string {
  if (status === "failed") {
    return "status-chip danger";
  }
  if (status === "done") {
    return "status-chip success";
  }
  if (status === "running" || status === "queued") {
    return "status-chip info";
  }
  return "status-chip";
}
