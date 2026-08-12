"use client";

import { useState, useCallback } from "react";
import { Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dropzone } from "@/components/dropzone";
import type { Note, StoredFile } from "@/lib/api";
import { getErrorMessage } from "@/lib/utils";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8001";
const SUPPORTED_UPLOAD_ACCEPT = [
  ".pdf", ".jpg", ".jpeg", ".png", ".gif", ".webp", ".tif", ".tiff", ".bmp", ".txt",
  ".doc", ".docx", ".xls", ".xlsx", ".pptx",
].join(",");

function uploadFileWithProgress(
  file: File,
  projectId: number,
  category: string,
  noteId: number | null,
  onProgress: (pct: number) => void,
): Promise<StoredFile> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) {
        onProgress(Math.round((e.loaded / e.total) * 100));
      }
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText) as StoredFile);
        } catch {
          reject(new Error("Invalid response"));
        }
      } else {
        let detail = "";
        try {
          const payload = JSON.parse(xhr.responseText) as { detail?: unknown };
          if (typeof payload.detail === "string") detail = payload.detail;
        } catch {
          // Keep the status fallback when the server returns a non-JSON error.
        }
        reject(new Error(detail || `上传失败: ${xhr.status}`));
      }
    };
    xhr.onerror = () => reject(new Error("上传失败"));

    const formData = new FormData();
    formData.append("upload", file);
    const params = new URLSearchParams({ file_category: category });
    if (noteId !== null) params.set("note_id", String(noteId));
    xhr.open("POST", `${API_BASE_URL}/projects/${projectId}/files?${params.toString()}`);
    xhr.withCredentials = true;
    xhr.send(formData);
  });
}

const categories = ["note_attachment", "knowledge_document"];
export const categoryText: Record<string, string> = {
  note_attachment: "笔记附件", knowledge_document: "知识文档",
};

interface UploadSectionProps {
  projectId: number;
  token: string | null;
  /** 上传开始时回调，父组件用于清除旧错误提示 */
  onStart: () => void;
  /** 上传成功后回传文件名列表，由父组件统一提示并刷新列表 */
  onUploaded: (names: string[]) => void;
  /** 上传失败回传错误文案，由父组件统一展示 */
  onError: (message: string) => void;
  notes: Note[];
}

export function UploadSection({ projectId, token, onStart, onUploaded, onError, notes }: UploadSectionProps) {
  const [category, setCategory] = useState("note_attachment");
  const [noteId, setNoteId] = useState("");
  const [uploading, setUploading] = useState(false);
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);

  const handleFilesSelected = useCallback((files: File[]) => {
    setSelectedFiles((prev) => [...prev, ...files]);
  }, []);

  const handleUpload = async () => {
    const authToken = token;
    if (!authToken || selectedFiles.length === 0) return;
    setUploading(true);
    onStart();
    setUploadProgress(0);
    try {
      const names: string[] = [];
      for (let i = 0; i < selectedFiles.length; i++) {
        const file = selectedFiles[i];
        await uploadFileWithProgress(file, projectId, category, noteId ? Number(noteId) : null, (pct) => {
          // Overall progress across all files
          const overall = Math.round(((i + pct / 100) / selectedFiles.length) * 100);
          setUploadProgress(overall);
        });
        names.push(file.name);
      }
      setUploadProgress(100);
      setSelectedFiles([]);
      onUploaded(names);
    } catch (e) {
      onError(getErrorMessage(e, "上传失败"));
    } finally {
      setUploading(false);
      setUploadProgress(null);
    }
  };

  return (
    <Card>
      <CardContent className="flex items-start gap-3 py-4">
        <Select value={category} onValueChange={setCategory}>
          <SelectTrigger aria-label="文件类别" className="w-36 mt-2"><SelectValue /></SelectTrigger>
          <SelectContent>
            {categories.map((c) => (<SelectItem key={c} value={c}>{categoryText[c] || c}</SelectItem>))}
          </SelectContent>
        </Select>
        {category === "note_attachment" && (
          <Select value={noteId} onValueChange={setNoteId}>
            <SelectTrigger aria-label="关联笔记" className="w-52 mt-2"><SelectValue placeholder="选择关联笔记" /></SelectTrigger>
            <SelectContent>
              {notes.map((note) => (
                <SelectItem key={note.id} value={String(note.id)}>{note.title}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
        <div className="flex-1 space-y-2">
          <Dropzone
            onFilesSelected={handleFilesSelected}
            accept={SUPPORTED_UPLOAD_ACCEPT}
            multiple
            maxSize={50 * 1024 * 1024}
          />
          {selectedFiles.length > 0 && (
            <div className="text-xs text-muted-foreground">
              已选择 {selectedFiles.length} 个文件：{selectedFiles.map((f) => f.name).join("、")}
            </div>
          )}
          {uploadProgress !== null && (
            <div>
              <div className="w-full bg-secondary rounded-full h-2">
                <div
                  className="bg-primary h-2 rounded-full transition-all"
                  style={{ width: `${uploadProgress}%` }}
                />
              </div>
              <p className="text-xs text-muted-foreground mt-1">{uploadProgress}%</p>
            </div>
          )}
        </div>
        <Button onClick={handleUpload} disabled={uploading || selectedFiles.length === 0 || (category === "note_attachment" && !noteId)} isLoading={uploading} className="mt-2">
          <Upload className="mr-2 h-4 w-4" />{uploading ? "上传中..." : "上传"}
        </Button>
      </CardContent>
    </Card>
  );
}
