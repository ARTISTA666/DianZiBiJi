"use client";

import {
  FileText,
  Send,
  CheckCircle,
  XCircle,
  Archive,
  Trash2,
  Image as ImageIcon,
} from "lucide-react";
import Link from "next/link";
import { useMemo } from "react";
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
import { fileDownloadUrl, type NoteVersion, type NoteApproval, type ProjectMember, type StoredFile } from "@/lib/api";
import { ImageCarousel, type CarouselImage } from "@/components/image-carousel";

export type NoteItem = {
  id: number;
  template_id: number | null;
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
  projectId: number;
  comment: string;
  onCommentChange: (value: string) => void;
  onAction: (action: string, noteId: number) => void;
  onEdit: (note: NoteItem) => void;
  versions: NoteVersion[];
  approvals: NoteApproval[];
  attachments: StoredFile[];
  members: ProjectMember[];
  canReview?: boolean;
  canWrite?: boolean;
}

const isImageFile = (file: StoredFile) => {
  if (file.mime_type?.startsWith("image/")) return true;
  return /\.(png|jpe?g|gif|webp|svg|bmp|ico)$/i.test(file.original_filename);
};

export function NoteDetailDialog({
  open,
  onOpenChange,
  note,
  projectId,
  comment,
  onCommentChange,
  onAction,
  onEdit,
  versions,
  approvals,
  attachments,
  members,
  canReview = false,
  canWrite = false,
}: NoteDetailDialogProps) {
  // 审批记录按 created_at 倒序返回，第一条退回即最近一次退回意见。
  const latestReturn = approvals.find((a) => a.action === "returned");

  // 提取日记关联的多张图片（优先附件图片，其次正文中的图片）
  const noteImages: CarouselImage[] = useMemo(() => {
    const list: CarouselImage[] = [];
    const seenUrls = new Set<string>();

    // 1. 来自附件中的图片文件
    attachments.forEach((file) => {
      if (isImageFile(file)) {
        const url = fileDownloadUrl(file.id);
        if (!seenUrls.has(url)) {
          seenUrls.add(url);
          list.push({
            id: `file-${file.id}`,
            fileId: file.id,
            url,
            title: file.original_filename,
          });
        }
      }
    });

    // 2. 来自最新版本正文 content_json 中的 images 数组
    if (versions.length > 0) {
      const contentJson = versions[0].content_json;
      if (Array.isArray(contentJson?.images)) {
        contentJson.images.forEach((imgItem: unknown, idx: number) => {
          if (typeof imgItem === "string" && !seenUrls.has(imgItem)) {
            seenUrls.add(imgItem);
            list.push({
              id: `content-img-${idx}`,
              url: imgItem,
              title: `正文图片 ${idx + 1}`,
            });
          } else if (imgItem && typeof imgItem === "object" && "url" in imgItem) {
            const item = imgItem as { url: string; title?: string };
            if (item.url && !seenUrls.has(item.url)) {
              seenUrls.add(item.url);
              list.push({
                id: `content-img-${idx}`,
                url: item.url,
                title: item.title || `正文图片 ${idx + 1}`,
              });
            }
          }
        });
      }

      // 3. 从 Markdown 语法 ![alt](url) 解析
      const text = typeof contentJson?.text === "string" ? contentJson.text : "";
      const mdRegex = /!\[(.*?)\]\((.*?)\)/g;
      let match: RegExpExecArray | null;
      let mdIndex = 0;
      while ((match = mdRegex.exec(text)) !== null) {
        const alt = match[1];
        const url = match[2];
        if (url && !seenUrls.has(url)) {
          seenUrls.add(url);
          list.push({
            id: `md-img-${mdIndex++}`,
            url,
            title: alt || `图片 ${list.length + 1}`,
          });
        }
      }
    }

    return list;
  }, [attachments, versions]);

  // 过滤非图片附件
  const nonImageAttachments = useMemo(
    () => attachments.filter((file) => !isImageFile(file)),
    [attachments]
  );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      {note && (
        <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto">
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
              <div className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive" role="alert">
                <p className="font-medium">最近退回意见</p>
                <p className="mt-0.5 whitespace-pre-wrap">{latestReturn.comment || "退回时未填写意见"}</p>
              </div>
            )}

            {/* 日记多图画廊与左右切换轮播 */}
            {noteImages.length > 0 && (
              <div className="space-y-2 rounded-lg border bg-muted/20 p-3">
                <div className="flex items-center justify-between">
                  <p className="text-sm font-medium flex items-center gap-1.5">
                    <ImageIcon className="h-4 w-4 text-primary" />
                    日记图片（{noteImages.length} 张）
                  </p>
                  {noteImages.length > 1 && (
                    <span className="text-xs text-muted-foreground">
                      可点击左右箭头、小圆点或全屏切换查看
                    </span>
                  )}
                </div>
                <ImageCarousel images={noteImages} />
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

            {/* 非图片附件 */}
            {nonImageAttachments.length > 0 && (
              <div className="space-y-2">
                <p className="text-sm font-medium">其他附件文档</p>
                {nonImageAttachments.map((file) => (
                  <Link
                    key={file.id}
                    href={`/projects/${projectId}/data#file-${file.id}`}
                    className="block rounded-md border p-2 text-sm hover:bg-muted/60"
                  >
                    {file.original_filename}
                  </Link>
                ))}
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
                              ? "text-success"
                              : "text-destructive"
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
                    variant="success"
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
