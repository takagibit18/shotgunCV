import type { ReactNode } from "react";

import "./globals.css";


export const metadata = {
  title: "ShotgunCV 运行查看器",
  description: "用于查看 ShotgunCV 运行产物的只读界面。",
};


export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
