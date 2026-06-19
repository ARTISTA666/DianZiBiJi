"use client";

import { FileText, CheckCircle2, XCircle } from "lucide-react";
import type { Note, NoteVersion, NoteApproval, Template } from "@/lib/api";
import { cardClass } from "../shared/utils";
import { statusText } from "../constants";

export interface NoteEditorState {
  id?: number;
  title: string;
  experiment_type: string;
  experiment_date: string;
  template_id: number | null;
  fixed_fields_json: Record<string, string>;
  content_text: string;
}

interface NotesPanelProps {
  editor: NoteEditorState;
  onEditorChange: (editor: NoteEditorState) => void;
  selectedNote: Note | null;
  selectedTemplate: Template | null;
  templates: Template[];
  notes: Note[];
  filteredNotes: Note[];
  noteFilters: { keyword: string; status: string; experiment_type: string };
  onNoteFiltersChange: (filters: { keyword: string; status: string; experiment_type: string }) => void;
  experimentTypes: string[];
  versions: NoteVersion[];
  approvals: NoteApproval[];
  canWriteSelectedProject: boolean;
  canReviewSelectedProject: boolean;
  canSubmitSelectedNote: boolean;
  onSaveNote: (e: React.FormEvent<HTMLFormElement>) => void;
  onEditNote: (note: Note) => void;
  onNewNote: () => void;
  onApplyTemplate: (templateId: number) => void;
  onSubmitNote: () => void;
  onArchiveNote: () => void;
  onVoidNote: () => void;
}

export function NotesPanel({
  editor,
  onEditorChange,
  selectedNote,
  selectedTemplate,
  templates,
  notes: _notes,
  filteredNotes,
  noteFilters,
  onNoteFiltersChange,
  experimentTypes,
  versions,
  approvals,
  canWriteSelectedProject,
  canReviewSelectedProject,
  canSubmitSelectedNote,
  onSaveNote,
  onEditNote,
  onNewNote,
  onApplyTemplate,
  onSubmitNote,
  onArchiveNote,
  onVoidNote,
}: NotesPanelProps) {
  return (
    <div className="grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
      <form onSubmit={onSaveNote} className={cardClass("p-5")}>
        <div className="flex items-center justify-between">
          <h2 className="flex items-center gap-2 font-semibold"><FileText size={18} />实验笔记编辑</h2>
          {canWriteSelectedProject && (
            <button type="button" onClick={onNewNote} className="rounded-md border border-border px-3 py-1 text-sm">
              新建
            </button>
          )}
        </div>
        {!canWriteSelectedProject && (
          <p className="mt-4 rounded-md border border-border bg-surface px-3 py-2 text-sm text-muted">
            当前账号仅可查看实验笔记，不能创建或编辑。
          </p>
        )}
        <div className="mt-4 grid gap-3 md:grid-cols-2">
          <input
            disabled={!canWriteSelectedProject}
            className="rounded-md border border-border px-3 py-2 disabled:bg-surface disabled:text-muted"
            placeholder="实验标题"
            value={editor.title}
            onChange={(e) => onEditorChange({ ...editor, title: e.target.value })}
            required
          />
          <select
            disabled={!canWriteSelectedProject}
            className="rounded-md border border-border px-3 py-2 disabled:bg-surface disabled:text-muted"
            value={editor.template_id || ""}
            onChange={(e) => onApplyTemplate(Number(e.target.value))}
          >
            <option value="">选择模板</option>
            {templates.map((t) => (
              <option key={t.id} value={t.id}>{t.name}</option>
            ))}
          </select>
          <input
            disabled={!canWriteSelectedProject}
            className="rounded-md border border-border px-3 py-2 disabled:bg-surface disabled:text-muted"
            placeholder="实验类型"
            value={editor.experiment_type}
            onChange={(e) => onEditorChange({ ...editor, experiment_type: e.target.value })}
            required
          />
          <input
            disabled={!canWriteSelectedProject}
            className="rounded-md border border-border px-3 py-2 disabled:bg-surface disabled:text-muted"
            type="date"
            value={editor.experiment_date}
            onChange={(e) => onEditorChange({ ...editor, experiment_date: e.target.value })}
          />
        </div>
        {selectedTemplate && (
          <div className="mt-4 grid gap-3 md:grid-cols-2">
            {(selectedTemplate.schema_json.fields || []).map((field) => (
              <label key={field.key} className="text-sm font-medium">
                {field.label}
                <textarea
                  disabled={!canWriteSelectedProject}
                  className="mt-2 min-h-20 w-full rounded-md border border-border px-3 py-2 disabled:bg-surface disabled:text-muted"
                  value={editor.fixed_fields_json[field.key] || ""}
                  onChange={(e) =>
                    onEditorChange({
                      ...editor,
                      fixed_fields_json: { ...editor.fixed_fields_json, [field.key]: e.target.value },
                    })
                  }
                />
              </label>
            ))}
          </div>
        )}
        <label className="mt-4 block text-sm font-medium">
          自由正文
          <textarea
            disabled={!canWriteSelectedProject}
            className="mt-2 min-h-44 w-full rounded-md border border-border px-3 py-2 disabled:bg-surface disabled:text-muted"
            value={editor.content_text}
            onChange={(e) => onEditorChange({ ...editor, content_text: e.target.value })}
            placeholder="记录实验过程、观察、结果分析和下一步计划"
          />
        </label>
        <div className="mt-4 flex flex-wrap gap-2">
          {canWriteSelectedProject && (
            <button className="rounded-md bg-brand px-4 py-2 text-sm font-medium text-white">保存笔记</button>
          )}
          {selectedNote && canSubmitSelectedNote && (
            <button type="button" onClick={onSubmitNote} className="rounded-md border border-border px-4 py-2 text-sm">
              提交审批
            </button>
          )}
          {selectedNote && canWriteSelectedProject && ["approved", "returned", "draft"].includes(selectedNote.status) && (
            <button type="button" onClick={onArchiveNote} className="rounded-md border border-border px-4 py-2 text-sm">
              归档
            </button>
          )}
          {selectedNote && canReviewSelectedProject && selectedNote.status !== "voided" && (
            <button type="button" onClick={onVoidNote} className="rounded-md border border-red-200 px-4 py-2 text-sm text-red-700">
              作废
            </button>
          )}
        </div>
      </form>

      <div className={cardClass("p-5")}>
        <h2 className="font-semibold">实验笔记列表</h2>
        <div className="mt-4 grid gap-2 md:grid-cols-3">
          <input
            className="rounded-md border border-border px-3 py-2 text-sm"
            placeholder="搜索标题/类型"
            value={noteFilters.keyword}
            onChange={(e) => onNoteFiltersChange({ ...noteFilters, keyword: e.target.value })}
          />
          <select
            className="rounded-md border border-border px-3 py-2 text-sm"
            value={noteFilters.status}
            onChange={(e) => onNoteFiltersChange({ ...noteFilters, status: e.target.value })}
          >
            <option value="">全部状态</option>
            {Object.entries(statusText).map(([value, label]) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </select>
          <select
            className="rounded-md border border-border px-3 py-2 text-sm"
            value={noteFilters.experiment_type}
            onChange={(e) => onNoteFiltersChange({ ...noteFilters, experiment_type: e.target.value })}
          >
            <option value="">全部类型</option>
            {experimentTypes.map((type) => (
              <option key={type} value={type}>{type}</option>
            ))}
          </select>
        </div>
        <div className="mt-4 max-h-[520px] space-y-2 overflow-auto">
          {filteredNotes.length === 0 && <p className="text-sm text-muted">暂无匹配实验笔记。</p>}
          {filteredNotes.map((note) => (
            <button
              key={note.id}
              onClick={() => onEditNote(note)}
              className={`w-full rounded-md border px-3 py-3 text-left text-sm ${
                selectedNote?.id === note.id ? "border-brand bg-[#eef8f6]" : "border-border hover:bg-surface"
              }`}
            >
              <span className="font-medium">{note.title}</span>
              <span className="mt-1 block text-xs text-muted">
                {note.experiment_type} · {statusText[note.status] || note.status}
              </span>
            </button>
          ))}
        </div>
        {versions.length > 0 && (
          <div className="mt-5 border-t border-border pt-4">
            <h3 className="text-sm font-semibold">版本历史</h3>
            <div className="mt-2 space-y-2 text-sm text-muted">
              {versions.map((v) => (
                <div key={v.id} className="rounded-md border border-border px-3 py-2">
                  v{v.version_number} · {v.is_locked ? "已锁定" : "未锁定"} · {new Date(v.created_at).toLocaleString("zh-CN")}
                </div>
              ))}
            </div>
          </div>
        )}
        {approvals.length > 0 && (
          <div className="mt-5 border-t border-border pt-4">
            <h3 className="text-sm font-semibold">审批记录</h3>
            <div className="mt-2 space-y-2 text-sm text-muted">
              {approvals.map((a) => (
                <div key={a.id} className="rounded-md border border-border px-3 py-2">
                  {a.action} · 审核人 {a.reviewer_user_id} · {new Date(a.created_at).toLocaleString("zh-CN")}
                  {a.comment && <p className="mt-1 text-foreground">{a.comment}</p>}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
