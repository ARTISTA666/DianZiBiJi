"use client";

import { ClipboardCheck, CheckCircle2, XCircle } from "lucide-react";
import type { Note } from "@/lib/api";
import { cardClass } from "../shared/utils";

interface ApprovalsPanelProps {
  pendingNotes: Note[];
  selectedProjectId: number | null;
  approvalComment: string;
  onApprovalCommentChange: (v: string) => void;
  canReviewSelectedProject: boolean;
  onApprove: (noteId: number, comment: string) => void;
  onReturn: (noteId: number, comment: string) => void;
}

export function ApprovalsPanel({
  pendingNotes,
  selectedProjectId,
  approvalComment,
  onApprovalCommentChange,
  canReviewSelectedProject,
  onApprove,
  onReturn,
}: ApprovalsPanelProps) {
  const projectPendingNotes = pendingNotes.filter(
    (note) => !selectedProjectId || note.project_id === selectedProjectId
  );

  return (
    <div className={cardClass("p-5")}>
      <h2 className="flex items-center gap-2 font-semibold"><ClipboardCheck size={18} />审批中心</h2>
      {!canReviewSelectedProject && (
        <p className="mt-4 rounded-md border border-border bg-surface px-3 py-2 text-sm text-muted">
          当前账号没有项目审核权限。
        </p>
      )}
      <div className="mt-4 space-y-2">
        {projectPendingNotes.length === 0 && (
          <p className="text-sm text-muted">当前项目暂无待审核笔记。</p>
        )}
        {projectPendingNotes.map((note) => (
          <div key={note.id} className="rounded-md border border-border p-3">
            <p className="font-medium">{note.title}</p>
            <p className="mt-1 text-xs text-muted">项目 {note.project_id} · {note.experiment_type}</p>
            {canReviewSelectedProject && (
              <>
                <textarea
                  className="mt-3 w-full rounded-md border border-border px-3 py-2 text-sm"
                  placeholder="审核意见"
                  value={approvalComment}
                  onChange={(e) => onApprovalCommentChange(e.target.value)}
                />
                <div className="mt-2 flex gap-2">
                  <button
                    type="button"
                    onClick={() => onApprove(note.id, approvalComment)}
                    className="flex items-center gap-1 rounded-md bg-accent px-3 py-1 text-sm text-white"
                  >
                    <CheckCircle2 size={15} />通过
                  </button>
                  <button
                    type="button"
                    onClick={() => onReturn(note.id, approvalComment)}
                    className="flex items-center gap-1 rounded-md border border-border px-3 py-1 text-sm"
                  >
                    <XCircle size={15} />退回
                  </button>
                </div>
              </>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
