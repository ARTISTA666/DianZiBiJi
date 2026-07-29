"use client";

import { useRef, useState, FormEvent, KeyboardEvent } from "react";
import { useParams } from "next/navigation";
import { Plus, FileText, CheckCircle, XCircle, Archive, Trash2, Send } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useAuthStore, useProjectStore } from "@/stores";
import { getNoteVersions, getNoteApprovals, type NoteVersion, type NoteApproval } from "@/lib/api";
import { getErrorMessage } from "@/lib/utils";
import { statusText } from "@/components/constants";

const experimentTypes = ["PCR", "qPCR", "WB", "ELISA", "测序", "细胞培养", "动物实验", "其他"];

const emptyForm = { title: "", experiment_type: "PCR", experiment_date: "", content_text: "" };

const handleCardKeyDown = (e: KeyboardEvent, callback: () => void) => {
  if (e.key === "Enter" || e.key === " ") {
    e.preventDefault();
    callback();
  }
};

export default function ProjectNotesPage() {
  const { id } = useParams();
  const projectId = Number(id);
  const token = useAuthStore((s) => s.token);
  const notes = useProjectStore((s) => s.notes);
  const busy = useProjectStore((s) => s.busy);
  const updateNote = useProjectStore((s) => s.updateNote);
  const createNote = useProjectStore((s) => s.createNote);
  const loadBaseProjectData = useProjectStore((s) => s.loadBaseProjectData);
  const submitNote = useProjectStore((s) => s.submitNote);
  const approveNote = useProjectStore((s) => s.approveNote);
  const returnNote = useProjectStore((s) => s.returnNote);
  const archiveNote = useProjectStore((s) => s.archiveNote);
  const voidNote = useProjectStore((s) => s.voidNote);

  // Note form
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingNote, setEditingNote] = useState<number | null>(null);
  const [form, setForm] = useState(emptyForm);

  // Detail / versions / approvals
  const [detailNote, setDetailNote] = useState<ReturnType<typeof useProjectStore.getState>["notes"][0] | null>(null);
  const [versions, setVersions] = useState<NoteVersion[]>([]);
  const [approvals, setApprovals] = useState<NoteApproval[]>([]);
  const [comment, setComment] = useState("");
  const detailRequestEpoch = useRef(0);

  // Error
  const [error, setError] = useState("");

  const resetForm = () => { setForm(emptyForm); setEditingNote(null); setError(""); };

  const openNew = () => { resetForm(); setDialogOpen(true); };

  const openEdit = async (note: ReturnType<typeof useProjectStore.getState>["notes"][0]) => {
    if (!token) return;
    setError("");
    try {
      const vs = await getNoteVersions(token, note.id);
      const latest = vs[0];
      if (!latest) throw new Error("未找到可编辑的笔记版本");
      const text = (latest.content_json?.text as string)
        || (latest.content_json?.content as string)
        || "";
      detailRequestEpoch.current += 1;
      setDetailNote(null);
      setEditingNote(note.id);
      setForm({
        title: note.title,
        experiment_type: note.experiment_type,
        experiment_date: note.experiment_date || "",
        content_text: text,
      });
      setDialogOpen(true);
    } catch (e) {
      setError(getErrorMessage(e, "笔记内容加载失败，未进入编辑模式"));
    }
  };

  const handleSave = async (e: FormEvent) => {
    e.preventDefault();
    if (!token) return;
    setError("");
    try {
      const payload = {
        title: form.title,
        experiment_type: form.experiment_type,
        experiment_date: form.experiment_date || undefined,
        content_json: { text: form.content_text },
      };
      if (editingNote) {
        await updateNote(token, editingNote, payload);
      } else {
        await createNote(token, {
          project_id: projectId,
          ...payload,
          fixed_fields_json: {},
        });
      }
      setDialogOpen(false);
      resetForm();
      // Refresh project data
      loadBaseProjectData(token, projectId);
    } catch (e) {
      setError(getErrorMessage(e, "保存失败"));
    }
  };

  const handleAction = async (action: string, noteId: number) => {
    if (!token) return;
    try {
      if (action === "submit") await submitNote(token, noteId);
      else if (action === "approve") await approveNote(token, noteId, comment);
      else if (action === "return") await returnNote(token, noteId, comment);
      else if (action === "archive") await archiveNote(token, noteId);
      else if (action === "void") await voidNote(token, noteId, comment);
      setComment("");
      setDetailNote(null);
      loadBaseProjectData(token, projectId);
    } catch (e) {
      setError(getErrorMessage(e, "操作失败"));
    }
  };

  const showDetail = async (note: ReturnType<typeof useProjectStore.getState>["notes"][0]) => {
    const requestEpoch = ++detailRequestEpoch.current;
    setDetailNote(note);
    setComment("");
    setVersions([]);
    setApprovals([]);
    setError("");
    if (token) {
      try {
        const [vs, as] = await Promise.all([
          getNoteVersions(token, note.id),
          getNoteApprovals(token, note.id),
        ]);
        if (requestEpoch !== detailRequestEpoch.current) return;
        setVersions(vs);
        setApprovals(as);
      } catch (e) {
        if (requestEpoch === detailRequestEpoch.current) {
          setError(getErrorMessage(e, "笔记详情加载失败"));
        }
      }
    }
  };

  if (busy) return <p className="text-sm text-muted-foreground py-8 text-center">加载中...</p>;

  return (
    <div className="space-y-4">
      {error && <p className="rounded-md bg-destructive/10 px-4 py-2 text-sm text-destructive">{error}</p>}

      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">{notes.length} 条笔记</p>
        <Button size="sm" onClick={openNew}><Plus className="mr-2 h-4 w-4" />新建笔记</Button>
      </div>

      {notes.length === 0 ? (
        <Card className="border-dashed">
          <CardContent className="py-12 text-center">
            <FileText className="mx-auto h-10 w-10 text-muted-foreground/50" />
            <p className="mt-3 text-sm text-muted-foreground">暂无笔记</p>
            <Button variant="outline" size="sm" className="mt-3" onClick={openNew}>新建笔记</Button>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {notes.map((note) => (
            <Card key={note.id} role="button" tabIndex={0} className="cursor-pointer transition-shadow hover:shadow-sm" onClick={() => showDetail(note)} onKeyDown={(e) => handleCardKeyDown(e, () => showDetail(note))}>
              <CardHeader className="pb-3">
                <div className="flex items-start justify-between">
                  <div className="min-w-0 flex-1">
                    <CardTitle className="text-base">{note.title}</CardTitle>
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      {note.experiment_type} · {note.experiment_date || "—"}
                    </p>
                  </div>
                  <Badge variant={note.status === "approved" ? "default" : note.status === "submitted" ? "secondary" : "outline"}>
                    {statusText[note.status] || note.status}
                  </Badge>
                </div>
              </CardHeader>
            </Card>
          ))}
        </div>
      )}

      {/* 新建/编辑 Dialog */}
      <Dialog open={dialogOpen} onOpenChange={(o) => { if (!o) resetForm(); setDialogOpen(o); }}>
        <DialogContent className="max-w-lg">
          <DialogHeader><DialogTitle>{editingNote ? "编辑笔记" : "新建笔记"}</DialogTitle></DialogHeader>
          <form onSubmit={handleSave} className="space-y-4 pt-2">
            <div className="space-y-2">
              <Label htmlFor="ntitle">标题</Label>
              <Input id="ntitle" required value={form.title} onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))} />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>实验类型</Label>
                <Select value={form.experiment_type} onValueChange={(v) => setForm((f) => ({ ...f, experiment_type: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>{experimentTypes.map((t) => (<SelectItem key={t} value={t}>{t}</SelectItem>))}</SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="ndate">实验日期</Label>
                <Input id="ndate" type="date" value={form.experiment_date} onChange={(e) => setForm((f) => ({ ...f, experiment_date: e.target.value }))} />
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="ncontent">内容</Label>
              <Textarea id="ncontent" rows={8} value={form.content_text} onChange={(e) => setForm((f) => ({ ...f, content_text: e.target.value }))} placeholder="实验笔记内容..." />
            </div>
            {error && <p className="text-sm text-destructive">{error}</p>}
            <div className="flex justify-end gap-2">
              <Button type="button" variant="outline" onClick={() => { resetForm(); setDialogOpen(false); }}>取消</Button>
              <Button type="submit" disabled={!form.title.trim()}>保存</Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      {/* 详情 Dialog */}
      <Dialog open={!!detailNote} onOpenChange={(o) => {
        if (!o) {
          detailRequestEpoch.current += 1;
          setDetailNote(null);
          setVersions([]);
          setApprovals([]);
        }
      }}>
        {detailNote && (
          <DialogContent className="max-w-xl max-h-[80vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle>{detailNote.title}</DialogTitle>
            </DialogHeader>
            <div className="space-y-4">
              <div className="flex gap-2 text-sm text-muted-foreground">
                <Badge variant="outline">{detailNote.experiment_type}</Badge>
                <span>{detailNote.experiment_date}</span>
                <Badge>{statusText[detailNote.status] || detailNote.status}</Badge>
              </div>

              {versions.length > 0 && (
                <div className="rounded-md border p-3">
                  <p className="text-sm font-medium mb-1">最新版本（v{versions[0].version_number}）</p>
                  <p className="text-sm whitespace-pre-wrap">
                    {(versions[0].content_json?.text as string) || JSON.stringify(versions[0].content_json, null, 2)}
                  </p>
                </div>
              )}

              {/* 审批记录 */}
              {approvals.length > 0 && (
                <div className="space-y-2">
                  <p className="text-sm font-medium">审批记录</p>
                  {approvals.map((a) => (
                    <div key={a.id} className="rounded-md border p-2 text-sm">
                      <span className={a.action === "approved" ? "text-green-600" : "text-red-600"}>
                        {a.action === "approved" ? "✓ 通过" : "✗ 退回"}
                      </span>
                      {a.comment && <p className="text-muted-foreground mt-1">{a.comment}</p>}
                    </div>
                  ))}
                </div>
              )}

              {/* 审批操作 */}
              <Textarea placeholder="审核意见（可选）" value={comment} onChange={(e) => setComment(e.target.value)} rows={2} />
              <div className="flex flex-wrap gap-2">
                {(detailNote.status === "draft" || detailNote.status === "returned") && (
                  <Button size="sm" onClick={() => handleAction("submit", detailNote.id)}>
                    <Send className="mr-1 h-4 w-4" />提交审核
                  </Button>
                )}
                {detailNote.status === "submitted" && (
                  <>
                    <Button size="sm" variant="default" className="bg-green-600 hover:bg-green-700" onClick={() => handleAction("approve", detailNote.id)}>
                      <CheckCircle className="mr-1 h-4 w-4" />通过
                    </Button>
                    <Button size="sm" variant="destructive" onClick={() => handleAction("return", detailNote.id)}>
                      <XCircle className="mr-1 h-4 w-4" />退回
                    </Button>
                  </>
                )}
                {(detailNote.status === "draft" || detailNote.status === "returned") && (
                  <>
                    <Button size="sm" variant="outline" onClick={() => openEdit(detailNote)}>
                      <FileText className="mr-1 h-4 w-4" />编辑
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => handleAction("archive", detailNote.id)}>
                      <Archive className="mr-1 h-4 w-4" />归档
                    </Button>
                  </>
                )}
                {detailNote.status !== "voided" && detailNote.status !== "archived" && (
                  <Button size="sm" variant="ghost" className="text-destructive" onClick={() => handleAction("void", detailNote.id)}>
                    <Trash2 className="mr-1 h-4 w-4" />作废
                  </Button>
                )}
              </div>
            </div>
          </DialogContent>
        )}
      </Dialog>
    </div>
  );
}
