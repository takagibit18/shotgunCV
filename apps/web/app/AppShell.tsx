import React, { type ReactNode } from "react";
import Link from "next/link";

type NavKey = "resume" | "queue" | "evaluation" | "settings";

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
  { key: "resume", label: "简历优化", href: "/resume", icon: "document" },
  { key: "queue", label: "运行队列", href: "/runs", icon: "list" },
  { key: "evaluation", label: "评估结果", href: "/evaluations", icon: "check-square" },
  { key: "settings", label: "设置", href: "/settings", icon: "settings" },
];

export type IconName =
  | "ai"
  | "alert-triangle"
  | "bell"
  | "book"
  | "briefcase"
  | "calendar"
  | "check-square"
  | "chevron-left"
  | "chevron-right"
  | "clock"
  | "delete"
  | "document"
  | "edit"
  | "external-link"
  | "eye"
  | "eye-off"
  | "file"
  | "filter"
  | "folder"
  | "home"
  | "image-upload"
  | "key"
  | "layers"
  | "link"
  | "list"
  | "model"
  | "play"
  | "refresh"
  | "reset"
  | "save"
  | "search"
  | "settings"
  | "shield-alert"
  | "shield-check"
  | "sparkle"
  | "stats";

export function AppShell({ active, children, eyebrow = "", freshnessText = "本地数据" }: AppShellProps) {
  return (
    <div className="app-frame">
      <aside className="app-sidebar" aria-label="主导航">
        <Link href="/" className="sidebar-brand" aria-label="智能简历工作台">
          <span className="brand-mark">
            <Icon name="ai" />
          </span>
          <span>
            <strong>智能简历工作台</strong>
            <small></small>
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
            <strong>智能洞察</strong>
            <small>基于历史数据的智能建议</small>
          </span>
        </div>

        <div className="sidebar-user">
          <span className="avatar-mark">本</span>
          <span>
            <strong>本地用户</strong>
            <small>单用户工作台</small>
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

type MetricCardProps = {
  icon: IconName;
  label: string;
  value: ReactNode;
  helper?: ReactNode;
  tone?: "blue" | "green" | "orange" | "red" | "purple" | "neutral";
  className?: string;
};

export function MetricCard({ icon, label, value, helper, tone = "blue", className = "" }: MetricCardProps) {
  return (
    <article className={["metric-card", tone, className].filter(Boolean).join(" ")}>
      <span className={["semantic-icon", tone].join(" ")} aria-hidden="true">
        <Icon name={icon} />
      </span>
      <span className="metric-card-label">{label}</span>
      <strong>{value}</strong>
      {helper ? <small>{helper}</small> : null}
    </article>
  );
}

export function Icon({ name, className = "" }: { name: IconName; className?: string }) {
  if (name === "ai") {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true" className={className}>
        <path d="M5.5 18.5V5.5h3v13h-3Zm4.1 0 4.5-13h3.1l4.4 13h-3.2l-.8-2.6h-4.2l-.8 2.6H9.6Zm4.5-5h2.8l-1.4-4.7-1.4 4.7Z" />
      </svg>
    );
  }

  const paths: Record<Exclude<IconName, "ai">, ReactNode> = {
    "alert-triangle": (
      <>
        <path d="M12 3.5 21 20H3L12 3.5Z" />
        <path d="M12 9v5" />
        <path d="M12 17.5h.01" />
      </>
    ),
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
    briefcase: (
      <>
        <path d="M9 7V5.5A1.5 1.5 0 0 1 10.5 4h3A1.5 1.5 0 0 1 15 5.5V7" />
        <rect x="4" y="7" width="16" height="12" rx="2" />
        <path d="M4 12h16" />
      </>
    ),
    calendar: (
      <>
        <rect x="4" y="5" width="16" height="16" rx="2" />
        <path d="M8 3v4M16 3v4M4 10h16" />
      </>
    ),
    "check-square": (
      <>
        <rect x="4" y="4" width="16" height="16" rx="3" />
        <path d="m8.5 12.3 2.3 2.3 4.8-5.2" />
      </>
    ),
    "chevron-left": <path d="m15 18-6-6 6-6" />,
    "chevron-right": <path d="m9 18 6-6-6-6" />,
    clock: (
      <>
        <circle cx="12" cy="12" r="8" />
        <path d="M12 7.5V12l3 2" />
      </>
    ),
    delete: (
      <>
        <path d="M4 7h16" />
        <path d="M10 11v6M14 11v6" />
        <path d="M6 7l1 13h10l1-13" />
        <path d="M9 7V4h6v3" />
      </>
    ),
    document: (
      <>
        <path d="M7 3.5h7l4 4V20a1.5 1.5 0 0 1-1.5 1.5h-9A1.5 1.5 0 0 1 6 20V5A1.5 1.5 0 0 1 7.5 3.5Z" />
        <path d="M14 3.5V8h4" />
        <path d="M9 13h6M9 16h4" />
      </>
    ),
    edit: (
      <>
        <path d="M4 20h4l10.5-10.5a2.1 2.1 0 0 0-3-3L5 17v3Z" />
        <path d="m14 7 3 3" />
      </>
    ),
    "external-link": (
      <>
        <path d="M14 4h6v6" />
        <path d="m20 4-8 8" />
        <path d="M10 6H6a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-4" />
      </>
    ),
    eye: (
      <>
        <path d="M3.5 12s3.2-5.5 8.5-5.5S20.5 12 20.5 12s-3.2 5.5-8.5 5.5S3.5 12 3.5 12Z" />
        <circle cx="12" cy="12" r="2.5" />
      </>
    ),
    "eye-off": (
      <>
        <path d="m4 4 16 16" />
        <path d="M9.8 9.8A2.5 2.5 0 0 0 13.4 13.4" />
        <path d="M7.1 7.7C4.8 9.1 3.5 12 3.5 12s3.2 5.5 8.5 5.5c1.5 0 2.8-.4 3.9-1" />
        <path d="M10.8 6.6c.4-.1.8-.1 1.2-.1 5.3 0 8.5 5.5 8.5 5.5s-.7 1.2-1.9 2.4" />
      </>
    ),
    file: (
      <>
        <path d="M8 4h6l4 4v12H8a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2Z" />
        <path d="M14 4v5h4" />
      </>
    ),
    filter: (
      <>
        <path d="M4 5h16" />
        <path d="M7 12h10" />
        <path d="M10 19h4" />
      </>
    ),
    folder: (
      <>
        <path d="M4 7.5A2.5 2.5 0 0 1 6.5 5H10l2 2h5.5A2.5 2.5 0 0 1 20 9.5v7A2.5 2.5 0 0 1 17.5 19h-11A2.5 2.5 0 0 1 4 16.5v-9Z" />
      </>
    ),
    home: (
      <>
        <path d="m4 10 8-6.5 8 6.5v10a1 1 0 0 1-1 1h-5v-6H10v6H5a1 1 0 0 1-1-1V10Z" />
      </>
    ),
    "image-upload": (
      <>
        <rect x="4" y="5" width="16" height="14" rx="2" />
        <path d="m8 14 2-2 2 2 2.5-3 3.5 4" />
        <path d="M12 10V3.5" />
        <path d="m9.5 6 2.5-2.5L14.5 6" />
      </>
    ),
    key: (
      <>
        <circle cx="8" cy="12" r="3.5" />
        <path d="M11.5 12H21" />
        <path d="M17 12v3" />
        <path d="M14.5 12v2" />
      </>
    ),
    layers: (
      <>
        <path d="m12 3 8 4.5-8 4.5-8-4.5L12 3Z" />
        <path d="m4 12 8 4.5 8-4.5" />
        <path d="m4 16.5 8 4.5 8-4.5" />
      </>
    ),
    link: (
      <>
        <path d="M10 13a5 5 0 0 0 7.1 0l1.4-1.4a5 5 0 0 0-7.1-7.1L10 5.9" />
        <path d="M14 11a5 5 0 0 0-7.1 0l-1.4 1.4a5 5 0 0 0 7.1 7.1L14 18.1" />
      </>
    ),
    list: (
      <>
        <path d="M8 6h12M8 12h12M8 18h12" />
        <path d="M4 6h.1M4 12h.1M4 18h.1" />
      </>
    ),
    model: (
      <>
        <rect x="7" y="7" width="10" height="10" rx="2" />
        <path d="M4 10h3M4 14h3M17 10h3M17 14h3M10 4v3M14 4v3M10 17v3M14 17v3" />
      </>
    ),
    play: (
      <>
        <circle cx="12" cy="12" r="8" />
        <path d="m10.5 8.5 5 3.5-5 3.5v-7Z" />
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
    reset: (
      <>
        <path d="M4 7v5h5" />
        <path d="M5.8 15A7 7 0 1 0 6.5 7.2L4 12" />
      </>
    ),
    save: (
      <>
        <path d="M5 4h12l2 2v14H5V4Z" />
        <path d="M8 4v6h8V4" />
        <path d="M8 20v-6h8v6" />
      </>
    ),
    search: (
      <>
        <circle cx="11" cy="11" r="6" />
        <path d="m16 16 4 4" />
      </>
    ),
    settings: (
      <>
        <path d="M12 8.5a3.5 3.5 0 1 1 0 7 3.5 3.5 0 0 1 0-7Z" />
        <path d="m19 13 .8 1.8-2.1 3.6-2-.2-1.5.9L13 21h-2l-1.2-1.9-1.5-.9-2 .2-2.1-3.6L5 13v-2l-.8-1.8 2.1-3.6 2 .2 1.5-.9L11 3h2l1.2 1.9 1.5.9 2-.2 2.1 3.6L19 11v2Z" />
      </>
    ),
    "shield-alert": (
      <>
        <path d="M12 3.5 19 6v5c0 4.2-2.7 7.6-7 9-4.3-1.4-7-4.8-7-9V6l7-2.5Z" />
        <path d="M12 8v4" />
        <path d="M12 15.5h.01" />
      </>
    ),
    "shield-check": (
      <>
        <path d="M12 3.5 19 6v5c0 4.2-2.7 7.6-7 9-4.3-1.4-7-4.8-7-9V6l7-2.5Z" />
        <path d="m9 12 2 2 4-5" />
      </>
    ),
    sparkle: (
      <>
        <path d="M12 3.5 13.7 9l5.3 2-5.3 2-1.7 5.5L10.3 13 5 11l5.3-2L12 3.5Z" />
        <path d="m18.5 3.5.6 2 1.9.7-1.9.7-.6 2-.6-2-1.9-.7 1.9-.7.6-2Z" />
      </>
    ),
    stats: (
      <>
        <path d="M5 20V10" />
        <path d="M12 20V4" />
        <path d="M19 20v-7" />
        <path d="M3.5 20h17" />
      </>
    ),
  };

  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className={className}>
      {paths[name]}
    </svg>
  );
}
