"use client";

import { useRef, useState, useCallback, FormEvent, useEffect } from "react";
import { useParams } from "next/navigation";
import { useAuthStore, useProjectStore } from "@/stores";
import { getNoteVersions, getNoteApprovals, getNoteFiles, type NoteVersion, type NoteApproval, type StoredFile, type Template } from "@/lib/api";
import { getErrorMessage } from "@/lib/utils";
import { useConfirmDialog } from "@/hooks/use-confirm-dialog";
import { useActionFeedback } from "@/hooks/use-action-feedback";
import { NotesListSkeleton } from "@/components/skeletons";
import { ErrorBanner } from "@/components/shared/error-banner";
import { NoteFilters } from "./note-filters";
import { NoteFormDialog, type NoteFormData } from "./note-form-dialog";
import { NoteDetailDialog, type NoteItem } from "./note-detail-dialog";
import { NoteListSection } from "./note-list-section";

const emptyForm: NoteFormData = {
  title: "",
  experiment_type: "",
  template_id: null,
  experiment_date: "",
  fixed_fields_json: {},
  content_text: "",
};

const NOTES_PER_PAGE = 10;

// 审批流转操作成功后的反馈文案（纯前端提示，不影响后端行为）。
const actionSuccessText: Record<string, string> = {
  submit: "已提交审核",
  approve: "已审批通过",
  return: "已退回",
  archive: "已归档",
  void: "已作废",
};

export default function ProjectNotesPage() {
  const { id } = useParams();
  const projectId = Number(id);
  const token = useAuthStore((s) => s.token);
  const user = useAuthStore((s) => s.user);
  const notes = useProjectStore((s) => s.notes);
  const members = useProjectStore((s) => s.members);
  const selectedProject = useProjectStore((s) => s.selectedProject);
  const notesTotal = useProjectStore((s) => s.notesTotal);
  const templates = useProjectStore((s) => s.templates);
  const busy = useProjectStore((s) => s.busy);
  const updateNote = useProjectStore((s) => s.updateNote);
  const createNote = useProjectStore((s) => s.createNote);
  const loadNotesPaginated = useProjectStore((s) => s.loadNotesPaginated);
  const submitNote = useProjectStore((s) => s.submitNote);
  const approveNote = useProjectStore((s) => s.approveNote);
  const returnNote = useProjectStore((s) => s.returnNote);
  const archiveNote = useProjectStore((s) => s.archiveNote);
  const voidNote = useProjectStore((s) => s.voidNote);
  const feedback = useActionFeedback();

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
  const [attachments, setAttachments] = useState<StoredFile[]>([]);
  const [comment, setComment] = useState("");
  const detailRequestEpoch = useRef(0);

  // Error
  const [error, setError] = useState("");

  // Saving state
  const [saving, setSaving] = useState(false);
  const draftReady = useRef(false);
  const draftKey = `eln.note-draft:${projectId}:${editingNote ?? "new"}`;

  useEffect(() => {
    if (!dialogOpen) {
      draftReady.current = false;
      return;
    }
    draftReady.current = false;
    try {
      const saved = window.localStorage.getItem(draftKey);
      if (saved) {
        const parsed = JSON.parse(saved) as Partial<NoteFormData>;
        setForm((current) => ({
          ...current,
          ...parsed,
          fixed_fields_json: parsed.fixed_fields_json ?? current.fixed_fields_json,
        }));
      }
    } catch {
      // A malformed or unavailable local draft must not block normal editing.
    }
    draftReady.current = true;
  }, [dialogOpen, draftKey]);

  useEffect(() => {
    if (!dialogOpen || !draftReady.current) return;
    try {
      window.localStorage.setItem(draftKey, JSON.stringify(form));
    } catch {
      // Local storage is best effort; the explicit save remains authoritative.
    }
  }, [dialogOpen, draftKey, form]);

  // Confirm dialog
  const { confirm, ConfirmDialog } = useConfirmDialog();

  // 搜索输入框：供快捷键 "/" 聚焦
  const searchInputRef = useRef<HTMLInputElement>(null);

  // Load notes with current filters
  const fetchNotes = useCallback(() => {
    if (!token) return;
    const skip = currentPage * NOTES_PER_PAGE;
    const params: { skip: number; limit: number; status?: string; search?: string; sort?: string } = {
      skip,
      limit: NOTES_PER_PAGE,
      search: searchQuery.trim() || undefined,
      sort: sortBy,
    };
    if (statusFilter !== "all") params.status = statusFilter;
    loadNotesPaginated(token, projectId, params);
  }, [token, projectId, currentPage, statusFilter, searchQuery, sortBy, loadNotesPaginated]);

  // Re-fetch when page, filter, search, or sort changes.
  useEffect(() => {
    fetchNotes();
  }, [fetchNotes]);

  const handleStatusChange = (value: string) => {
    setStatusFilter(value);
    setCurrentPage(0);
  };

  const handleSearchChange = (value: string) => {
    setSearchQuery(value);
    setCurrentPage(0);
  };

  const handleSortChange = (value: string) => {
    setSortBy(value);
    setCurrentPage(0);
  };

  const formForTemplate = (template: Template | undefined): NoteFormData => ({
    ...emptyForm,
    template_id: template?.id ?? null,
    experiment_type: template?.experiment_type ?? "",
    fixed_fields_json: Object.fromEntries(
      (template?.schema_json.fields ?? []).map((field) => [field.key, ""]),
    ),
  });

  const resetForm = () => { setForm(emptyForm); setEditingNote(null); setError(""); };

  const openNew = useCallback(() => {
    setForm(formForTemplate(templates[0]));
    setEditingNote(null);
    setError("");
    setDialogOpen(true);
  }, [templates]);

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
        template_id: note.template_id,
        experiment_date: note.experiment_date || "",
        fixed_fields_json: latest.fixed_fields_json ?? {},
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
        template_id: form.template_id,
        fixed_fields_json: form.fixed_fields_json,
        content_json: { text: form.content_text },
      };
      if (editingNote) {
        await updateNote(token, editingNote, payload);
      } else {
        await createNote(token, {
          project_id: projectId,
          ...payload,
        });
      }
      try {
        window.localStorage.removeItem(`eln.note-draft:${projectId}:${editingNote ?? "new"}`);
      } catch {
        // Local storage can be unavailable in private browsing; the server save still stands.
      }
      setDialogOpen(false);
      resetForm();
      fetchNotes();
      feedback.success("笔记已保存");
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
      if (actionSuccessText[action]) feedback.success(actionSuccessText[action]);
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
    setAttachments([]);
    setError("");
    if (token) {
      try {
        const [vs, as, fs] = await Promise.all([
          getNoteVersions(token, note.id),
          getNoteApprovals(token, note.id),
          getNoteFiles(token, note.id),
        ]);
        if (requestEpoch !== detailRequestEpoch.current) return;
        setVersions(vs);
        setApprovals(as);
        setAttachments(fs);
      } catch (e) {
        if (requestEpoch === detailRequestEpoch.current) {
          setError(getErrorMessage(e, "笔记详情加载失败"));
        }
      }
    }
  };

  // 页面快捷键：N 新建笔记、/ 聚焦搜索框。
  // 守卫：输入态（input/textarea/select/contentEditable）、组合键、对话框打开时均不触发。
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const target = e.target;
      if (target instanceof HTMLElement
        && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.tagName === "SELECT" || target.isContentEditable)) return;
      // Radix 对话框（含确认弹窗）打开时禁用快捷键。
      // 限定 data-state="open"：Radix 关闭后内容节点会短暂残留（data-state="closed"，退出动画期），不应继续屏蔽。
      if (document.querySelector('[role="dialog"][data-state="open"], [role="alertdialog"][data-state="open"]')) return;
      if (e.key === "n" || e.key === "N") {
        if (canWrite) {
          // 阻止默认行为，避免按键字符在对话框打开、焦点移到标题输入框后被写入。
          e.preventDefault();
          openNew();
        }
      } else if (e.key === "/") {
        e.preventDefault();
        searchInputRef.current?.focus();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [canWrite, openNew]);

  if (busy) return <NotesListSkeleton />;

  return (
    <div className="space-y-4">
      {error && <ErrorBanner message={error} />}

      {/* 操作栏：状态筛选 + 搜索 + 排序 */}
      <NoteFilters
        searchQuery={searchQuery}
        onSearchChange={handleSearchChange}
        statusFilter={statusFilter}
        onStatusChange={handleStatusChange}
        sortBy={sortBy}
        onSortChange={handleSortChange}
        onNewNote={openNew}
        canWrite={canWrite}
        searchInputRef={searchInputRef}
      />

      {/* 笔记列表 + 分页 */}
      <NoteListSection
        notes={notes}
        total={notesTotal}
        page={currentPage}
        onPageChange={setCurrentPage}
        onSelectNote={showDetail}
      />

      {/* 新建/编辑 Dialog */}
      <NoteFormDialog
        open={dialogOpen}
        onOpenChange={(o) => { if (!o) resetForm(); setDialogOpen(o); }}
        editingNote={editingNote}
        templates={templates}
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
            setAttachments([]);
          }
        }}
        note={detailNote}
        projectId={projectId}
        comment={comment}
        onCommentChange={setComment}
        onAction={handleAction}
        onEdit={openEdit}
        versions={versions}
        approvals={approvals}
        attachments={attachments}
        members={members}
        canReview={canReview}
        canWrite={canWrite}
      />

      {ConfirmDialog}
    </div>
  );
}
