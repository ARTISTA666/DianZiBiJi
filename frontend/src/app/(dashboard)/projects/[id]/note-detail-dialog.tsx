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
import type { NoteVersion, NoteApproval } from "@/lib/api";

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
  canReview = false,
  canWrite = false,
}: NoteDetailDialogProps) {
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
                {approvals.map((a) => (
                  <div key={a.id} className="rounded-md border p-2 text-sm">
                    <span
                      className={
                        a.action === "approved"
                          ? "text-green-600"
                          : "text-red-600"
                      }
                    >
                      {a.action === "approved" ? "✓ 通过" : "✗ 退回"}
                    </span>
                    {a.comment && (
                      <p className="text-muted-foreground mt-1">{a.comment}</p>
                    )}
                  </div>
                ))}
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
