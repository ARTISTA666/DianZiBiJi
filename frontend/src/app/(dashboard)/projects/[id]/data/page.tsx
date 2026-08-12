"use client";

import { useState, useRef, useEffect } from "react";
import { useParams } from "next/navigation";
import { Upload, CheckCircle, XCircle, Eye, Database, Archive } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { ErrorBanner } from "@/components/shared/error-banner";
import { EmptyState } from "@/components/shared/empty-state";
import { useAuthStore, useProjectStore } from "@/stores";
import type { OcrJobResult, StoredFile } from "@/lib/api";
import { getErrorMessage, formatFileSize } from "@/lib/utils";
import { knowledgeSyncText } from "@/components/constants";
import { useActionFeedback } from "@/hooks/use-action-feedback";
import { useConfirmDialog } from "@/hooks/use-confirm-dialog";
import { FilesListSkeleton } from "@/components/skeletons";
import { UploadSection, categoryText } from "./upload-section";
import { OcrDialog } from "./ocr-dialog";
import { RejectDialog } from "./reject-dialog";

const isImageFile = (file: StoredFile) =>
  file.mime_type?.startsWith("image/")
  || /\.(?:bmp|gif|jpe?g|png|tiff?|webp)$/i.test(file.original_filename);

const fileStatusText: Record<string, string> = {
  uploaded: "待审核",
  approved: "已审核",
  rejected: "已拒绝",
  archived: "已归档",
};

export default function DataPage() {
  const { id } = useParams();
  const projectId = Number(id);
  const token = useAuthStore((s) => s.token);
  const user = useAuthStore((s) => s.user);
  const files = useProjectStore((s) => s.files);
  const notes = useProjectStore((s) => s.notes);
  const members = useProjectStore((s) => s.members);
  const selectedProject = useProjectStore((s) => s.selectedProject);
  const reviewFile = useProjectStore((s) => s.reviewFile);
  const busy = useProjectStore((s) => s.busy);
  const loadDataTabData = useProjectStore((s) => s.loadDataTabData);
  const ocrRequestEpoch = useRef(0);
  const [error, setError] = useState("");
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

  const handleUploaded = async (names: string[]) => {
    if (!token) return;
    setError("");
    feedback.success(`文件 ${names.join("、")} 上传成功`);
    // Refresh file list
    useProjectStore.getState().invalidateCache();
    await loadDataTabData(token, projectId);
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
      {error && <ErrorBanner message={error} />}

      {/* Upload */}
      {canWrite && (
        <UploadSection
          projectId={projectId}
          token={token}
          onStart={() => setError("")}
          onUploaded={handleUploaded}
          onError={(msg) => {
            setError(msg);
            feedback.error(msg);
          }}
          notes={notes}
        />
      )}

      {files.length === 0 ? (
        <EmptyState
          icon={Upload}
          title="还没有资料文件"
          description="上传实验相关的文档、图片等资料"
          action={canWrite ? (
            <Button onClick={() => document.querySelector<HTMLInputElement>('input[type="file"]')?.click()}>
              <Upload className="mr-2 h-4 w-4" />上传文件
            </Button>
          ) : undefined}
        />
      ) : (
        <div className="space-y-2">
          {files.map((f) => (
            <Card id={`file-${f.id}`} key={f.id} data-testid={`file-row-${f.id}`}>
              <CardContent className="flex items-center justify-between py-3">
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium truncate">{f.original_filename}</p>
                  <p className="text-xs text-muted-foreground">{categoryText[f.file_category] || f.file_category} · {formatFileSize(f.file_size)}</p>
                  {f.note_id !== null && (
                    <p className="text-xs text-muted-foreground truncate">
                      关联笔记：{notes.find((note) => note.id === f.note_id)?.title || `#${f.note_id}`}
                    </p>
                  )}
                  {(f.status === "rejected" || f.knowledge_sync_status === "failed") && f.knowledge_sync_message && (
                    <p className="mt-0.5 text-xs text-destructive truncate" title={f.knowledge_sync_message}>
                      {f.knowledge_sync_message}
                    </p>
                  )}
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  {f.file_category === "knowledge_document" && (
                    <Badge variant={f.status === "approved" ? "success" : f.status === "rejected" ? "destructive" : "secondary"}>
                      {fileStatusText[f.status] || f.status}
                    </Badge>
                  )}
                  <Badge variant="secondary">{knowledgeSyncText[f.knowledge_sync_status] || f.knowledge_sync_status}</Badge>
                  {canWrite && f.status !== "archived" && isImageFile(f) && (
                    <Button aria-label={`提取文本 ${f.original_filename}`} variant="outline" size="sm" onClick={() => openOcr(f)}>
                      <Eye className="mr-1 h-3 w-3" />OCR
                    </Button>
                  )}
                  {canReview && f.status === "uploaded" && f.file_category === "knowledge_document" && (
                    <>
                      <Button aria-label={`通过 ${f.original_filename}`} size="sm" variant="success" className="h-8 w-8 p-0" onClick={() => handleReview(f.id, "approve")}>
                        <CheckCircle className="h-4 w-4" />
                      </Button>
                      <Button aria-label={`拒绝 ${f.original_filename}`} size="sm" variant="destructive" className="h-8 w-8 p-0" onClick={() => { setRejectTarget(f); setRejectComment(""); }}>
                        <XCircle className="h-4 w-4" />
                      </Button>
                    </>
                  )}
                  {canManage && f.status === "approved"
                    && ["pending_sync", "failed"].includes(f.knowledge_sync_status) && (
                    <Button size="sm" variant="outline" onClick={() => handleSyncRag(f.id)}>
                      <Database className="mr-1 h-3 w-3" />
                      {f.knowledge_sync_status === "failed" ? "重试向量入库" : "本地向量入库"}
                    </Button>
                  )}
                  {f.status === "archived" ? (
                    <Badge variant="secondary">已归档</Badge>
                  ) : canWrite && (
                    <Button aria-label={`归档 ${f.original_filename}`} size="sm" variant="ghost" onClick={() => handleArchiveConfirm(f.id, f.original_filename)}>
                      <Archive className="h-4 w-4" />
                    </Button>
                  )}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* OCR Dialog */}
      <OcrDialog
        file={ocrFile}
        result={ocrResult}
        draft={ocrDraft}
        busy={ocrBusy}
        canReview={canReview}
        onDraftChange={setOcrDraft}
        onConfirm={confirmOcr}
        onOpenChange={(open) => {
          if (!open) {
            ocrRequestEpoch.current += 1;
            setOcrFile(null);
            setOcrResult(null);
            setOcrBusy(false);
          }
        }}
      />
      {/* 拒绝审核意见 Dialog */}
      <RejectDialog
        file={rejectTarget}
        comment={rejectComment}
        busy={rejectBusy}
        onCommentChange={setRejectComment}
        onConfirm={confirmReject}
        onClose={closeRejectDialog}
      />
      {ConfirmDialog}
    </div>
  );
}
