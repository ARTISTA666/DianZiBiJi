"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { CheckCircle, XCircle, FileText, FileCheck } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useAuthStore, useProjectStore } from "@/stores";
import { getNoteVersions, type Note, type ProjectMember } from "@/lib/api";
import { getErrorMessage } from "@/lib/utils";
import { statusText } from "@/components/constants";
import { useActionFeedback } from "@/hooks/use-action-feedback";
import { ApprovalsListSkeleton } from "@/components/skeletons";

/** 卡片内预览最多展示字数，超出折叠。 */
const PREVIEW_LIMIT = 300;

function formatTime(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("zh-CN");
}

interface ApprovalCardProps {
  token: string;
  note: Note;
  members: ProjectMember[];
  comment: string;
  onCommentChange: (value: string) => void;
  onAction: (noteId: number, action: "approve" | "return") => void;
}

function ApprovalCard({ token, note, members, comment, onCommentChange, onAction }: ApprovalCardProps) {
  const [previewText, setPreviewText] = useState("");
  const [submittedAt, setSubmittedAt] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);

  // 拉取最新版内容用于审批前预览；失败静默降级，不阻塞审批操作。
  useEffect(() => {
    let cancelled = false;
    getNoteVersions(token, note.id)
      .then((versions) => {
        if (cancelled) return;
        const latest = versions[0];
        if (!latest) return;
        const text = (latest.content_json?.text as string)
          || (latest.content_json?.content as string)
          || "";
        setPreviewText(text);
        setSubmittedAt(latest.created_at);
      })
      .catch(() => {
        // 预览加载失败时保留审批操作能力，仅缺少内容预览。
      });
    return () => { cancelled = true; };
  }, [token, note.id]);

  const submitter = members.find((m) => m.user_id === note.owner_user_id);
  const needCollapse = previewText.length > PREVIEW_LIMIT;
  const shownText = expanded || !needCollapse ? previewText : `${previewText.slice(0, PREVIEW_LIMIT)}…`;

  return (
    <Card data-testid={`approval-note-${note.id}`}>
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between">
          <div>
            <CardTitle className="text-base flex items-center gap-2">
              <FileText className="h-4 w-4 text-muted-foreground" />
              {note.title}
            </CardTitle>
            <p className="text-xs text-muted-foreground mt-0.5">
              {note.experiment_type} · {note.experiment_date || "—"}
            </p>
            <p className="text-xs text-muted-foreground mt-0.5">
              提交人：{submitter ? `用户 #${note.owner_user_id}` : `#${note.owner_user_id}`}
              {" · 提交时间："}
              {formatTime(submittedAt || note.updated_at)}
            </p>
          </div>
          <Badge variant="secondary">{statusText[note.status] || note.status}</Badge>
        </div>
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          {previewText && (
            <div className="rounded-md border bg-muted/30 p-3 text-sm">
              <p className="whitespace-pre-wrap break-words">{shownText}</p>
              {needCollapse && (
                <button
                  type="button"
                  className="mt-1 text-xs text-primary underline underline-offset-2"
                  onClick={() => setExpanded((v) => !v)}
                >
                  {expanded ? "收起" : "展开全文"}
                </button>
              )}
            </div>
          )}
          <Textarea
            placeholder="审核意见"
            value={comment}
            onChange={(e) => onCommentChange(e.target.value)}
            rows={2}
          />
          <div className="flex gap-2">
            <Button size="sm" className="bg-green-600 hover:bg-green-700" onClick={() => onAction(note.id, "approve")}>
              <CheckCircle className="mr-1 h-4 w-4" />通过
            </Button>
            <Button size="sm" variant="destructive" onClick={() => onAction(note.id, "return")}>
              <XCircle className="mr-1 h-4 w-4" />退回
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

export default function ApprovalsPage() {
  const { id } = useParams();
  const projectId = Number(id);
  const router = useRouter();
  const token = useAuthStore((s) => s.token);
  const pendingNotes = useProjectStore((s) => s.pendingNotes);
  const members = useProjectStore((s) => s.members);
  const loadBaseProjectData = useProjectStore((s) => s.loadBaseProjectData);
  const [comment, setComment] = useState<Record<number, string>>({});
  const [error, setError] = useState("");
  const b = useProjectStore((s) => s.busy);
  const feedback = useActionFeedback();

  const handleError = (msg: string) => {
    if (msg.includes("登录")) {
      router.push("/login");
      return;
    }
    setError(msg);
  };

  const handleAction = async (noteId: number, action: "approve" | "return") => {
    if (!token) return;
    // 退回时缺少意见仅给软提示，不阻断提交，后端行为保持不变。
    if (action === "return" && !(comment[noteId] || "").trim()) {
      toast.info("建议填写退回原因，帮助记录人快速定位修订点");
    }
    try {
      const fn = action === "approve" ? useProjectStore.getState().approveNote : useProjectStore.getState().returnNote;
      await fn(token, noteId, comment[noteId] || "");
      setComment((c) => { const n = { ...c }; delete n[noteId]; return n; });
      loadBaseProjectData(token, projectId);
      feedback.success(action === "approve" ? "已通过" : "已退回");
    } catch (e) {
      const msg = getErrorMessage(e, "操作失败");
      handleError(msg);
      feedback.error(msg);
    }
  };

  if (b) return <ApprovalsListSkeleton />;

  const projectPending = pendingNotes.filter((n) => n.project_id === projectId);

  if (projectPending.length === 0) {
    return (
      <Card className="border-dashed">
        <CardContent className="flex flex-col items-center justify-center py-12 text-center">
          <FileCheck className="h-12 w-12 text-muted-foreground/50 mb-4" />
          <p className="text-lg font-medium text-muted-foreground">所有笔记已审批完毕</p>
          <p className="text-sm text-muted-foreground/70 mt-1">新笔记提交审批后将在此显示</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      {error && (
        <p className="rounded-md bg-destructive/10 px-4 py-2 text-sm text-destructive">
          {error}
          <button className="ml-2 underline" onClick={() => setError("")}>关闭</button>
        </p>
      )}
      {projectPending.map((note) => (
        <ApprovalCard
          key={note.id}
          token={token || ""}
          note={note}
          members={members}
          comment={comment[note.id] || ""}
          onCommentChange={(value) => setComment((c) => ({ ...c, [note.id]: value }))}
          onAction={handleAction}
        />
      ))}
    </div>
  );
}
