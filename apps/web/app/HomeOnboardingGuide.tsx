"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";

import { Icon } from "./AppShell";

const GUIDE_STORAGE_KEY = "shotguncv_v08_opening_guide_dismissed";

type HomeOnboardingGuideProps = {
  totalRuns: number;
  draftRuns: number;
  activeRuns: number;
};

const GUIDE_STEPS = [
  {
    step: "01",
    title: "整理输入",
    body: "上传 CV、补充材料和 JD，Web 只保存文件与元数据，不在浏览器里展开原文。",
    href: "/upload",
    action: "创建草稿 run",
    icon: "image-upload",
  },
  {
    step: "02",
    title: "执行 pipeline",
    body: "按照草稿返回的本地命令运行 ingest、analyze、generate、evaluate、plan、report。",
    href: "/",
    action: "查看运行队列",
    icon: "play",
  },
  {
    step: "03",
    title: "复核证据",
    body: "在简历优化与评估结果中检查 scorecard、gate、gap map 和策略建议。",
    href: "/evaluations",
    action: "查看评估结果",
    icon: "shield-check",
  },
] as const;

export function HomeOnboardingGuide({ totalRuns, draftRuns, activeRuns }: HomeOnboardingGuideProps) {
  const [isDismissed, setIsDismissed] = useState(false);

  useEffect(() => {
    setIsDismissed(window.localStorage.getItem(GUIDE_STORAGE_KEY) === "1");
  }, []);

  function handleDismiss() {
    window.localStorage.setItem(GUIDE_STORAGE_KEY, "1");
    setIsDismissed(true);
  }

  function handleRestore() {
    window.localStorage.removeItem(GUIDE_STORAGE_KEY);
    setIsDismissed(false);
  }

  if (isDismissed) {
    return (
      <section className="opening-guide compact" aria-label="打开引导">
        <div>
          <strong>引导已收起</strong>
          <span>
            当前有 {totalRuns} 个 run，{draftRuns} 个草稿，{activeRuns} 个运行中。
          </span>
        </div>
        <button className="secondary-button" type="button" onClick={handleRestore}>
          重新查看引导
        </button>
      </section>
    );
  }

  return (
    <section className="opening-guide" aria-labelledby="opening-guide-title">
      <div className="opening-guide-head">
        <div>
          <p className="eyebrow">打开后的第一步</p>
          <h2 id="opening-guide-title">先把工作流跑通，再进入证据复核</h2>
          <p>
            首次进入时先给出可执行路径，同时保留 ShotgunCV 的本地执行边界：Web 帮你定位状态、风险和下一步，不替代 CLI pipeline。
          </p>
        </div>
        <button className="secondary-button" type="button" onClick={handleDismiss}>
          收起
        </button>
      </div>
      <div className="opening-guide-grid">
        {GUIDE_STEPS.map((item) => (
          <article className="opening-guide-step" key={item.step}>
            <span className="step-index">{item.step}</span>
            <span className="semantic-icon green" aria-hidden="true">
              <Icon name={item.icon} />
            </span>
            <h3>{item.title}</h3>
            <p>{item.body}</p>
            <Link href={item.href} className="inline-action">
              {item.action}
            </Link>
          </article>
        ))}
      </div>
    </section>
  );
}
