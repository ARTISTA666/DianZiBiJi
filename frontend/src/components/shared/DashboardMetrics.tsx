"use client";

import { FileText, ClipboardCheck, Paperclip, Sparkles } from "lucide-react";
import { cardClass } from "./utils";

interface DashboardMetricsProps {
  notes: Array<{ id: number }>;
  pendingNotes: Array<{ id: number }>;
  files: Array<{ id: number }>;
  ragInitialized: boolean;
}

export function DashboardMetrics({ notes, pendingNotes, files, ragInitialized }: DashboardMetricsProps) {
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      {[
        { icon: FileText, label: "实验笔记", value: notes.length },
        { icon: ClipboardCheck, label: "待审核", value: pendingNotes.length },
        { icon: Paperclip, label: "项目文件", value: files.length },
        { icon: Sparkles, label: "AI 能力", value: ragInitialized ? "已启用" : "待初始化" },
      ].map((item) => (
        <div key={item.label} className={cardClass("p-4 transition-shadow hover:shadow-[0_8px_24px_rgba(23,32,51,0.08]")}>
          <div className="flex items-center justify-between">
            <span className="text-sm text-muted">{item.label}</span>
            <item.icon size={18} className="text-brand" />
          </div>
          <p className="mt-3 text-2xl font-semibold">{item.value}</p>
        </div>
      ))}
    </div>
  );
}
