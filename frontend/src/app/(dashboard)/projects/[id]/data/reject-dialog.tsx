"use client";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import type { StoredFile } from "@/lib/api";

interface RejectDialogProps {
  file: StoredFile | null;
  comment: string;
  busy: boolean;
  onCommentChange: (value: string) => void;
  onConfirm: () => void;
  onClose: () => void;
}

export function RejectDialog({
  file,
  comment,
  busy,
  onCommentChange,
  onConfirm,
  onClose,
}: RejectDialogProps) {
  return (
    <Dialog
      open={!!file}
      onOpenChange={(open) => { if (!open) onClose(); }}
    >
      {file && (
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>拒绝资料 — {file.original_filename}</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <p className="text-sm text-muted-foreground">请填写拒绝原因，便于上传者快速定位问题并修正。</p>
            <Textarea
              aria-label="审核意见"
              placeholder="审核意见"
              value={comment}
              onChange={(e) => onCommentChange(e.target.value)}
              rows={3}
              autoFocus
            />
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={onClose} disabled={busy}>取消</Button>
              <Button variant="destructive" onClick={onConfirm} disabled={busy} isLoading={busy}>
                {busy ? "提交中..." : "确认拒绝"}
              </Button>
            </div>
          </div>
        </DialogContent>
      )}
    </Dialog>
  );
}
