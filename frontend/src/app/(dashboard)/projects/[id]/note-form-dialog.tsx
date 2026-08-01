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

const experimentTypes = [
  "PCR",
  "qPCR",
  "WB",
  "ELISA",
  "测序",
  "细胞培养",
  "动物实验",
  "其他",
];

export interface NoteFormData {
  title: string;
  experiment_type: string;
  experiment_date: string;
  content_text: string;
}

interface NoteFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  editingNote: number | null;
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
}: NoteFormDialogProps) {
  const [titleError, setTitleError] = useState("");

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
              <Label>实验类型</Label>
              <Select
                value={form.experiment_type}
                onValueChange={(v) =>
                  onFormChange({ ...form, experiment_type: v })
                }
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {experimentTypes.map((t) => (
                    <SelectItem key={t} value={t}>
                      {t}
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
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              取消
            </Button>
            <Button type="submit" disabled={busy || !form.title.trim()}>
              {busy ? "保存中..." : "保存"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
