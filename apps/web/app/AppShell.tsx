import React, { type ReactNode } from "react";
import Link from "next/link";

type NavKey = "dashboard" | "resume" | "queue" | "evaluation" | "settings";

type AppShellProps = {
  active: NavKey;
  children: ReactNode;
  eyebrow?: string;
  freshnessText?: string;
};

const NAV_ITEMS: Array<{
  key: NavKey;
  label: string;
  href?: string;
  icon: IconName;
  disabled?: boolean;
}> = [
  { key: "dashboard", label: "仪表盘", href: "/", icon: "home" },
  { key: "resume", label: "简历优化", href: "/resume", icon: "document" },
  { key: "queue", label: "运行队列", href: "/", icon: "list" },
  { key: "evaluation", label: "评估结果", href: "/evaluations", icon: "check-square" },
  { key: "settings", label: "设置", href: "/settings", icon: "settings" },
];

type IconName =
  | "ai"
  | "bell"
  | "book"
  | "check-square"
  | "document"
  | "home"
  | "list"
  | "refresh"
  | "settings"
  | "sparkle";

export function AppShell({ active, children, eyebrow = "AI Resume Ops 工作台", freshnessText = "本地数据" }: AppShellProps) {
  return (
    <div className="app-frame">
      <aside className="app-sidebar" aria-label="主导航">
        <Link href="/" className="sidebar-brand" aria-label="AI Resume Ops 工作台">
          <span className="brand-mark">
            <Icon name="ai" />
          </span>
          <span>
            <strong>AI Resume Ops</strong>
            <small>工作台</small>
          </span>
        </Link>

        <nav className="sidebar-nav">
          {NAV_ITEMS.map((item) => {
            const className = ["sidebar-nav-item", item.key === active ? "active" : "", item.disabled ? "disabled" : ""]
              .filter(Boolean)
              .join(" ");
            const content = (
              <>
                <Icon name={item.icon} />
                <span>{item.label}</span>
              </>
            );
            return item.href && !item.disabled ? (
              <Link key={item.key} href={item.href} className={className}>
                {content}
              </Link>
            ) : (
              <span key={item.key} className={className} aria-disabled="true" title={buildDisabledNavTitle(item.key)}>
                {content}
              </span>
            );
          })}
        </nav>

        <div className="sidebar-insight">
          <Icon name="sparkle" />
          <span>
            <strong>AI 洞察</strong>
            <small>基于历史数据的智能建议</small>
          </span>
        </div>

        <div className="sidebar-user">
          <span className="avatar-mark">N</span>
          <span>
            <strong>Nemo Zhang</strong>
            <small>产品负责人</small>
          </span>
        </div>
      </aside>

      <div className="app-main-shell">
        <header className="app-commandbar">
          <span className="commandbar-context">{eyebrow}</span>
          <div className="commandbar-actions" aria-label="工作台工具">
            <span className="freshness-pill">
              <Icon name="refresh" />
              数据更新：{freshnessText}
            </span>
          </div>
        </header>
        {children}
      </div>
    </div>
  );
}

function buildDisabledNavTitle(key: NavKey): string {
  return "后续版本规划中";
}

export function Icon({ name }: { name: IconName }) {
  if (name === "ai") {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M5.5 18.5V5.5h3v13h-3Zm4.1 0 4.5-13h3.1l4.4 13h-3.2l-.8-2.6h-4.2l-.8 2.6H9.6Zm4.5-5h2.8l-1.4-4.7-1.4 4.7Z" />
      </svg>
    );
  }

  const paths: Record<Exclude<IconName, "ai">, ReactNode> = {
    bell: (
      <>
        <path d="M18 9.5a6 6 0 0 0-12 0c0 6-2 6.5-2 6.5h16s-2-.5-2-6.5Z" />
        <path d="M10 20a2.3 2.3 0 0 0 4 0" />
      </>
    ),
    book: (
      <>
        <path d="M5 4.5h8a3 3 0 0 1 3 3v12H8a3 3 0 0 0-3 3v-18Z" />
        <path d="M16 7.5h3v12h-3" />
      </>
    ),
    "check-square": (
      <>
        <rect x="4" y="4" width="16" height="16" rx="3" />
        <path d="m8.5 12.3 2.3 2.3 4.8-5.2" />
      </>
    ),
    document: (
      <>
        <path d="M7 3.5h7l4 4V20a1.5 1.5 0 0 1-1.5 1.5h-9A1.5 1.5 0 0 1 6 20V5A1.5 1.5 0 0 1 7.5 3.5Z" />
        <path d="M14 3.5V8h4" />
        <path d="M9 13h6M9 16h4" />
      </>
    ),
    home: (
      <>
        <path d="m4 10 8-6.5 8 6.5v10a1 1 0 0 1-1 1h-5v-6H10v6H5a1 1 0 0 1-1-1V10Z" />
      </>
    ),
    list: (
      <>
        <path d="M8 6h12M8 12h12M8 18h12" />
        <path d="M4 6h.1M4 12h.1M4 18h.1" />
      </>
    ),
    refresh: (
      <>
        <path d="M20 11a8 8 0 0 0-14.3-4.9L4 8" />
        <path d="M4 4v4h4" />
        <path d="M4 13a8 8 0 0 0 14.3 4.9L20 16" />
        <path d="M20 20v-4h-4" />
      </>
    ),
    settings: (
      <>
        <path d="M12 8.5a3.5 3.5 0 1 1 0 7 3.5 3.5 0 0 1 0-7Z" />
        <path d="m19 13 .8 1.8-2.1 3.6-2-.2-1.5.9L13 21h-2l-1.2-1.9-1.5-.9-2 .2-2.1-3.6L5 13v-2l-.8-1.8 2.1-3.6 2 .2 1.5-.9L11 3h2l1.2 1.9 1.5.9 2-.2 2.1 3.6L19 11v2Z" />
      </>
    ),
    sparkle: (
      <>
        <path d="M12 3.5 13.7 9l5.3 2-5.3 2-1.7 5.5L10.3 13 5 11l5.3-2L12 3.5Z" />
        <path d="m18.5 3.5.6 2 1.9.7-1.9.7-.6 2-.6-2-1.9-.7 1.9-.7.6-2Z" />
      </>
    ),
  };

  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      {paths[name]}
    </svg>
  );
}
