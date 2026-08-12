"use client";

import { Send } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import type { OcrJobResult, StoredFile } from "@/lib/api";

interface OcrDialogProps {
  file: StoredFile | null;
  result: OcrJobResult | null;
  draft: string;
  busy: boolean;
  canReview: boolean;
  onDraftChange: (value: string) => void;
  onConfirm: () => void;
  /** 关闭对话框（Radix open 变化回调，仅 open=false 时触发清理） */
  onOpenChange: (open: boolean) => void;
}

export function OcrDialog({
  file,
  result,
  draft,
  busy,
  canReview,
  onDraftChange,
  onConfirm,
  onOpenChange,
}: OcrDialogProps) {
  return (
    <Dialog open={!!file} onOpenChange={onOpenChange}>
      {file && (
        <DialogContent className="max-w-lg">
          <DialogHeader><DialogTitle>OCR — {file.original_filename}</DialogTitle></DialogHeader>
          <div className="space-y-4">
            {busy ? (
              <div className="space-y-1">
                <p className="text-sm text-muted-foreground">加载 OCR 结果...</p>
                <p className="text-xs text-muted-foreground">图片文本识别通常需要数十秒，请勿关闭窗口</p>
              </div>
            ) : (
              <>
                <div className="space-y-2">
                  <p className="text-sm font-medium">识别文本</p>
                  <div className="rounded-md border bg-muted/30 p-3 text-sm whitespace-pre-wrap max-h-40 overflow-y-auto">{result?.raw_text}</div>
                </div>
                <div className="space-y-2">
                  <p className="text-sm font-medium">校对文本</p>
                  <Textarea
                    aria-label="OCR 校对文本"
                    rows={6}
                    value={draft}
                    onChange={(e) => onDraftChange(e.target.value)}
                    readOnly={result?.review_status === "confirmed" || !canReview}
                  />
                </div>
                {result?.review_status === "confirmed" ? (
                  <p className="rounded-md bg-success/10 px-3 py-2 text-center text-sm text-success">该结果已确认签名</p>
                ) : canReview ? (
                  <Button className="w-full" onClick={onConfirm} disabled={!result || !draft.trim()}>
                    <Send className="mr-2 h-4 w-4" />确认校对并签名
                  </Button>
                ) : (
                  <p className="text-sm text-muted-foreground">仅具审核权限的成员可以确认校对文本。</p>
                )}
              </>
            )}
          </div>
        </DialogContent>
      )}
    </Dialog>
  );
}
