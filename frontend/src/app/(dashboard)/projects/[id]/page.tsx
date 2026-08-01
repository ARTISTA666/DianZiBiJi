"use client";

import { useRef, useState, useMemo, useCallback, FormEvent, useEffect } from "react";
import { useParams } from "next/navigation";
import { useAuthStore, useProjectStore } from "@/stores";
import { getNoteVersions, getNoteApprovals, type NoteVersion, type NoteApproval } from "@/lib/api";
import { getErrorMessage } from "@/lib/utils";
import { useConfirmDialog } from "@/hooks/use-confirm-dialog";
import { NotesListSkeleton } from "@/components/skeletons";
import { toast } from "sonner";
import { NoteFilters } from "./note-filters";
import { NoteFormDialog, type NoteFormData } from "./note-form-dialog";
import { NoteDetailDialog, type NoteItem } from "./note-detail-dialog";
import { NoteListSection } from "./note-list-section";

const emptyForm: NoteFormData = { title: "", experiment_type: "PCR", experiment_date: "", content_text: "" };

const NOTES_PER_PAGE = 10;

export default function ProjectNotesPage() {
  const { id } = useParams();
  const projectId = Number(id);
  const token = useAuthStore((s) => s.token);
  const user = useAuthStore((s) => s.user);
  const notes = useProjectStore((s) => s.notes);
  const members = useProjectStore((s) => s.members);
  const selectedProject = useProjectStore((s) => s.selectedProject);
  const notesTotal = useProjectStore((s) => s.notesTotal);
  const busy = useProjectStore((s) => s.busy);
  const updateNote = useProjectStore((s) => s.updateNote);
  const createNote = useProjectStore((s) => s.createNote);
  const loadNotesPaginated = useProjectStore((s) => s.loadNotesPaginated);
  const submitNote = useProjectStore((s) => s.submitNote);
  const approveNote = useProjectStore((s) => s.approveNote);
  const returnNote = useProjectStore((s) => s.returnNote);
  const archiveNote = useProjectStore((s) => s.archiveNote);
  const voidNote = useProjectStore((s) => s.voidNote);

  const membership = members.find((m) => m.user_id === user?.id);
  const canReview = user?.role === "super_admin"
    || (selectedProject?.owner_user_id != null && selectedProject.owner_user_id === user?.id)
    || membership?.can_manage === true
    || membership?.can_review === true
    || membership?.project_role === "owner";
  const canWrite = user?.role === "super_admin" || membership?.can_write === true;

  // Filter / search / sort state
  const [statusFilter, setStatusFilter] = useState("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [sortBy, setSortBy] = useState("updated_desc");
  const [currentPage, setCurrentPage] = useState(0);

  // Note form
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingNote, setEditingNote] = useState<number | null>(null);
  const [form, setForm] = useState<NoteFormData>(emptyForm);

  // Detail / versions / approvals
  const [detailNote, setDetailNote] = useState<NoteItem | null>(null);
  const [versions, setVersions] = useState<NoteVersion[]>([]);
  const [approvals, setApprovals] = useState<NoteApproval[]>([]);
  const [comment, setComment] = useState("");
  const detailRequestEpoch = useRef(0);

  // Error
  const [error, setError] = useState("");

  // Saving state
  const [saving, setSaving] = useState(false);

  // Confirm dialog
  const { confirm, ConfirmDialog } = useConfirmDialog();

  // Load notes with current filters
  const fetchNotes = useCallback(() => {
    if (!token) return;
    const skip = currentPage * NOTES_PER_PAGE;
    const params: { skip: number; limit: number; status?: string } = { skip, limit: NOTES_PER_PAGE };
    if (statusFilter !== "all") params.status = statusFilter;
    loadNotesPaginated(token, projectId, params);
  }, [token, projectId, currentPage, statusFilter, loadNotesPaginated]);

  // Re-fetch when page or status filter changes
  useEffect(() => {
    fetchNotes();
  }, [fetchNotes]);

  // Client-side: filter by search, then sort
  const displayedNotes = useMemo(() => {
    let result = [...notes];
    if (searchQuery.trim()) {
      const q = searchQuery.trim().toLowerCase();
      result = result.filter((n) => n.title.toLowerCase().includes(q));
    }
    switch (sortBy) {
      case "updated_desc":
        result.sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime());
        break;
      case "updated_asc":
        result.sort((a, b) => new Date(a.updated_at).getTime() - new Date(b.updated_at).getTime());
        break;
      case "created_desc":
        result.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
        break;
    }
    return result;
  }, [notes, searchQuery, sortBy]);

  const handleStatusChange = (value: string) => {
    setStatusFilter(value);
    setCurrentPage(0);
  };

  const resetForm = () => { setForm(emptyForm); setEditingNote(null); setError(""); };

  const openNew = () => { resetForm(); setDialogOpen(true); };

  const openEdit = async (note: NoteItem) => {
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
    setSaving(true);
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
      fetchNotes();
      toast.success("笔记已保存");
    } catch (e) {
      setError(getErrorMessage(e, "保存失败"));
    } finally {
      setSaving(false);
    }
  };

  const doAction = async (action: string, noteId: number) => {
    if (!token) return;
    try {
      if (action === "submit") await submitNote(token, noteId);
      else if (action === "approve") await approveNote(token, noteId, comment);
      else if (action === "return") await returnNote(token, noteId, comment);
      else if (action === "archive") await archiveNote(token, noteId);
      else if (action === "void") await voidNote(token, noteId, comment);
      setComment("");
      setDetailNote(null);
      fetchNotes();
    } catch (e) {
      setError(getErrorMessage(e, "操作失败"));
    }
  };

  const handleAction = (action: string, noteId: number) => {
    if (action === "archive") {
      confirm("归档笔记", "确定要归档此笔记吗？归档后笔记将变为只读状态。", () => doAction(action, noteId));
    } else if (action === "void") {
      confirm("作废笔记", "确定要作废此笔记吗？此操作不可恢复。", () => doAction(action, noteId));
    } else if (action === "return") {
      confirm("退回笔记", "确定要退回此笔记进行修改吗？", () => doAction(action, noteId));
    } else {
      doAction(action, noteId);
    }
  };

  const showDetail = async (note: NoteItem) => {
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

  if (busy) return <NotesListSkeleton />;

  return (
    <div className="space-y-4">
      {error && <p className="rounded-md bg-destructive/10 px-4 py-2 text-sm text-destructive">{error}</p>}

      {/* 操作栏：状态筛选 + 搜索 + 排序 */}
      <NoteFilters
        searchQuery={searchQuery}
        onSearchChange={setSearchQuery}
        statusFilter={statusFilter}
        onStatusChange={handleStatusChange}
        sortBy={sortBy}
        onSortChange={setSortBy}
        onNewNote={openNew}
        canWrite={canWrite}
      />

      {/* 笔记列表 + 分页 */}
      <NoteListSection
        notes={displayedNotes}
        total={notesTotal}
        page={currentPage}
        onPageChange={setCurrentPage}
        onSelectNote={showDetail}
        searchQuery={searchQuery}
        serverNotesCount={notes.length}
      />

      {/* 新建/编辑 Dialog */}
      <NoteFormDialog
        open={dialogOpen}
        onOpenChange={(o) => { if (!o) resetForm(); setDialogOpen(o); }}
        editingNote={editingNote}
        form={form}
        onFormChange={setForm}
        onSave={handleSave}
        busy={saving}
        error={error}
      />

      {/* 详情 Dialog */}
      <NoteDetailDialog
        open={!!detailNote}
        onOpenChange={(o) => {
          if (!o) {
            detailRequestEpoch.current += 1;
            setDetailNote(null);
            setVersions([]);
            setApprovals([]);
          }
        }}
        note={detailNote}
        comment={comment}
        onCommentChange={setComment}
        onAction={handleAction}
        onEdit={openEdit}
        versions={versions}
        approvals={approvals}
        canReview={canReview}
        canWrite={canWrite}
      />

      {ConfirmDialog}
    </div>
  );
}
