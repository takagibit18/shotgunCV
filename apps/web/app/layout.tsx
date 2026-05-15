import type { ReactNode } from "react";

import "./globals.css";


export const metadata = {
  title: "智能简历本地工作台",
  description: "用于查看本地运行产物、评分证据、风险提示和投递策略的单用户工作台。",
};


export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
