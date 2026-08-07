"use client";

import {
  FileText,
  Send,
  CheckCircle,
  XCircle,
  Archive,
  Trash2,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { statusText } from "@/components/constants";
import type { NoteVersion, NoteApproval, ProjectMember } from "@/lib/api";

export type NoteItem = {
  id: number;
  title: string;
  experiment_type: string;
  experiment_date: string | null;
  status: string;
  created_at: string;
  updated_at: string;
};

interface NoteDetailDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  note: NoteItem | null;
  comment: string;
  onCommentChange: (value: string) => void;
  onAction: (action: string, noteId: number) => void;
  onEdit: (note: NoteItem) => void;
  versions: NoteVersion[];
  approvals: NoteApproval[];
  members: ProjectMember[];
  canReview?: boolean;
  canWrite?: boolean;
}

export function NoteDetailDialog({
  open,
  onOpenChange,
  note,
  comment,
  onCommentChange,
  onAction,
  onEdit,
  versions,
  approvals,
  members,
  canReview = false,
  canWrite = false,
}: NoteDetailDialogProps) {
  // 审批记录按 created_at 倒序返回，第一条退回即最近一次退回意见。
  const latestReturn = approvals.find((a) => a.action === "returned");
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      {note && (
        <DialogContent className="max-w-xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{note.title}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div className="flex gap-2 text-sm text-muted-foreground">
              <Badge variant="outline">{note.experiment_type}</Badge>
              <span>{note.experiment_date}</span>
              <Badge>{statusText[note.status] || note.status}</Badge>
            </div>

            {/* 已退回笔记置顶展示最近一条退回意见，便于记录人快速定位修订点 */}
            {note.status === "returned" && latestReturn && (
              <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
                <p className="font-medium">最近退回意见</p>
                <p className="mt-0.5 whitespace-pre-wrap">{latestReturn.comment || "退回时未填写意见"}</p>
              </div>
            )}

            {versions.length > 0 && (
              <div className="rounded-md border p-3">
                <p className="text-sm font-medium mb-1">
                  最新版本（v{versions[0].version_number}）
                </p>
                <p className="text-sm whitespace-pre-wrap">
                  {(versions[0].content_json?.text as string) ||
                    JSON.stringify(versions[0].content_json, null, 2)}
                </p>
              </div>
            )}

            {/* 审批记录 */}
            {approvals.length > 0 && (
              <div className="space-y-2">
                <p className="text-sm font-medium">审批记录</p>
                {approvals.map((a) => {
                  const isMember = members.some((m) => m.user_id === a.reviewer_user_id);
                  return (
                    <div key={a.id} className="rounded-md border p-2 text-sm">
                      <div className="flex flex-wrap items-center justify-between gap-1">
                        <span
                          className={
                            a.action === "approved"
                              ? "text-green-600"
                              : "text-red-600"
                          }
                        >
                          {a.action === "approved" ? "✓ 通过" : "✗ 退回"}
                        </span>
                        <span className="text-xs text-muted-foreground">
                          {isMember ? `用户 #${a.reviewer_user_id}` : `#${a.reviewer_user_id}`}
                          {" · "}
                          {new Date(a.created_at).toLocaleString("zh-CN")}
                        </span>
                      </div>
                      {a.comment && (
                        <p className="text-muted-foreground mt-1">{a.comment}</p>
                      )}
                    </div>
                  );
                })}
              </div>
            )}

            {/* 审批操作 */}
            {canReview && (
              <Textarea
                placeholder="审核意见（可选）"
                value={comment}
                onChange={(e) => onCommentChange(e.target.value)}
                rows={2}
              />
            )}
            <div className="flex flex-wrap gap-2">
              {canWrite && (note.status === "draft" || note.status === "returned") && (
                <Button size="sm" onClick={() => onAction("submit", note.id)}>
                  <Send className="mr-1 h-4 w-4" />
                  提交审核
                </Button>
              )}
              {note.status === "submitted" && canReview && (
                <>
                  <Button
                    size="sm"
                    variant="default"
                    className="bg-green-600 hover:bg-green-700"
                    onClick={() => onAction("approve", note.id)}
                  >
                    <CheckCircle className="mr-1 h-4 w-4" />
                    通过
                  </Button>
                  <Button
                    size="sm"
                    variant="destructive"
                    onClick={() => onAction("return", note.id)}
                  >
                    <XCircle className="mr-1 h-4 w-4" />
                    退回
                  </Button>
                </>
              )}
              {canWrite && (note.status === "draft" || note.status === "returned") && (
                <>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => onEdit(note)}
                  >
                    <FileText className="mr-1 h-4 w-4" />
                    编辑
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => onAction("archive", note.id)}
                  >
                    <Archive className="mr-1 h-4 w-4" />
                    归档
                  </Button>
                </>
              )}
              {canWrite && note.status !== "voided" && note.status !== "archived" && (
                <Button
                  size="sm"
                  variant="ghost"
                  className="text-destructive"
                  onClick={() => onAction("void", note.id)}
                >
                  <Trash2 className="mr-1 h-4 w-4" />
                  作废
                </Button>
              )}
            </div>
          </div>
        </DialogContent>
      )}
    </Dialog>
  );
}
