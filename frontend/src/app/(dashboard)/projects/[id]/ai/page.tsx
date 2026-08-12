"use client";

import { useState, useEffect, useRef, useCallback, useMemo } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { Database, Send, Sparkles, Download, HelpCircle, MessageSquarePlus, Loader2, ThumbsDown, ThumbsUp } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tooltip as UITooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useAuthStore, useProjectStore } from "@/stores";
import { getErrorMessage } from "@/lib/utils";
import { useActionFeedback } from "@/hooks/use-action-feedback";
import { ErrorBanner } from "@/components/shared/error-banner";
import { CitationRichText, RagAnswerBlock, ragModeText, type RagSource, type RagGraphContextItem } from "@/lib/citations";
import { submitQueryLogFeedback } from "@/lib/api";

const modes = [
  { value: "auto", label: "自动选择", desc: "系统根据问题类型自动选择最佳检索策略" },
  { value: "project_rag", label: "项目级 RAG", desc: "基于项目资料库的向量+BM25 混合检索，适合查找实验资料中的具体内容" },
  { value: "kg_enhanced_rag", label: "图谱增强 RAG", desc: "在 RAG 基础上叠加知识图谱关系，适合回答关系型问题（如试剂→仪器→结果）" },
  { value: "structured_query", label: "结构化查询", desc: "只依据知识图谱关系回答，适合精确核对关系和结构化指标" },
  { value: "pure_llm", label: "纯 LLM", desc: "不检索资料库，直接由大模型回答，适合通用知识问题" },
  { value: "bm25_rag", label: "BM25 RAG", desc: "仅使用关键词匹配检索，适合术语精确查找（如特定基因名、试剂名）" },
] as const;

/** 根据回答中的来源和图谱上下文，生成 2-3 个追问建议。 */
function suggestFollowUps(
  lastQuestion: string,
  sources: RagSource[],
  graphContext: RagGraphContextItem[],
): string[] {
  const suggestions: string[] = [];
  // 基于来源文件名建议深入
  if (sources.length > 0) {
    const fname = sources[0].filename;
    if (fname) suggestions.push(`关于 ${fname} 还有哪些细节？`);
  }
  // 基于图谱上下文建议关联查询
  if (graphContext.length > 0) {
    const rel = graphContext[0];
    suggestions.push(`与 ${rel.source_label} 和 ${rel.target_label} 有什么关联？`);
  }
  // 通用建议
  suggestions.push("请总结以上问题的关键要点");
  return suggestions.slice(0, 3);
}

/** 将当前对话导出为 Markdown。 */
function exportConversation(
  conversation: { question: string; result: { answer: string; rag_mode: string; response_ms: number | null; sources: RagSource[] } }[],
  projectName: string,
) {
  const lines: string[] = [`# ${projectName} — AI 问答记录`, ``, `导出时间：${new Date().toLocaleString("zh-CN")}`, ``];
  conversation.forEach((entry, i) => {
    lines.push(`## 问题 ${i + 1}`);
    lines.push(``);
    lines.push(entry.question);
    lines.push(``);
    lines.push(`### 回答（${ragModeText[entry.result.rag_mode] || entry.result.rag_mode}，${entry.result.response_ms ?? "—"} ms）`);
    lines.push(``);
    lines.push(entry.result.answer);
    lines.push(``);
    if (entry.result.sources.length > 0) {
      lines.push(`**来源：**`);
      entry.result.sources.forEach((s, j) => {
        lines.push(`- [S${j + 1}] ${s.filename || "未知文件"}（相关度 ${s.retrieval_score?.toFixed(3) ?? "—"}）`);
      });
      lines.push(``);
    }
    lines.push(`---`);
    lines.push(``);
  });
  const blob = new Blob([lines.join("\n")], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${projectName}-AI问答-${new Date().toISOString().slice(0, 10)}.md`;
  a.click();
  URL.revokeObjectURL(url);
}

export default function AIPage() {
  const { id } = useParams();
  const projectId = Number(id);
  const token = useAuthStore((s) => s.token);
  const user = useAuthStore((s) => s.user);
  const ragConversation = useProjectStore((s) => s.ragConversation);
  const ragConversationProjectId = useProjectStore((s) => s.ragConversationProjectId);
  const clearRagConversation = useProjectStore((s) => s.clearRagConversation);
  const ragStatus = useProjectStore((s) => s.ragStatus);
  const queryLogs = useProjectStore((s) => s.queryLogs);
  const selectedProject = useProjectStore((s) => s.selectedProject);
  const members = useProjectStore((s) => s.members);
  const initRag = useProjectStore((s) => s.initRag);
  const queryRag = useProjectStore((s) => s.queryRag);
  const loadAITabData = useProjectStore((s) => s.loadAITabData);
  const [question, setQuestion] = useState("");
  const [mode, setMode] = useState("auto");
  const [busy, setBusy] = useState(false);
  const [initBusy, setInitBusy] = useState(false);
  const [error, setError] = useState("");
  const [answerFeedback, setAnswerFeedback] = useState<Record<number, "helpful" | "not_helpful">>({});
  const [feedbackBusy, setFeedbackBusy] = useState<number | null>(null);
  const feedback = useActionFeedback();
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const membership = members.find((member) => member.user_id === user?.id);
  const canManage = user?.role === "super_admin"
    || selectedProject?.owner_user_id === user?.id
    || membership?.can_manage === true
    || membership?.project_role === "owner";
  const ragReady = ragStatus?.initialized === true;
  const pureLlmMode = mode === "pure_llm";
  const datasetIndependentMode = pureLlmMode || mode === "structured_query";
  const modeAvailable = datasetIndependentMode || ragReady;
  const ragSyncSummary = ragStatus && ragStatus.initialized
    ? `已初始化 · ${ragStatus.synced_count} 个文件已入库${ragStatus.pending_sync_count > 0 ? ` · 待入库 ${ragStatus.pending_sync_count}` : ""}${ragStatus.failed_sync_count > 0 ? ` · 失败 ${ragStatus.failed_sync_count}` : ""}`
    : null;

  // 最后一轮回答的追问建议
  const followUpSuggestions = useMemo(() => {
    if (ragConversation.length === 0) return [];
    const last = ragConversation[ragConversation.length - 1];
    return suggestFollowUps(last.question, last.result.sources, last.result.graph_context);
  }, [ragConversation]);

  // Cmd+K / Ctrl+K 聚焦输入框
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        inputRef.current?.focus();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  useEffect(() => {
    if (token) loadAITabData(token, projectId);
  }, [token, projectId, loadAITabData]);

  useEffect(() => {
    // 仅当会话属于其他项目时清空；同项目内往返导航（如点引用跳数据页）保留多轮对话。
    if (ragConversationProjectId !== null && ragConversationProjectId !== projectId) {
      clearRagConversation();
    }
  }, [projectId, ragConversationProjectId, clearRagConversation]);

  useEffect(() => {
    if (ragConversation.length > 0 || busy) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
    }
  }, [ragConversation.length, busy]);

  const handleInit = async () => {
    if (!token || !canManage || initBusy) return;
    setInitBusy(true);
    setError("");
    try {
      await initRag(token, projectId);
      feedback.success("项目资料库已初始化");
    }
    catch (e) {
      const msg = getErrorMessage(e, "资料库初始化失败");
      setError(msg);
      feedback.error(msg);
    }
    finally { setInitBusy(false); }
  };

  const handleAsk = async (overrideQuestion?: string) => {
    const q = (overrideQuestion || question).trim();
    if (!token || !q || busy || !modeAvailable) return;
    setBusy(true); setError("");
    try {
      await queryRag(token, projectId, q, mode);
      setQuestion("");
    }
    catch (e) {
      const msg = getErrorMessage(e, "查询失败");
      setError(msg);
      feedback.error(msg);
    }
    finally { setBusy(false); }
  };

  const handleExport = useCallback(() => {
    if (ragConversation.length === 0) return;
    exportConversation(ragConversation, selectedProject?.name || `项目${projectId}`);
    feedback.success("对话已导出");
  }, [ragConversation, selectedProject, projectId, feedback]);

  const handleAnswerFeedback = async (logId: number | null, value: "helpful" | "not_helpful") => {
    if (!token || logId === null || feedbackBusy !== null || answerFeedback[logId]) return;
    setFeedbackBusy(logId);
    try {
      await submitQueryLogFeedback(token, logId, { value });
      setAnswerFeedback((current) => ({ ...current, [logId]: value }));
      feedback.success("感谢反馈，我们会用于后续优化");
    } catch (e) {
      feedback.error(getErrorMessage(e, "反馈提交失败"));
    } finally {
      setFeedbackBusy(null);
    }
  };

  // 未初始化时的引导步骤
  const initSteps = [
    { label: "上传实验资料", desc: "在「资料」标签页上传实验相关的文档和附件" },
    { label: "审核通过资料", desc: "审核人员对上传的资料进行审核确认" },
    { label: "初始化资料库", desc: "点击下方「初始化资料库」按钮，将审核通过的资料同步到 AI 知识库" },
    { label: "开始 AI 问答", desc: "项目资料问答需资料库就绪；纯 LLM 模式无需初始化即可使用" },
  ];

  return (
    <div className="space-y-4">
      {error && (
        <ErrorBanner className="flex items-center justify-between">
          <span>{error}</span>
          <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={() => { setError(""); }}>关闭</Button>
        </ErrorBanner>
      )}

      {/* 资料库状态卡片 */}
      <Card>
        <CardContent className="flex items-center justify-between py-4">
          <div className="flex items-center gap-3">
            <Database className="h-5 w-5 text-primary" />
            <div>
              <p className="text-sm font-medium">项目资料库</p>
              <p className="text-xs text-muted-foreground">
                {ragStatus === null
                  ? "状态加载中..."
                  : ragReady
                    ? ragSyncSummary
                    : "尚未初始化；项目资料问答需初始化，纯 LLM 模式可直接使用"}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {!ragReady && ragStatus !== null && canManage && (
              <Button size="sm" onClick={handleInit} disabled={initBusy} isLoading={initBusy}>
                {initBusy ? "初始化中..." : "初始化资料库"}
              </Button>
            )}
            {ragReady && (
              <UITooltip>
                <TooltipTrigger asChild>
                  <HelpCircle className="h-4 w-4 cursor-help text-muted-foreground" />
                </TooltipTrigger>
                <TooltipContent side="left" className="max-w-xs text-xs">
                  资料库已同步 {ragStatus.synced_count} 个文件。新审核通过的文件请到“资料”页执行本地向量入库；初始化只负责创建资料库或切换模型。
                </TooltipContent>
              </UITooltip>
            )}
          </div>
        </CardContent>
      </Card>

      {ragReady && ragStatus && (ragStatus.pending_sync_count > 0 || ragStatus.failed_sync_count > 0) && (
        <ErrorBanner>
          <span>
            {ragStatus.pending_sync_count > 0 && `有 ${ragStatus.pending_sync_count} 个已审核资料等待入库。`}
            {ragStatus.failed_sync_count > 0 && `有 ${ragStatus.failed_sync_count} 个资料入库失败，请重试。`}
            {" "}
            <Link className="underline" href={`/projects/${projectId}/data`}>前往资料页处理</Link>
          </span>
        </ErrorBanner>
      )}

      {/* 未初始化引导 */}
      {!ragReady && ragStatus !== null && (
        <Card className="border-dashed">
          <CardHeader>
            <CardTitle className="text-base">快速开始 AI 问答</CardTitle>
            <CardDescription>初始化后可使用项目资料问答；纯 LLM 和知识图谱结构化查询可直接使用</CardDescription>
          </CardHeader>
          <CardContent>
            <ol className="space-y-3">
              {initSteps.map((step, i) => (
                <li key={i} className="flex gap-3 text-sm">
                  <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-medium text-primary">{i + 1}</span>
                  <div>
                    <p className="font-medium">{step.label}</p>
                    <p className="text-xs text-muted-foreground">{step.desc}</p>
                  </div>
                </li>
              ))}
            </ol>
          </CardContent>
        </Card>
      )}

      {/* AI 问答主卡片 */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="flex items-center gap-2 text-base"><Sparkles className="h-5 w-5 text-primary" />AI 智能问答</CardTitle>
              <CardDescription>基于项目资料库和知识图谱回答实验相关问题</CardDescription>
            </div>
            {ragConversation.length > 0 && (
              <Button variant="outline" size="sm" onClick={handleExport} title="导出当前对话为 Markdown">
                <Download className="mr-1.5 h-3.5 w-3.5" />导出对话
              </Button>
            )}
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* 对话区域 */}
          {ragConversation.length > 0 && (
            <div className="space-y-3">
              {ragConversation.map((entry, index) => (
                <div key={index} className="space-y-2">
                  <div className="flex justify-end">
                    <p className="max-w-[80%] rounded-md bg-primary/10 px-3 py-2 text-sm whitespace-pre-wrap">
                      {entry.question}
                    </p>
                  </div>
                  <Card className="bg-muted/50"><CardContent className="py-4">
                    <RagAnswerBlock result={entry.result} projectId={projectId} />
                    {entry.result.query_log_id !== null && (
                      <div className="mt-3 flex items-center gap-2 border-t pt-2 text-xs text-muted-foreground">
                        <span>这个回答有帮助吗？</span>
                        <Button
                          variant={answerFeedback[entry.result.query_log_id] === "helpful" ? "secondary" : "ghost"}
                          size="sm"
                          className="h-7 px-2"
                          disabled={feedbackBusy !== null || Boolean(answerFeedback[entry.result.query_log_id])}
                          aria-label="回答有帮助"
                          onClick={() => handleAnswerFeedback(entry.result.query_log_id, "helpful")}
                        >
                          <ThumbsUp className="h-3.5 w-3.5" />有帮助
                        </Button>
                        <Button
                          variant={answerFeedback[entry.result.query_log_id] === "not_helpful" ? "secondary" : "ghost"}
                          size="sm"
                          className="h-7 px-2"
                          disabled={feedbackBusy !== null || Boolean(answerFeedback[entry.result.query_log_id])}
                          aria-label="回答没有帮助"
                          onClick={() => handleAnswerFeedback(entry.result.query_log_id, "not_helpful")}
                        >
                          <ThumbsDown className="h-3.5 w-3.5" />没帮助
                        </Button>
                      </div>
                    )}
                  </CardContent></Card>
                </div>
              ))}
              {/* 加载指示器 */}
              {busy && (
                <Card className="bg-muted/50"><CardContent className="flex items-center gap-2 py-4">
                  <Loader2 className="h-4 w-4 animate-spin text-primary" />
                  <span className="text-sm text-muted-foreground">正在检索并生成回答...</span>
                </CardContent></Card>
              )}
              <div ref={bottomRef} />
            </div>
          )}

          {/* 追问建议 */}
          {followUpSuggestions.length > 0 && !busy && modeAvailable && (
            <div className="flex flex-wrap gap-2">
              <MessageSquarePlus className="h-4 w-4 text-muted-foreground" />
              {followUpSuggestions.map((suggestion, i) => (
                <Button key={i} variant="outline" size="sm" className="h-7 text-xs font-normal"
                  onClick={() => handleAsk(suggestion)}>
                  {suggestion}
                </Button>
              ))}
            </div>
          )}

          {/* 输入区域 */}
          <div className="flex gap-2">
            <UITooltip>
              <TooltipTrigger asChild>
                <div className="shrink-0">
                  <Select value={mode} onValueChange={setMode}>
                    <SelectTrigger className="w-36"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {modes.map((m) => (
                        <SelectItem key={m.value} value={m.value}>
                          <span>{m.label}</span>
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </TooltipTrigger>
              <TooltipContent side="bottom" className="max-w-xs text-xs">
                {modes.find((m) => m.value === mode)?.desc || ""}
              </TooltipContent>
            </UITooltip>
            <Input ref={inputRef} value={question} onChange={(e) => setQuestion(e.target.value)}
              placeholder={modeAvailable
                ? (pureLlmMode ? "输入通用问题... (⌘K 聚焦，Enter 发送)" : "输入问题... (⌘K 聚焦，Enter 发送)")
                : "请先初始化项目资料库"}
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleAsk(); } }}
              disabled={!modeAvailable || busy}
              className="flex-1" />
            <Button onClick={() => handleAsk()} disabled={!modeAvailable || busy || !question.trim()} isLoading={busy}>
              <Send className="mr-2 h-4 w-4" />{busy ? "查询中..." : "提问"}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* 历史问答 */}
      {queryLogs.length > 0 && (
        <details className="rounded-md border">
          <summary className="cursor-pointer select-none px-4 py-3 text-sm font-medium">
            历史问答（{queryLogs.length} 条）
          </summary>
          <div className="space-y-2 border-t px-4 py-3">
            {queryLogs.map((log) => (
              <div key={log.id} className="rounded-md border p-3 text-sm">
                <p className="text-xs text-muted-foreground">
                  {new Date(log.created_at).toLocaleString("zh-CN")}
                  {" · "}
                  {ragModeText[log.rag_mode] || log.rag_mode}
                  {" · 耗时 "}
                  {log.response_ms} ms
                </p>
                <p className="mt-1 font-medium">{log.question}</p>
                {log.answer && (
                  <details className="mt-1">
                    <summary className="cursor-pointer select-none text-xs text-muted-foreground">查看回答</summary>
                    <div className="mt-1 text-sm whitespace-pre-wrap">
                      <CitationRichText
                        answer={log.answer}
                        sources={log.sources_json || []}
                        graphContext={log.graph_context_json || []}
                        projectId={projectId}
                      />
                    </div>
                  </details>
                )}
              </div>
            ))}
          </div>
        </details>
      )}
    </div>
  );
}
