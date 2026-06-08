import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "智能电子实验笔记系统",
  description: "课题组级智能 ELN MVP",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}

