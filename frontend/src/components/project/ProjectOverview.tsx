"use client";

import type { Note, StoredFile } from "@/lib/api";
import { cardClass } from "../shared/utils";
import { statusText } from "../constants";

interface ProjectOverviewProps {
  notes: Note[];
  pendingNotes: Note[];
  files: StoredFile[];
  selectedProjectId: number | null;
  onNavigateNotes: (note: Note) => void;
  onNavigateApprovals: () => void;
  onNavigateFiles: () => void;
}

export function ProjectOverview({
  notes,
  pendingNotes,
  files,
  selectedProjectId,
  onNavigateNotes,
  onNavigateApprovals,
  onNavigateFiles,
}: ProjectOverviewProps) {
  return (
    <div className="grid gap-4 md:grid-cols-3">
      <div className={cardClass("p-5")}>
        <h2 className="font-semibold">最近实验笔记</h2>
        <div className="mt-4 space-y-2">
          {notes.slice(0, 5).map((note) => (
            <button
              key={note.id}
              type="button"
              onClick={() => onNavigateNotes(note)}
              className="w-full rounded-md border border-border px-3 py-2 text-left text-sm hover:bg-surface"
            >
              <span className="font-medium">{note.title}</span>
              <span className="mt-1 block text-xs text-muted">{statusText[note.status] || note.status}</span>
            </button>
          ))}
          {notes.length === 0 && <p className="text-sm text-muted">当前项目还没有实验笔记。</p>}
        </div>
      </div>
      <div className={cardClass("p-5")}>
        <h2 className="font-semibold">待处理审批</h2>
        <p className="mt-4 text-3xl font-semibold">
          {pendingNotes.filter((note) => !selectedProjectId || note.project_id === selectedProjectId).length}
        </p>
        <button
          type="button"
          onClick={onNavigateApprovals}
          className="mt-4 rounded-md border border-border px-3 py-2 text-sm"
        >
          查看审批中心
        </button>
      </div>
      <div className={cardClass("p-5")}>
        <h2 className="font-semibold">资料库状态</h2>
        <div className="mt-4 space-y-2 text-sm text-muted">
          <p>文件总数：{files.length}</p>
          <p>
            待审核资料：
            {files.filter((f) => f.file_category === "knowledge_document" && f.status === "uploaded").length}
          </p>
          <p>
            待同步资料：
            {files.filter((f) => f.knowledge_sync_status === "pending_sync").length}
          </p>
        </div>
        <button
          type="button"
          onClick={onNavigateFiles}
          className="mt-4 rounded-md border border-border px-3 py-2 text-sm"
        >
          打开资料库
        </button>
      </div>
    </div>
  );
}
