import type { ReactNode } from "react";

import "./globals.css";


export const metadata = {
  title: "ShotgunCV 本地 AI 简历运营工作台",
  description: "用于查看 ShotgunCV run 产物、评分证据、风险提示和投递策略的本地工作台。",
};


export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
