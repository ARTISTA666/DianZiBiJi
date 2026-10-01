"use client";

import { useState, useRef, ChangeEvent, FormEvent } from "react";
import { ImagePlus, X, Upload } from "lucide-react";
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
  pendingImages?: File[];
  onPendingImagesChange?: (files: File[]) => void;
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
  pendingImages = [],
  onPendingImagesChange,
}: NoteFormDialogProps) {
  const [titleError, setTitleError] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);
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

  const handleFileChange = (e: ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files || !onPendingImagesChange) return;
    const newFiles = Array.from(e.target.files).filter((file) =>
      file.type.startsWith("image/")
    );
    if (newFiles.length > 0) {
      onPendingImagesChange([...pendingImages, ...newFiles]);
    }
    e.target.value = "";
  };

  const removePendingImage = (index: number) => {
    if (!onPendingImagesChange) return;
    onPendingImagesChange(pendingImages.filter((_, i) => i !== index));
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto">
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
              rows={6}
              value={form.content_text}
              onChange={(e) =>
                onFormChange({ ...form, content_text: e.target.value })
              }
              placeholder="实验笔记内容..."
            />
          </div>

          {/* 日记图片上传与管理 */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label className="flex items-center gap-1.5 text-sm font-medium">
                <ImagePlus className="h-4 w-4 text-primary" />
                日记图片
                {pendingImages.length > 0 && (
                  <span className="text-xs text-muted-foreground font-normal">
                    （已选 {pendingImages.length} 张，保存后可左右切换查看）
                  </span>
                )}
              </Label>
              <input
                ref={fileInputRef}
                type="file"
                multiple
                accept="image/*"
                className="hidden"
                onChange={handleFileChange}
              />
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="h-8 text-xs gap-1.5"
                onClick={() => fileInputRef.current?.click()}
              >
                <Upload className="h-3.5 w-3.5" />
                添加图片
              </Button>
            </div>

            {/* 待上传图片预览列表 */}
            {pendingImages.length > 0 ? (
              <div className="grid grid-cols-3 sm:grid-cols-4 gap-2 p-2 rounded-lg border border-dashed border-border/80 bg-muted/20">
                {pendingImages.map((file, idx) => {
                  const previewUrl = URL.createObjectURL(file);
                  return (
                    <div
                      key={`${file.name}-${idx}`}
                      className="group relative aspect-square overflow-hidden rounded-md border border-border/60 bg-muted"
                    >
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img
                        src={previewUrl}
                        alt={file.name}
                        className="h-full w-full object-cover"
                        onLoad={() => URL.revokeObjectURL(previewUrl)}
                      />
                      <button
                        type="button"
                        aria-label={`移除图片 ${file.name}`}
                        className="absolute top-1 right-1 flex h-5 w-5 items-center justify-center rounded-full bg-black/75 text-white hover:bg-destructive transition-colors"
                        onClick={() => removePendingImage(idx)}
                      >
                        <X className="h-3 w-3" />
                      </button>
                      <div className="absolute bottom-0 inset-x-0 bg-black/60 px-1 py-0.5 text-[9px] text-white truncate text-center">
                        {file.name}
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div
                role="button"
                tabIndex={0}
                className="flex flex-col items-center justify-center gap-1 p-3 rounded-lg border border-dashed border-border/80 bg-muted/10 hover:bg-muted/20 cursor-pointer transition-colors text-center"
                onClick={() => fileInputRef.current?.click()}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    fileInputRef.current?.click();
                  }
                }}
              >
                <ImagePlus className="h-5 w-5 text-muted-foreground/70" />
                <p className="text-xs text-muted-foreground">
                  点击或添加日记附图（支持多张图片）
                </p>
              </div>
            )}
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
