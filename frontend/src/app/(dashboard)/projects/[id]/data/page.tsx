"use client";

import { useState, useRef, useEffect } from "react";
import { useParams } from "next/navigation";
import { Upload, CheckCircle, XCircle, Eye, Database, Archive, Send } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useAuthStore, useProjectStore } from "@/stores";
import type { OcrJobResult, StoredFile } from "@/lib/api";
import { getErrorMessage } from "@/lib/utils";
import { knowledgeSyncText } from "@/components/constants";

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
  const files = useProjectStore((s) => s.files);
  const uploadFile = useProjectStore((s) => s.uploadFile);
  const reviewFile = useProjectStore((s) => s.reviewFile);
  const busy = useProjectStore((s) => s.busy);
  const loadTabProjectData = useProjectStore((s) => s.loadTabProjectData);
  const fileInput = useRef<HTMLInputElement>(null);
  const ocrRequestEpoch = useRef(0);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [category, setCategory] = useState("note_attachment");
  const [uploading, setUploading] = useState(false);

  useEffect(() => {
    if (token) loadTabProjectData(token, projectId);
  }, [token, projectId, loadTabProjectData]);

  // OCR dialog
  const [ocrFile, setOcrFile] = useState<(typeof files)[0] | null>(null);
  const [ocrResult, setOcrResult] = useState<OcrJobResult | null>(null);
  const [ocrDraft, setOcrDraft] = useState("");
  const [ocrBusy, setOcrBusy] = useState(false);

  const handleUpload = async () => {
    const file = fileInput.current?.files?.[0];
    if (!token || !file) return;
    setUploading(true);
    setError("");
    setMessage("");
    try {
      await uploadFile(token, projectId, file, category);
      setMessage(`文件 ${file.name} 上传成功`);
      if (fileInput.current) fileInput.current.value = "";
    } catch (e) {
      setError(getErrorMessage(e, "上传失败"));
    } finally {
      setUploading(false);
    }
  };

  const handleReview = async (fileId: number, action: "approve" | "reject") => {
    if (!token) return;
    setError("");
    setMessage("");
    try {
      await reviewFile(token, fileId, action, "");
      setMessage(action === "approve" ? "资料审核已通过" : "资料审核已拒绝");
    } catch (e) { setError(getErrorMessage(e, "审核失败")); }
  };

  const handleSyncRag = async (fileId: number) => {
    if (!token) return;
    setError("");
    setMessage("");
    try {
      await useProjectStore.getState().syncFileToRag(token, fileId);
      setMessage("资料已同步到 AI 知识库");
    }
    catch (e) { setError(getErrorMessage(e, "同步失败")); }
  };

  const handleArchive = async (fileId: number) => {
    if (!token) return;
    try { await useProjectStore.getState().archiveFile(token, fileId); }
    catch (e) { setError(getErrorMessage(e, "归档失败")); }
  };

  const openOcr = async (f: (typeof files)[0]) => {
    if (!token) return;
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
    setMessage("");
    try {
      const { confirmOcrResult } = await import("@/lib/api");
      await confirmOcrResult(token, ocrResult.ocr_result_id, ocrDraft);
      if (requestEpoch !== ocrRequestEpoch.current) return;
      setOcrFile(null);
      setMessage("文本校对已确认，图片资料现可进入 RAG 入库流程");
      const refreshed = await (await import("@/lib/api")).getProjectFiles(token, projectId);
      if (
        requestEpoch === ocrRequestEpoch.current
        && useProjectStore.getState().selectedProjectId === projectId
      ) {
        useProjectStore.setState({ files: refreshed });
      }
    } catch (e) {
      if (requestEpoch === ocrRequestEpoch.current) {
        setError(getErrorMessage(e, "确认失败"));
      }
    } finally {
      if (requestEpoch === ocrRequestEpoch.current) setOcrBusy(false);
    }
  };

  if (busy) return <p className="text-sm text-muted-foreground py-8 text-center">加载中...</p>;

  return (
    <div className="space-y-4">
      {error && <p className="rounded-md bg-destructive/10 px-4 py-2 text-sm text-destructive">{error}</p>}
      {message && <p className="rounded-md bg-green-50 px-4 py-2 text-sm text-green-700">{message}</p>}

      {/* Upload */}
      <Card>
        <CardContent className="flex items-center gap-3 py-4">
          <Select value={category} onValueChange={setCategory}>
            <SelectTrigger aria-label="文件类别" className="w-36"><SelectValue /></SelectTrigger>
            <SelectContent>
              {categories.map((c) => (<SelectItem key={c} value={c}>{categoryText[c] || c}</SelectItem>))}
            </SelectContent>
          </Select>
          <Input ref={fileInput} aria-label="选择上传文件" type="file" className="flex-1" />
          <Button onClick={handleUpload} disabled={uploading}>
            <Upload className="mr-2 h-4 w-4" />{uploading ? "上传中..." : "上传"}
          </Button>
        </CardContent>
      </Card>

      {files.length === 0 ? (
        <Card className="border-dashed"><CardContent className="py-12 text-center"><p className="text-sm text-muted-foreground">暂无文件</p></CardContent></Card>
      ) : (
        <div className="space-y-2">
          {files.map((f) => (
            <Card key={f.id} data-testid={`file-row-${f.id}`}>
              <CardContent className="flex items-center justify-between py-3">
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium truncate">{f.original_filename}</p>
                  <p className="text-xs text-muted-foreground">{categoryText[f.file_category] || f.file_category} · {(f.file_size / 1024).toFixed(0)} KB</p>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <Badge variant="secondary">{knowledgeSyncText[f.knowledge_sync_status] || f.knowledge_sync_status}</Badge>
                  {isImageFile(f) && (
                    <Button aria-label={`提取文本 ${f.original_filename}`} variant="outline" size="sm" onClick={() => openOcr(f)}>
                      <Eye className="mr-1 h-3 w-3" />OCR
                    </Button>
                  )}
                  {f.status === "uploaded" && f.file_category === "knowledge_document" && (
                    <>
                      <Button aria-label={`通过 ${f.original_filename}`} size="sm" className="bg-green-600 h-8 w-8 p-0" onClick={() => handleReview(f.id, "approve")}>
                        <CheckCircle className="h-4 w-4" />
                      </Button>
                      <Button aria-label={`拒绝 ${f.original_filename}`} size="sm" variant="destructive" className="h-8 w-8 p-0" onClick={() => handleReview(f.id, "reject")}>
                        <XCircle className="h-4 w-4" />
                      </Button>
                    </>
                  )}
                  {f.status === "approved" && f.knowledge_sync_status === "pending_sync" && (
                    <Button size="sm" variant="outline" onClick={() => handleSyncRag(f.id)}>
                      <Database className="mr-1 h-3 w-3" />本地向量入库
                    </Button>
                  )}
                  <Button aria-label={`归档 ${f.original_filename}`} size="sm" variant="ghost" onClick={() => handleArchive(f.id)}>
                    <Archive className="h-4 w-4" />
                  </Button>
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
                <p className="text-sm text-muted-foreground">加载 OCR 结果...</p>
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
                      readOnly={ocrResult?.review_status === "confirmed"}
                    />
                  </div>
                  {ocrResult?.review_status === "confirmed" ? (
                    <p className="rounded-md bg-green-50 px-3 py-2 text-center text-sm text-green-700">该结果已确认签名</p>
                  ) : (
                    <Button className="w-full" onClick={confirmOcr} disabled={!ocrResult || !ocrDraft.trim()}>
                      <Send className="mr-2 h-4 w-4" />确认校对并签名
                    </Button>
                  )}
                </>
              )}
            </div>
          </DialogContent>
        )}
      </Dialog>
    </div>
  );
}
