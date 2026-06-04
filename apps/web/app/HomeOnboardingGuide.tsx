"use client";

import React, { useEffect, useMemo, useState } from "react";
import Link from "next/link";

import { Icon, type IconName } from "./AppShell";

const GUIDE_STORAGE_KEY = "shotguncv_landing_workflow_guide_dismissed";
const AUTO_PLAY_MS = 5200;

type HomeOnboardingGuideProps = {
  totalRuns: number;
  draftRuns: number;
  activeRuns: number;
};

const GUIDE_STEPS: Array<{
  step: string;
  title: string;
  body: string;
  href: string;
  action: string;
  icon: IconName;
}> = [
  {
    step: "01",
    title: "整理输入",
    body: "上传简历、补充材料和岗位描述。网页只保存文件与元数据，不在浏览器里展开原文。",
    href: "/upload",
    action: "创建投递草稿",
    icon: "image-upload",
  },
  {
    step: "02",
    title: "执行本地流程",
    body: "按照草稿返回的本地命令运行导入、分析、生成、评估、计划和报告。",
    href: "/runs",
    action: "查看运行队列",
    icon: "play",
  },
  {
    step: "03",
    title: "复核证据",
    body: "在简历优化与评估结果中检查评分摘要、门槛判断、差距分析和策略建议。",
    href: "/evaluations",
    action: "查看评估结果",
    icon: "shield-check",
  },
];

export function HomeOnboardingGuide({ totalRuns, draftRuns, activeRuns }: HomeOnboardingGuideProps) {
  const [activeIndex, setActiveIndex] = useState(0);
  const [direction, setDirection] = useState<"next" | "previous">("next");
  const [isDismissed, setIsDismissed] = useState(false);
  const activeStep = GUIDE_STEPS[activeIndex];
  const progressText = `${activeIndex + 1} / ${GUIDE_STEPS.length}`;
  const statusText = useMemo(
    () => `当前有 ${totalRuns} 个任务，${draftRuns} 个草稿，${activeRuns} 个运行中。`,
    [activeRuns, draftRuns, totalRuns],
  );

  useEffect(() => {
    setIsDismissed(window.localStorage.getItem(GUIDE_STORAGE_KEY) === "1");
  }, []);

  useEffect(() => {
    if (isDismissed) {
      return;
    }
    const timer = window.setInterval(() => {
      setDirection("next");
      setActiveIndex((current) => (current + 1) % GUIDE_STEPS.length);
    }, AUTO_PLAY_MS);
    return () => window.clearInterval(timer);
  }, [isDismissed]);

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (isDismissed) {
        return;
      }
      if (event.key === "ArrowRight") {
        event.preventDefault();
        goToStep((activeIndex + 1) % GUIDE_STEPS.length, "next");
      }
      if (event.key === "ArrowLeft") {
        event.preventDefault();
        goToStep((activeIndex - 1 + GUIDE_STEPS.length) % GUIDE_STEPS.length, "previous");
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [activeIndex, isDismissed]);

  function goToStep(nextIndex: number, nextDirection: "next" | "previous") {
    setDirection(nextDirection);
    setActiveIndex(nextIndex);
  }

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
      <section id="workflow" className="landing-section landing-workflow compact" aria-label="打开引导">
        <div>
          <strong>动态指引已收起</strong>
          <span>{statusText}</span>
        </div>
        <button className="landing-button secondary" type="button" onClick={handleRestore}>
          重新查看引导
        </button>
      </section>
    );
  }

  return (
    <section id="workflow" className="landing-section landing-workflow" aria-labelledby="workflow-title">
      <div className="landing-workflow-head">
        <div>
          <span className="landing-kicker">打开后的第一步</span>
          <h2 id="workflow-title">先把工作流跑通，再进入证据复核</h2>
          <p>首次进入时先给出可执行路径，同时保留 ShotgunCV 的本地执行边界：网页帮你定位状态、风险和下一步，不替代本地执行流程。</p>
        </div>
        <button className="landing-workflow-dismiss" type="button" onClick={handleDismiss}>
          收起
        </button>
      </div>

      <div className="landing-workflow-stage" aria-live="polite">
        <button
          className="landing-workflow-arrow"
          type="button"
          aria-label="上一步"
          onClick={() => goToStep((activeIndex - 1 + GUIDE_STEPS.length) % GUIDE_STEPS.length, "previous")}
        >
          <Icon name="chevron-left" />
        </button>

        <article className={`landing-workflow-card ${direction}`} key={activeStep.step}>
          <div className="landing-workflow-visual" aria-hidden="true">
            <span className="landing-workflow-icon">
              <Icon name={activeStep.icon} />
            </span>
            <span className="landing-workflow-ring" />
          </div>
          <div className="landing-workflow-copy">
            <span className="landing-workflow-count">{activeStep.step}</span>
            <h3>{activeStep.title}</h3>
            <p>{activeStep.body}</p>
            <Link href={activeStep.href} className="landing-button primary">
              {activeStep.action}
            </Link>
          </div>
        </article>

        <button
          className="landing-workflow-arrow"
          type="button"
          aria-label="下一步"
          onClick={() => goToStep((activeIndex + 1) % GUIDE_STEPS.length, "next")}
        >
          <Icon name="chevron-right" />
        </button>
      </div>

      <div className="landing-workflow-controls" aria-label="工作流步骤分页">
        <span className="landing-workflow-progress">{progressText}</span>
        <div className="landing-workflow-dots">
          {GUIDE_STEPS.map((step, index) => (
            <button
              key={step.step}
              type="button"
              className={index === activeIndex ? "active" : ""}
              aria-label={`查看第 ${index + 1} 步`}
              aria-current={index === activeIndex ? "step" : undefined}
              onClick={() => goToStep(index, index > activeIndex ? "next" : "previous")}
            />
          ))}
        </div>
      </div>
    </section>
  );
}
