"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { useParams } from "next/navigation";
import { Upload, CheckCircle, XCircle, Eye, Database, Archive, Send } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Dropzone } from "@/components/dropzone";
import { useAuthStore, useProjectStore } from "@/stores";
import type { OcrJobResult, StoredFile } from "@/lib/api";
import { getErrorMessage, formatFileSize } from "@/lib/utils";
import { knowledgeSyncText } from "@/components/constants";
import { useActionFeedback } from "@/hooks/use-action-feedback";
import { useConfirmDialog } from "@/hooks/use-confirm-dialog";
import { FilesListSkeleton } from "@/components/skeletons";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8001";
const SUPPORTED_UPLOAD_ACCEPT = [
  ".pdf", ".jpg", ".jpeg", ".png", ".gif", ".webp", ".tif", ".tiff", ".bmp", ".txt",
  ".doc", ".docx", ".xls", ".xlsx", ".pptx",
].join(",");

function uploadFileWithProgress(
  file: File,
  projectId: number,
  category: string,
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
    xhr.open("POST", `${API_BASE_URL}/projects/${projectId}/files?${params.toString()}`);
    xhr.withCredentials = true;
    xhr.send(formData);
  });
}

const categories = ["note_attachment", "knowledge_document"];
const categoryText: Record<string, string> = {
  note_attachment: "笔记附件", knowledge_document: "知识文档",
};

const isImageFile = (file: StoredFile) =>
  file.mime_type?.startsWith("image/")
  || /\.(?:bmp|gif|jpe?g|png|tiff?|webp)$/i.test(file.original_filename);

export default function DataPage() {
  const { id } = useParams();
  const projectId = Number(id);
  const token = useAuthStore((s) => s.token);
  const user = useAuthStore((s) => s.user);
  const files = useProjectStore((s) => s.files);
  const members = useProjectStore((s) => s.members);
  const selectedProject = useProjectStore((s) => s.selectedProject);
  const reviewFile = useProjectStore((s) => s.reviewFile);
  const busy = useProjectStore((s) => s.busy);
  const loadDataTabData = useProjectStore((s) => s.loadDataTabData);
  const ocrRequestEpoch = useRef(0);
  const [error, setError] = useState("");
  const [category, setCategory] = useState("note_attachment");
  const [uploading, setUploading] = useState(false);
  const feedback = useActionFeedback();
  const { confirm, ConfirmDialog } = useConfirmDialog();
  const membership = members.find((member) => member.user_id === user?.id);
  const canWrite = user?.role === "super_admin" || membership?.can_write === true;
  const canReview = user?.role === "super_admin"
    || membership?.can_review === true
    || membership?.can_manage === true;
  const canManage = user?.role === "super_admin"
    || selectedProject?.owner_user_id === user?.id
    || membership?.can_manage === true
    || membership?.project_role === "owner";

  useEffect(() => {
    if (token) loadDataTabData(token, projectId);
  }, [token, projectId, loadDataTabData]);

  // OCR dialog
  const [ocrFile, setOcrFile] = useState<(typeof files)[0] | null>(null);
  const [ocrResult, setOcrResult] = useState<OcrJobResult | null>(null);
  const [ocrDraft, setOcrDraft] = useState("");
  const [ocrBusy, setOcrBusy] = useState(false);

  // 拒绝审核意见收集 dialog
  const [rejectTarget, setRejectTarget] = useState<StoredFile | null>(null);
  const [rejectComment, setRejectComment] = useState("");
  const [rejectBusy, setRejectBusy] = useState(false);

  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);

  const handleFilesSelected = useCallback((files: File[]) => {
    setSelectedFiles((prev) => [...prev, ...files]);
  }, []);

  const handleUpload = async () => {
    if (!token || selectedFiles.length === 0) return;
    setUploading(true);
    setError("");
    setUploadProgress(0);
    try {
      const names: string[] = [];
      for (let i = 0; i < selectedFiles.length; i++) {
        const file = selectedFiles[i];
        await uploadFileWithProgress(file, projectId, category, (pct) => {
          // Overall progress across all files
          const overall = Math.round(((i + pct / 100) / selectedFiles.length) * 100);
          setUploadProgress(overall);
        });
        names.push(file.name);
      }
      setUploadProgress(100);
      feedback.success(`文件 ${names.join("、")} 上传成功`);
      setSelectedFiles([]);
      // Refresh file list
      useProjectStore.getState().invalidateCache();
      await loadDataTabData(token, projectId);
    } catch (e) {
      const msg = getErrorMessage(e, "上传失败");
      setError(msg);
      feedback.error(msg);
    } finally {
      setUploading(false);
      setUploadProgress(null);
    }
  };

  const handleReview = async (fileId: number, action: "approve" | "reject", comment = "") => {
    if (!token) return;
    setError("");
    try {
      await reviewFile(token, fileId, action, comment);
      feedback.success(action === "approve" ? "资料审核已通过" : "资料审核已拒绝");
      // 刷新文件列表，及时反映审核状态与同步提示信息。
      useProjectStore.getState().invalidateCache();
      await loadDataTabData(token, projectId);
    } catch (e) {
      const msg = getErrorMessage(e, "审核失败");
      setError(msg);
      feedback.error(msg);
    }
  };

  const closeRejectDialog = () => {
    setRejectTarget(null);
    setRejectComment("");
  };

  const confirmReject = async () => {
    if (!rejectTarget) return;
    setRejectBusy(true);
    try {
      await handleReview(rejectTarget.id, "reject", rejectComment.trim());
      closeRejectDialog();
    } finally {
      setRejectBusy(false);
    }
  };

  const handleSyncRag = async (fileId: number) => {
    if (!token) return;
    setError("");
    try {
      await useProjectStore.getState().syncFileToRag(token, fileId);
      feedback.success("资料已同步到 AI 知识库");
    }
    catch (e) {
      const msg = getErrorMessage(e, "同步失败");
      setError(msg);
      feedback.error(msg);
    }
  };

  const handleArchive = async (fileId: number) => {
    if (!token) return;
    try {
      await useProjectStore.getState().archiveFile(token, fileId);
      feedback.success("文件已归档");
    }
    catch (e) {
      const msg = getErrorMessage(e, "归档失败");
      setError(msg);
      feedback.error(msg);
    }
  };

  const handleArchiveConfirm = (fileId: number, fileName: string) => {
    confirm("确认归档", `确定要归档文件「${fileName}」吗？归档后仍可恢复。`, () => {
      handleArchive(fileId);
    });
  };

  const openOcr = async (f: (typeof files)[0]) => {
    if (!canWrite || !token) return;
    const requestEpoch = ++ocrRequestEpoch.current;
    setOcrFile(f);
    setOcrDraft("");
    setOcrResult(null);
    setOcrBusy(true);
    setError("");
    try {
      const { ApiRequestError, extractOcr, getLatestOcrResult } = await import("@/lib/api");
      let result: OcrJobResult;
      try {
        result = await getLatestOcrResult(token, f.id);
      } catch (error) {
        if (!(error instanceof ApiRequestError) || error.status !== 404) throw error;
        result = await extractOcr(token, f.id);
      }
      if (requestEpoch !== ocrRequestEpoch.current) return;
      if (result.file_id !== f.id) throw new Error("OCR 结果与当前文件不匹配");
      setOcrResult(result);
      setOcrDraft(result.extracted_text || result.raw_text || "");
    } catch (e) {
      if (requestEpoch === ocrRequestEpoch.current) {
        setError(getErrorMessage(e, "OCR 结果加载失败"));
        setOcrFile(null);
      }
    } finally {
      if (requestEpoch === ocrRequestEpoch.current) setOcrBusy(false);
    }
  };

  const confirmOcr = async () => {
    if (!token || !ocrFile || !ocrResult || ocrResult.file_id !== ocrFile.id) return;
    const requestEpoch = ++ocrRequestEpoch.current;
    setOcrBusy(true);
    setError("");
    try {
      const { confirmOcrResult } = await import("@/lib/api");
      await confirmOcrResult(token, ocrResult.ocr_result_id, ocrDraft);
      if (requestEpoch !== ocrRequestEpoch.current) return;
      setOcrFile(null);
      feedback.success("文本校对已确认，图片资料现可进入 RAG 入库流程");
      const refreshed = await (await import("@/lib/api")).getProjectFiles(token, projectId);
      if (
        requestEpoch === ocrRequestEpoch.current
        && useProjectStore.getState().selectedProjectId === projectId
      ) {
        useProjectStore.setState({ files: refreshed.items });
      }
    } catch (e) {
      if (requestEpoch === ocrRequestEpoch.current) {
        setError(getErrorMessage(e, "确认失败"));
      }
    } finally {
      if (requestEpoch === ocrRequestEpoch.current) setOcrBusy(false);
    }
  };

  if (busy) return <FilesListSkeleton />;

  return (
    <div className="space-y-4">
      {error && <p className="rounded-md bg-destructive/10 px-4 py-2 text-sm text-destructive">{error}</p>}

      {/* Upload */}
      {canWrite && <Card>
        <CardContent className="flex items-start gap-3 py-4">
          <Select value={category} onValueChange={setCategory}>
            <SelectTrigger aria-label="文件类别" className="w-36 mt-2"><SelectValue /></SelectTrigger>
            <SelectContent>
              {categories.map((c) => (<SelectItem key={c} value={c}>{categoryText[c] || c}</SelectItem>))}
            </SelectContent>
          </Select>
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
          <Button onClick={handleUpload} disabled={uploading || selectedFiles.length === 0} className="mt-2">
            <Upload className="mr-2 h-4 w-4" />{uploading ? "上传中..." : "上传"}
          </Button>
        </CardContent>
      </Card>}

      {files.length === 0 ? (
        <Card className="border-dashed">
          <CardContent className="flex flex-col items-center justify-center py-12 text-center">
            <Upload className="h-12 w-12 text-muted-foreground/50 mb-4" />
            <p className="text-lg font-medium text-muted-foreground">还没有资料文件</p>
            <p className="text-sm text-muted-foreground/70 mt-1">上传实验相关的文档、图片等资料</p>
            {canWrite && <Button className="mt-4" onClick={() => document.querySelector<HTMLInputElement>('input[type="file"]')?.click()}>
              <Upload className="mr-2 h-4 w-4" />上传文件
            </Button>}
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-2">
          {files.map((f) => (
            <Card key={f.id} data-testid={`file-row-${f.id}`}>
              <CardContent className="flex items-center justify-between py-3">
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium truncate">{f.original_filename}</p>
                  <p className="text-xs text-muted-foreground">{categoryText[f.file_category] || f.file_category} · {formatFileSize(f.file_size)}</p>
                  {(f.status === "rejected" || f.knowledge_sync_status === "failed") && f.knowledge_sync_message && (
                    <p className="mt-0.5 text-xs text-red-600 truncate" title={f.knowledge_sync_message}>
                      {f.knowledge_sync_message}
                    </p>
                  )}
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <Badge variant="secondary">{knowledgeSyncText[f.knowledge_sync_status] || f.knowledge_sync_status}</Badge>
                  {canWrite && isImageFile(f) && (
                    <Button aria-label={`提取文本 ${f.original_filename}`} variant="outline" size="sm" onClick={() => openOcr(f)}>
                      <Eye className="mr-1 h-3 w-3" />OCR
                    </Button>
                  )}
                  {canReview && f.status === "uploaded" && f.file_category === "knowledge_document" && (
                    <>
                      <Button aria-label={`通过 ${f.original_filename}`} size="sm" className="bg-green-600 h-8 w-8 p-0" onClick={() => handleReview(f.id, "approve")}>
                        <CheckCircle className="h-4 w-4" />
                      </Button>
                      <Button aria-label={`拒绝 ${f.original_filename}`} size="sm" variant="destructive" className="h-8 w-8 p-0" onClick={() => { setRejectTarget(f); setRejectComment(""); }}>
                        <XCircle className="h-4 w-4" />
                      </Button>
                    </>
                  )}
                  {canManage && f.status === "approved" && f.knowledge_sync_status === "pending_sync" && (
                    <Button size="sm" variant="outline" onClick={() => handleSyncRag(f.id)}>
                      <Database className="mr-1 h-3 w-3" />本地向量入库
                    </Button>
                  )}
                  {canWrite && <Button aria-label={`归档 ${f.original_filename}`} size="sm" variant="ghost" onClick={() => handleArchiveConfirm(f.id, f.original_filename)}>
                    <Archive className="h-4 w-4" />
                  </Button>}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* OCR Dialog */}
      <Dialog
        open={!!ocrFile}
        onOpenChange={(open) => {
          if (!open) {
            ocrRequestEpoch.current += 1;
            setOcrFile(null);
            setOcrResult(null);
            setOcrBusy(false);
          }
        }}
      >
        {ocrFile && (
          <DialogContent className="max-w-lg">
            <DialogHeader><DialogTitle>OCR — {ocrFile.original_filename}</DialogTitle></DialogHeader>
            <div className="space-y-4">
              {ocrBusy ? (
                <div className="space-y-1">
                  <p className="text-sm text-muted-foreground">加载 OCR 结果...</p>
                  <p className="text-xs text-muted-foreground">图片文本识别通常需要数十秒，请勿关闭窗口</p>
                </div>
              ) : (
                <>
                  <div className="space-y-2">
                    <p className="text-sm font-medium">识别文本</p>
                    <div className="rounded-md border bg-muted/30 p-3 text-sm whitespace-pre-wrap max-h-40 overflow-y-auto">{ocrResult?.raw_text}</div>
                  </div>
                  <div className="space-y-2">
                    <p className="text-sm font-medium">校对文本</p>
                    <Textarea
                      aria-label="OCR 校对文本"
                      rows={6}
                      value={ocrDraft}
                      onChange={(e) => setOcrDraft(e.target.value)}
                      readOnly={ocrResult?.review_status === "confirmed" || !canReview}
                    />
                  </div>
                  {ocrResult?.review_status === "confirmed" ? (
                    <p className="rounded-md bg-green-50 px-3 py-2 text-center text-sm text-green-700">该结果已确认签名</p>
                  ) : canReview ? (
                    <Button className="w-full" onClick={confirmOcr} disabled={!ocrResult || !ocrDraft.trim()}>
                      <Send className="mr-2 h-4 w-4" />确认校对并签名
                    </Button>
                  ) : (
                    <p className="text-sm text-muted-foreground">仅具审核权限的成员可以确认校对文本。</p>
                  )}
                </>
              )}
            </div>
          </DialogContent>
        )}
      </Dialog>
      {/* 拒绝审核意见 Dialog */}
      <Dialog
        open={!!rejectTarget}
        onOpenChange={(open) => { if (!open) closeRejectDialog(); }}
      >
        {rejectTarget && (
          <DialogContent className="max-w-md">
            <DialogHeader><DialogTitle>拒绝资料 — {rejectTarget.original_filename}</DialogTitle></DialogHeader>
            <div className="space-y-3">
              <p className="text-sm text-muted-foreground">请填写拒绝原因，便于上传者快速定位问题并修正。</p>
              <Textarea
                aria-label="审核意见"
                placeholder="审核意见"
                value={rejectComment}
                onChange={(e) => setRejectComment(e.target.value)}
                rows={3}
                autoFocus
              />
              <div className="flex justify-end gap-2">
                <Button variant="outline" onClick={closeRejectDialog} disabled={rejectBusy}>取消</Button>
                <Button variant="destructive" onClick={confirmReject} disabled={rejectBusy}>
                  {rejectBusy ? "提交中..." : "确认拒绝"}
                </Button>
              </div>
            </div>
          </DialogContent>
        )}
      </Dialog>
      {ConfirmDialog}
    </div>
  );
}
