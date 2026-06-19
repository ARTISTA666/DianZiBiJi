"use client";

import { FormEvent } from "react";
import { Sparkles, Upload } from "lucide-react";
import type {
  StoredFile,
  RagStatus,
  RagQueryResponse,
  AIQueryLog,
  AIQueryAnalytics,
  AIExperimentRun,
  Note,
} from "@/lib/api";
import { cardClass, formatRate, formatScore, ragModeLabel } from "../shared/utils";
import { knowledgeSyncText, agentTaskOptions } from "../constants";

interface FilesPanelProps {
  // RAG state
  ragStatus: RagStatus | null;
  ragQuestion: string;
  onRagQuestionChange: (v: string) => void;
  ragMode: string;
  onRagModeChange: (v: string) => void;
  ragAnswer: RagQueryResponse | null;
  ragBusy: boolean;
  // Analytics
  queryLogs: AIQueryLog[];
  queryAnalytics: AIQueryAnalytics | null;
  // Experiments
  experimentRuns: AIExperimentRun[];
  experimentDraft: { name: string; questions: string };
  onExperimentDraftChange: (draft: { name: string; questions: string }) => void;
  experimentBusy: boolean;
  // Evaluations
  evaluationDrafts: Record<number, { score: string; is_accurate: boolean | null; is_traceable: boolean | null; comment: string }>;
  onEvaluationDraftChange: (logId: number, draft: { score: string; is_accurate: boolean | null; is_traceable: boolean | null; comment: string }) => void;
  // Files
  files: StoredFile[];
  filteredFiles: StoredFile[];
  fileFilters: { keyword: string; category: string; status: string };
  onFileFiltersChange: (filters: { keyword: string; category: string; status: string }) => void;
  fileEdits: Record<number, string>;
  onFileEditChange: (fileId: number, name: string) => void;
  fileReviewComment: string;
  onFileReviewCommentChange: (v: string) => void;
  ocrResult: string | null;
  // Context
  selectedNote: Note | null;
  selectedProjectId: number | null;
  canReviewSelectedProject: boolean;
  canWriteSelectedProject: boolean;
  // Handlers
  onInitRag: () => void;
  onSyncRagFile: (file: StoredFile) => void;
  onQueryRag: (e: FormEvent<HTMLFormElement>) => void;
  onEvaluateQueryLog: (log: AIQueryLog) => void;
  onRunRagExperiment: (e: FormEvent<HTMLFormElement>) => void;
  onDownloadRagExperiment: (run: AIExperimentRun) => void;
  onUpload: (e: FormEvent<HTMLFormElement>) => void;
  onDownload: (file: StoredFile) => void;
  onUpdateFile: (file: StoredFile) => void;
  onArchiveFile: (file: StoredFile) => void;
  onOcrExtract: (file: StoredFile) => void;
  onReviewFile: (fileId: number, action: "approve" | "reject", comment: string) => void;
  onRefreshQueryLogs: () => void;
}

export function FilesPanel({
  ragStatus,
  ragQuestion,
  onRagQuestionChange,
  ragMode,
  onRagModeChange,
  ragAnswer,
  ragBusy,
  queryLogs,
  queryAnalytics,
  experimentRuns,
  experimentDraft,
  onExperimentDraftChange,
  experimentBusy,
  evaluationDrafts,
  onEvaluationDraftChange,
  files: _files,
  filteredFiles,
  fileFilters,
  onFileFiltersChange,
  fileEdits,
  onFileEditChange,
  fileReviewComment,
  onFileReviewCommentChange,
  ocrResult: _ocrResult,
  selectedNote,
  selectedProjectId,
  canReviewSelectedProject,
  canWriteSelectedProject,
  onInitRag,
  onSyncRagFile,
  onQueryRag,
  onEvaluateQueryLog,
  onRunRagExperiment,
  onDownloadRagExperiment,
  onUpload,
  onDownload,
  onUpdateFile,
  onArchiveFile,
  onOcrExtract,
  onReviewFile,
  onRefreshQueryLogs,
}: FilesPanelProps) {
  if (!selectedProjectId) return null;

  return (
    <div className="grid gap-6">
      {/* ── RAG Knowledge Base ── */}
      <div className={cardClass("p-5")}>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="flex items-center gap-2 font-semibold"><Sparkles size={18} />AI 知识库</h2>
            <p className="mt-1 text-sm text-muted">只使用当前项目中审核通过并同步的资料回答问题。</p>
          </div>
          {canReviewSelectedProject && (
            <button
              type="button"
              disabled={ragBusy || ragStatus?.initialized}
              onClick={onInitRag}
              className="rounded-md border border-border px-3 py-2 text-sm disabled:cursor-not-allowed disabled:opacity-60"
            >
              {ragStatus?.initialized ? "已初始化" : "初始化知识库"}
            </button>
          )}
        </div>
        <div className="mt-4 grid gap-3 text-sm md:grid-cols-4">
          <div className="rounded-md border border-border px-3 py-2">
            <p className="text-xs text-muted">状态</p>
            <p className="mt-1 font-medium">{ragStatus?.initialized ? "已初始化" : "未初始化"}</p>
          </div>
          <div className="rounded-md border border-border px-3 py-2">
            <p className="text-xs text-muted">待同步</p>
            <p className="mt-1 font-medium">{ragStatus?.pending_sync_count ?? 0}</p>
          </div>
          <div className="rounded-md border border-border px-3 py-2">
            <p className="text-xs text-muted">已入库</p>
            <p className="mt-1 font-medium">{ragStatus?.synced_count ?? 0}</p>
          </div>
          <div className="rounded-md border border-border px-3 py-2">
            <p className="text-xs text-muted">失败</p>
            <p className="mt-1 font-medium">{ragStatus?.failed_sync_count ?? 0}</p>
          </div>
        </div>
        {ragStatus?.dataset && (
          <div className="mt-3 flex flex-wrap gap-2 text-xs text-muted">
            <span className="rounded-md border border-border px-2 py-1">生成模型：{ragStatus.dataset.generation_model}</span>
            <span className="rounded-md border border-border px-2 py-1">嵌入模型：{ragStatus.dataset.embedding_model}</span>
            <span className="rounded-md border border-border px-2 py-1">运行方式：本地向量检索 + DeepSeek</span>
          </div>
        )}

        {/* Analytics */}
        {queryAnalytics && (
          <div className="mt-4 rounded-md border border-border bg-surface px-3 py-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <h3 className="text-sm font-semibold">AI 成效概览</h3>
                <p className="mt-1 text-xs text-muted">用于论文第 7 章的问答质量统计与模式对比。</p>
              </div>
              <span className="rounded-md border border-border bg-white px-2 py-1 text-xs text-muted">
                评价覆盖率 {formatRate(queryAnalytics.evaluation_rate)}
              </span>
            </div>
            <div className="mt-3 grid gap-2 text-sm md:grid-cols-6">
              <div className="rounded-md border border-border bg-white px-3 py-2">
                <p className="text-xs text-muted">问答次数</p>
                <p className="mt-1 font-medium">{queryAnalytics.total_queries}</p>
              </div>
              <div className="rounded-md border border-border bg-white px-3 py-2">
                <p className="text-xs text-muted">平均评分</p>
                <p className="mt-1 font-medium">{formatScore(queryAnalytics.avg_score)}</p>
              </div>
              <div className="rounded-md border border-border bg-white px-3 py-2">
                <p className="text-xs text-muted">准确率</p>
                <p className="mt-1 font-medium">{formatRate(queryAnalytics.accurate_rate)}</p>
              </div>
              <div className="rounded-md border border-border bg-white px-3 py-2">
                <p className="text-xs text-muted">可追溯率</p>
                <p className="mt-1 font-medium">{formatRate(queryAnalytics.traceable_rate)}</p>
              </div>
              <div className="rounded-md border border-border bg-white px-3 py-2">
                <p className="text-xs text-muted">平均图谱命中</p>
                <p className="mt-1 font-medium">{queryAnalytics.avg_graph_hit_count.toFixed(1)}</p>
              </div>
              <div className="rounded-md border border-border bg-white px-3 py-2">
                <p className="text-xs text-muted">平均响应</p>
                <p className="mt-1 font-medium">{Math.round(queryAnalytics.avg_response_ms)} ms</p>
              </div>
            </div>
            <div className="mt-3 grid gap-2 md:grid-cols-2">
              {queryAnalytics.mode_stats.map((stat) => (
                <div key={stat.rag_mode} className="rounded-md border border-border bg-white px-3 py-2 text-xs">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-medium text-foreground">{ragModeLabel(stat.rag_mode)}</span>
                    <span className="text-muted">{stat.total_queries} 次 / 已评 {stat.evaluated_queries}</span>
                  </div>
                  <div className="mt-2 grid grid-cols-4 gap-2 text-muted">
                    <span>评分 {formatScore(stat.avg_score)}</span>
                    <span>准确 {formatRate(stat.accurate_rate)}</span>
                    <span>追溯 {formatRate(stat.traceable_rate)}</span>
                    <span>图谱 {stat.avg_graph_hit_count.toFixed(1)}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Experiment Section */}
        {canReviewSelectedProject && (
          <div className="mt-4 rounded-md border border-border bg-surface px-3 py-3">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div>
                <h3 className="text-sm font-semibold">论文对照实验</h3>
                <p className="mt-1 text-xs text-muted">对同一题集分别运行普通 RAG 与知识图谱增强 RAG，并保存配置快照和 CSV。</p>
              </div>
              <span className="rounded-md border border-border bg-white px-2 py-1 text-xs text-muted">
                已运行 {experimentRuns.length} 次
              </span>
            </div>
            <form onSubmit={onRunRagExperiment} className="mt-3 grid gap-2">
              <input
                className="rounded-md border border-border px-3 py-2 text-sm"
                value={experimentDraft.name}
                onChange={(e) => onExperimentDraftChange({ ...experimentDraft, name: e.target.value })}
                placeholder="实验名称"
              />
              <textarea
                className="min-h-24 rounded-md border border-border px-3 py-2 text-sm"
                value={experimentDraft.questions}
                onChange={(e) => onExperimentDraftChange({ ...experimentDraft, questions: e.target.value })}
                placeholder="每行一个问题"
              />
              <button
                disabled={experimentBusy || !ragStatus?.initialized}
                className="justify-self-start rounded-md bg-accent px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-60"
              >
                {experimentBusy ? "正在运行，请勿关闭页面" : "运行成对对照实验"}
              </button>
            </form>
            <div className="mt-3 grid gap-2">
              {experimentRuns.slice(0, 5).map((run) => (
                <div key={run.id} className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-border bg-white px-3 py-2 text-xs">
                  <div>
                    <p className="font-medium text-foreground">#{run.id} {run.name}</p>
                    <p className="mt-1 text-muted">
                      {run.completed_cases}/{run.total_cases} 成功 · {run.failed_cases} 失败 · {new Date(run.created_at).toLocaleString()}
                    </p>
                  </div>
                  <button type="button" onClick={() => onDownloadRagExperiment(run)} className="rounded-md border border-border px-3 py-1">
                    导出 CSV
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Query Form */}
        <form onSubmit={onQueryRag} className="mt-4 grid gap-2 md:grid-cols-[180px_1fr_auto]">
          <select
            className="rounded-md border border-border px-3 py-2 text-sm"
            value={ragMode}
            onChange={(e) => onRagModeChange(e.target.value)}
          >
            <option value="auto">自动选择</option>
            <option value="project_rag">普通 RAG</option>
            <option value="kg_enhanced_rag">图谱增强 RAG</option>
          </select>
          <input
            className="min-w-0 rounded-md border border-border px-3 py-2 text-sm"
            placeholder="向当前项目资料提问"
            value={ragQuestion}
            onChange={(e) => onRagQuestionChange(e.target.value)}
          />
          <button
            disabled={ragBusy || !ragStatus?.initialized}
            className="rounded-md bg-brand px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-60"
          >
            提问
          </button>
        </form>
        {!ragStatus?.initialized && <p className="mt-3 text-xs text-muted">请先由审核人或管理员初始化该项目知识库。</p>}

        {/* Answer */}
        {ragAnswer && (
          <div className="mt-4 rounded-md border border-border bg-surface px-3 py-3 text-sm">
            <div className="mb-3 flex flex-wrap items-center gap-2 text-xs">
              <span className="rounded-md border border-border bg-white px-2 py-1 text-muted">
                回答模式：{ragAnswer.rag_mode === "kg_enhanced_rag" ? "知识图谱增强 RAG" : "项目级 RAG"}
              </span>
              <span className="rounded-md border border-border bg-white px-2 py-1 text-muted">
                图谱依据：{ragAnswer.graph_context.length} 条
              </span>
              <span className="rounded-md border border-border bg-white px-2 py-1 text-muted">
                响应耗时：{ragAnswer.response_ms ?? 0} ms
              </span>
              <span className="rounded-md border border-border bg-white px-2 py-1 text-muted">
                模型：{ragAnswer.provider}/{ragAnswer.model_name || "未知"}
              </span>
              {ragAnswer.query_log_id && (
                <span className="rounded-md border border-border bg-white px-2 py-1 text-muted">
                  记录编号：{ragAnswer.query_log_id}
                </span>
              )}
            </div>
            {ragAnswer.fallback_reason && (
              <p className="mb-3 rounded-md border border-amber-200 bg-amber-50 px-2 py-2 text-xs text-amber-800">
                降级说明：{ragAnswer.fallback_reason}
              </p>
            )}
            <p className="whitespace-pre-wrap">{ragAnswer.answer || "AI 没有返回回答。"}</p>
            {ragAnswer.graph_context.length > 0 && (
              <div className="mt-3 border-t border-border pt-3 text-xs text-muted">
                <p className="font-medium text-foreground">图谱依据</p>
                <div className="mt-2 grid gap-2 md:grid-cols-2">
                  {ragAnswer.graph_context.map((item) => (
                    <div key={item.relation_id} className="rounded-md border border-border bg-white px-2 py-2">
                      <p className="font-medium text-foreground">
                        {item.source_label} → {item.target_label}
                      </p>
                      <p className="mt-1">
                        {item.source_entity_type_label} --{item.relation_label}--&gt; {item.target_entity_type_label}
                        {" · "}置信度 {item.confidence.toFixed(2)}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            )}
            {ragAnswer.sources.length > 0 && (
              <div className="mt-3 border-t border-border pt-3 text-xs text-muted">
                <p className="font-medium text-foreground">来源</p>
                {ragAnswer.sources.map((source, index) => (
                  <p key={`${source.dify_document_id || source.file_id || index}-${index}`} className="mt-1">
                    {source.filename || source.dify_document_id || "未知资料"}
                    {source.snippet ? `：${source.snippet.slice(0, 120)}` : ""}
                    {source.retrieval_score != null ? `（综合相关度 ${source.retrieval_score.toFixed(3)}）` : ""}
                  </p>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Query Log Evaluation */}
        <div className="mt-4 border-t border-border pt-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="font-semibold">问答记录与评价</h3>
            <button
              type="button"
              disabled={ragBusy || !selectedProjectId}
              onClick={onRefreshQueryLogs}
              className="rounded-md border border-border px-3 py-1 text-xs disabled:cursor-not-allowed disabled:opacity-60"
            >
              刷新记录
            </button>
          </div>
          <div className="mt-3 max-h-96 space-y-3 overflow-auto">
            {queryLogs.length === 0 && <p className="text-sm text-muted">暂无问答记录。</p>}
            {queryLogs.slice(0, 8).map((log) => {
              const draft = evaluationDrafts[log.id] || {
                score: log.evaluation ? String(log.evaluation.score) : "",
                is_accurate: log.evaluation?.is_accurate ?? null,
                is_traceable: log.evaluation?.is_traceable ?? null,
                comment: log.evaluation?.comment || "",
              };
              return (
                <div key={log.id} className="rounded-md border border-border bg-white px-3 py-3 text-sm">
                  <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
                    <span>{new Date(log.created_at).toLocaleString()}</span>
                    <span>{log.rag_mode === "kg_enhanced_rag" ? "知识图谱增强 RAG" : "项目级 RAG"}</span>
                    <span>{log.provider}/{log.model_name || "未知模型"}</span>
                    <span>图谱 {log.graph_hit_count} 条</span>
                    <span>来源 {log.source_count} 个</span>
                    {log.experiment_run_id && <span>实验 #{log.experiment_run_id} / 题 {log.experiment_case_index}</span>}
                    <span>{log.response_ms} ms</span>
                    {log.evaluation && <span className="text-brand">已评价 {log.evaluation.score}/5</span>}
                  </div>
                  <p className="mt-2 font-medium">{log.question}</p>
                  <p className="mt-1 line-clamp-2 text-xs text-muted">{log.error_message || log.answer || "无回答内容"}</p>
                  <div className="mt-3 grid gap-2 md:grid-cols-[90px_1fr_100px_110px_auto]">
                    <select
                      className="rounded-md border border-border px-2 py-1 text-xs"
                      value={draft.score}
                      onChange={(e) =>
                        onEvaluationDraftChange(log.id, { ...draft, score: e.target.value })
                      }
                    >
                      <option value="">评分</option>
                      {[5, 4, 3, 2, 1].map((s) => (
                        <option key={s} value={s}>{s} 分</option>
                      ))}
                    </select>
                    <input
                      className="rounded-md border border-border px-2 py-1 text-xs"
                      placeholder="评价备注"
                      value={draft.comment}
                      onChange={(e) =>
                        onEvaluationDraftChange(log.id, { ...draft, comment: e.target.value })
                      }
                    />
                    <select
                      aria-label="准确性"
                      className="rounded-md border border-border px-2 py-1 text-xs"
                      value={draft.is_accurate === null ? "" : String(draft.is_accurate)}
                      onChange={(e) =>
                        onEvaluationDraftChange(log.id, {
                          ...draft,
                          is_accurate: e.target.value === "" ? null : e.target.value === "true",
                        })
                      }
                    >
                      <option value="">准确性</option>
                      <option value="true">准确</option>
                      <option value="false">不准确</option>
                    </select>
                    <select
                      aria-label="可追溯性"
                      className="rounded-md border border-border px-2 py-1 text-xs"
                      value={draft.is_traceable === null ? "" : String(draft.is_traceable)}
                      onChange={(e) =>
                        onEvaluationDraftChange(log.id, {
                          ...draft,
                          is_traceable: e.target.value === "" ? null : e.target.value === "true",
                        })
                      }
                    >
                      <option value="">可追溯性</option>
                      <option value="true">可追溯</option>
                      <option value="false">不可追溯</option>
                    </select>
                    <button
                      type="button"
                      disabled={ragBusy || !draft.score || draft.is_accurate === null || draft.is_traceable === null}
                      onClick={() => onEvaluateQueryLog(log)}
                      className="rounded-md border border-brand px-3 py-1 text-xs text-brand disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      保存评价
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* ── File Management ── */}
      <div className={cardClass("p-5")}>
        <h2 className="flex items-center gap-2 font-semibold"><Upload size={18} />附件与资料</h2>
        {canWriteSelectedProject ? (
          <form onSubmit={onUpload} className="mt-4 flex flex-wrap gap-2">
            <input name="file" type="file" className="rounded-md border border-border px-3 py-2 text-sm" />
            <button className="rounded-md bg-brand px-4 py-2 text-sm font-medium text-white">上传</button>
            <span className="self-center text-xs text-muted">
              {selectedNote ? "上传为当前笔记附件" : "未选笔记时上传为项目资料"}
            </span>
          </form>
        ) : (
          <p className="mt-4 rounded-md border border-border bg-surface px-3 py-2 text-sm text-muted">当前账号仅可查看和下载文件。</p>
        )}
        {canReviewSelectedProject && (
          <textarea
            className="mt-3 w-full rounded-md border border-border px-3 py-2 text-sm"
            placeholder="资料审核意见"
            value={fileReviewComment}
            onChange={(e) => onFileReviewCommentChange(e.target.value)}
          />
        )}
        <div className="mt-3 grid gap-2 md:grid-cols-3">
          <input
            className="rounded-md border border-border px-3 py-2 text-sm"
            placeholder="搜索文件名/哈希"
            value={fileFilters.keyword}
            onChange={(e) => onFileFiltersChange({ ...fileFilters, keyword: e.target.value })}
          />
          <select
            className="rounded-md border border-border px-3 py-2 text-sm"
            value={fileFilters.category}
            onChange={(e) => onFileFiltersChange({ ...fileFilters, category: e.target.value })}
          >
            <option value="">全部类型</option>
            <option value="note_attachment">笔记附件</option>
            <option value="knowledge_document">资料库</option>
          </select>
          <select
            className="rounded-md border border-border px-3 py-2 text-sm"
            value={fileFilters.status}
            onChange={(e) => onFileFiltersChange({ ...fileFilters, status: e.target.value })}
          >
            <option value="">全部状态</option>
            <option value="uploaded">uploaded</option>
            <option value="approved">approved</option>
            <option value="rejected">rejected</option>
            <option value="archived">archived</option>
          </select>
        </div>
        <div className="mt-4 max-h-80 space-y-2 overflow-auto">
          {filteredFiles.length === 0 && <p className="text-sm text-muted">暂无匹配文件。</p>}
          {filteredFiles.map((file) => (
            <div key={file.id} className="flex items-center justify-between gap-3 rounded-md border border-border px-3 py-2 text-sm">
              <div className="min-w-0">
                <input
                  disabled={!canWriteSelectedProject}
                  className="w-full rounded-md border border-border px-2 py-1 text-sm font-medium disabled:bg-surface disabled:text-muted"
                  value={fileEdits[file.id] ?? file.original_filename}
                  onChange={(e) => onFileEditChange(file.id, e.target.value)}
                />
                <p className="text-xs text-muted">{file.file_category} · {file.status} · {(file.file_size / 1024).toFixed(1)} KB</p>
                {file.file_category === "knowledge_document" && (
                  <p className="mt-1 text-xs text-muted">
                    知识库：{knowledgeSyncText[file.knowledge_sync_status] || file.knowledge_sync_status}
                    {file.knowledge_sync_message ? ` · ${file.knowledge_sync_message}` : ""}
                  </p>
                )}
              </div>
              <div className="flex shrink-0 flex-wrap gap-2">
                {canReviewSelectedProject && file.file_category === "knowledge_document" && file.status === "uploaded" && (
                  <>
                    <button type="button" onClick={() => onReviewFile(file.id, "approve", fileReviewComment)} className="rounded-md border border-green-200 px-3 py-1 text-xs text-green-700">通过</button>
                    <button type="button" onClick={() => onReviewFile(file.id, "reject", fileReviewComment)} className="rounded-md border border-red-200 px-3 py-1 text-xs text-red-700">拒绝</button>
                  </>
                )}
                {canReviewSelectedProject && file.file_category === "knowledge_document" && file.status === "approved" && file.knowledge_sync_status !== "synced" && ragStatus?.initialized && (
                  <button type="button" disabled={ragBusy} onClick={() => onSyncRagFile(file)} className="rounded-md border border-brand px-3 py-1 text-xs text-brand disabled:cursor-not-allowed disabled:opacity-60">本地向量入库</button>
                )}
                {canWriteSelectedProject && <button type="button" onClick={() => onUpdateFile(file)} className="rounded-md border border-border px-3 py-1 text-xs">保存</button>}
                {canWriteSelectedProject && file.status !== "archived" && (
                  <button type="button" onClick={() => onArchiveFile(file)} className="rounded-md border border-border px-3 py-1 text-xs">归档</button>
                )}
                <button type="button" onClick={() => onDownload(file)} className="rounded-md border border-border px-3 py-1 text-xs">下载</button>
                <button type="button" onClick={() => onOcrExtract(file)} className="rounded-md border border-border px-3 py-1 text-xs">OCR</button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
