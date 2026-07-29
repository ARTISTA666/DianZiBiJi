import type { Metadata } from "next";
import "./globals.css";
import { ToastProvider } from "@/components/shared/ToastProvider";

export const metadata: Metadata = {
  title: "智能电子实验笔记系统",
  description: "课题组级智能 ELN MVP",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body className="min-h-screen bg-background antialiased">
        <ToastProvider>{children}</ToastProvider>
      </body>
    </html>
  );
}
