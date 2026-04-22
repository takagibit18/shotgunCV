import type { ReactNode } from "react";

import "./globals.css";


export const metadata = {
  title: "ShotgunCV Run Viewer",
  description: "Read-only viewer for ShotgunCV run artifacts.",
};


export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
