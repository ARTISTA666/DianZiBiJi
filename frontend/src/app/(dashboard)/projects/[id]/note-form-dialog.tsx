"use client";

import { useState, FormEvent } from "react";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { Template } from "@/lib/api";

export interface NoteFormData {
  title: string;
  experiment_type: string;
  template_id: number | null;
  experiment_date: string;
  fixed_fields_json: Record<string, string>;
  content_text: string;
}

interface NoteFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  editingNote: number | null;
  templates: Template[];
  form: NoteFormData;
  onFormChange: (form: NoteFormData) => void;
  onSave: (e: FormEvent) => void;
  busy: boolean;
  error: string;
}

export function NoteFormDialog({
  open,
  onOpenChange,
  editingNote,
  form,
  onFormChange,
  onSave,
  busy,
  error,
  templates,
}: NoteFormDialogProps) {
  const [titleError, setTitleError] = useState("");
  const selectedTemplate = templates.find((template) => template.id === form.template_id);
  const templateFields = selectedTemplate?.schema_json.fields ?? [];

  const handleTemplateChange = (value: string) => {
    if (value === "__none_template__") {
      onFormChange({
        ...form,
        template_id: null,
        fixed_fields_json: {},
      });
      return;
    }
    const template = templates.find((item) => item.id === Number(value));
    if (!template) return;
    const fields = Object.fromEntries(
      (template.schema_json.fields ?? []).map((field) => [
        field.key,
        form.fixed_fields_json[field.key] ?? "",
      ]),
    );
    onFormChange({
      ...form,
      template_id: template.id,
      experiment_type: template.experiment_type,
      fixed_fields_json: fields,
    });
  };

  const handleTitleBlur = () => {
    if (!form.title.trim()) {
      setTitleError("笔记标题不能为空");
    } else {
      setTitleError("");
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{editingNote ? "编辑笔记" : "新建笔记"}</DialogTitle>
        </DialogHeader>
        <form onSubmit={onSave} className="space-y-4 pt-2">
          <div className="space-y-2">
            <Label htmlFor="ntitle">标题</Label>
            <Input
              id="ntitle"
              required
              value={form.title}
              onChange={(e) =>
                onFormChange({ ...form, title: e.target.value })
              }
              onBlur={handleTitleBlur}
              className={titleError ? "border-destructive" : ""}
            />
            {titleError && (
              <p className="text-sm text-destructive">{titleError}</p>
            )}
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label>实验模板</Label>
              <Select
                value={form.template_id ? String(form.template_id) : "__none_template__"}
                onValueChange={handleTemplateChange}
              >
                <SelectTrigger aria-label="实验模板">
                  <SelectValue placeholder="选择结构化模板" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none_template__">不使用模板（兼容旧笔记）</SelectItem>
                  {templates.map((template) => (
                    <SelectItem key={template.id} value={String(template.id)}>
                      {template.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="ndate">实验日期</Label>
              <Input
                id="ndate"
                type="date"
                value={form.experiment_date}
                onChange={(e) =>
                  onFormChange({ ...form, experiment_date: e.target.value })
                }
              />
            </div>
          </div>
          {templateFields.map((field) => (
            <div key={field.key} className="space-y-2">
              <Label htmlFor={`nfield-${field.key}`}>
                {field.label}{field.required ? " *" : ""}
              </Label>
              <Textarea
                id={`nfield-${field.key}`}
                rows={3}
                required={field.required === true}
                value={form.fixed_fields_json[field.key] ?? ""}
                onChange={(e) =>
                  onFormChange({
                    ...form,
                    fixed_fields_json: {
                      ...form.fixed_fields_json,
                      [field.key]: e.target.value,
                    },
                  })
                }
              />
            </div>
          ))}
          <div className="space-y-2">
            <Label htmlFor="ncontent">内容</Label>
            <Textarea
              id="ncontent"
              rows={8}
              value={form.content_text}
              onChange={(e) =>
                onFormChange({ ...form, content_text: e.target.value })
              }
              placeholder="实验笔记内容..."
            />
          </div>
          {error && <p className="text-sm text-destructive">{error}</p>}
          <p className="text-xs text-muted-foreground">编辑中的内容会自动保存在本机，刷新或暂时断网后可恢复。</p>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              取消
            </Button>
            <Button
              type="submit"
              disabled={busy || !form.title.trim() || !form.experiment_type.trim()}
              isLoading={busy}
            >
              {busy ? "保存中..." : "保存"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
