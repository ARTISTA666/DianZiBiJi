"use client";

import { useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { CheckCircle, XCircle, FileText } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useAuthStore, useProjectStore } from "@/stores";
import { getErrorMessage } from "@/lib/utils";
import { statusText } from "@/components/constants";

export default function ApprovalsPage() {
  const { id } = useParams();
  const projectId = Number(id);
  const router = useRouter();
  const token = useAuthStore((s) => s.token);
  const pendingNotes = useProjectStore((s) => s.pendingNotes);
  const loadBaseProjectData = useProjectStore((s) => s.loadBaseProjectData);
  const [comment, setComment] = useState<Record<number, string>>({});
  const [error, setError] = useState("");
  const b = useProjectStore((s) => s.busy);

  const handleError = (msg: string) => {
    if (msg.includes("登录")) {
      router.push("/login");
      return;
    }
    setError(msg);
  };

  const handleAction = async (noteId: number, action: "approve" | "return") => {
    if (!token) return;
    try {
      const fn = action === "approve" ? useProjectStore.getState().approveNote : useProjectStore.getState().returnNote;
      await fn(token, noteId, comment[noteId] || "");
      setComment((c) => { const n = { ...c }; delete n[noteId]; return n; });
      loadBaseProjectData(token, projectId);
    } catch (e) {
      handleError(getErrorMessage(e, "操作失败"));
    }
  };

  if (b) return <p className="text-sm text-muted-foreground py-8 text-center">加载中...</p>;

  const projectPending = pendingNotes.filter((n) => n.project_id === projectId);

  if (projectPending.length === 0) {
    return <Card className="border-dashed"><CardContent className="py-12 text-center"><p className="text-sm text-muted-foreground">暂无待审批笔记</p></CardContent></Card>;
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
        <Card key={note.id} data-testid={`approval-note-${note.id}`}>
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
              </div>
              <Badge variant="secondary">{statusText[note.status] || note.status}</Badge>
            </div>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              <Textarea
                placeholder="审核意见"
                value={comment[note.id] || ""}
                onChange={(e) => setComment((c) => ({ ...c, [note.id]: e.target.value }))}
                rows={2}
              />
              <div className="flex gap-2">
                <Button size="sm" className="bg-green-600 hover:bg-green-700" onClick={() => handleAction(note.id, "approve")}>
                  <CheckCircle className="mr-1 h-4 w-4" />通过
                </Button>
                <Button size="sm" variant="destructive" onClick={() => handleAction(note.id, "return")}>
                  <XCircle className="mr-1 h-4 w-4" />退回
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
