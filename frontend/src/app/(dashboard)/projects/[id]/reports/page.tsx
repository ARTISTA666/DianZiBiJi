"use client";

import { useState, useEffect, useMemo, type ReactNode } from "react";
import { useParams } from "next/navigation";
import { Play, FileText, Copy, ChevronsDownUp, ChevronsUpDown, AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useAuthStore, useProjectStore } from "@/stores";
import { getErrorMessage } from "@/lib/utils";
import { agentTaskOptions } from "@/components/constants";
import { useActionFeedback } from "@/hooks/use-action-feedback";
import { ErrorBanner } from "@/components/shared/error-banner";
import { PageLoadingSkeleton } from "@/components/skeletons";

const BODY_PREVIEW_LENGTH = 200;

const agentStatusText: Record<string, string> = {
  running: "运行中", completed: "已完成",
  needs_review: "待人工复核", failed: "失败", pending: "等待中", cancelled: "已取消",
};

function renderInline(text: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, index) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={index}>{part.slice(2, -2)}</strong>;
    }
    return <span key={index}>{part}</span>;
  });
}

function renderReportBody(body: string): ReactNode[] {
  const blocks: ReactNode[] = [];
  let bullets: string[] = [];
  const flushBullets = () => {
    if (bullets.length === 0) return;
    blocks.push(
      <ul key={`list-${blocks.length}`} className="list-disc space-y-1 pl-5">
        {bullets.map((item, index) => <li key={index}>{renderInline(item)}</li>)}
      </ul>,
    );
    bullets = [];
  };

  body.replace(/\r/g, "").split("\n").forEach((rawLine, index) => {
    const line = rawLine.trim();
    if (!line || line === "---") {
      flushBullets();
      return;
    }
    const bullet = line.match(/^[-*]\s+(.+)/);
    if (bullet) {
      bullets.push(bullet[1]);
      return;
    }
    flushBullets();
    const heading = line.match(/^#{2,6}\s+(.+)/);
    if (heading) {
      blocks.push(<h3 key={`heading-${index}`} className="pt-2 text-base font-semibold text-foreground">{renderInline(heading[1])}</h3>);
      return;
    }
    blocks.push(<p key={`paragraph-${index}`}>{renderInline(line)}</p>);
  });
  flushBullets();
  return blocks;
}

export default function ReportsPage() {
  const { id } = useParams();
  const projectId = Number(id);
  const token = useAuthStore((s) => s.token);
  const user = useAuthStore((s) => s.user);
  const agentRuns = useProjectStore((s) => s.agentRuns);
  const members = useProjectStore((s) => s.members);
  const generateAgent = useProjectStore((s) => s.generateAgent);
  const loadReportsTabData = useProjectStore((s) => s.loadReportsTabData);
  const busy = useProjectStore((s) => s.busy);
  const [error, setError] = useState("");
  const [taskType, setTaskType] = useState("experiment_summary");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [agentBusy, setAgentBusy] = useState(false);
  const [expandedRunIds, setExpandedRunIds] = useState<Set<number>>(new Set());
  const [onlySuccess, setOnlySuccess] = useState(false);
  const feedback = useActionFeedback();
  const membership = members.find((member) => member.user_id === user?.id);
  const canWrite = user?.role === "super_admin" || membership?.can_write === true;

  // 排序与过滤：成功/待审记录优先置顶，失败记录后置；支持“仅看成功”过滤
  const sortedAndFilteredRuns = useMemo(() => {
    let list = [...agentRuns];
    if (onlySuccess) {
      list = list.filter((r) => r.status !== "failed");
    }
    list.sort((a, b) => {
      const aFailed = a.status === "failed" ? 1 : 0;
      const bFailed = b.status === "failed" ? 1 : 0;
      if (aFailed !== bFailed) return aFailed - bFailed;
      return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
    });
    return list;
  }, [agentRuns, onlySuccess]);

  useEffect(() => {
    if (token) loadReportsTabData(token, projectId);
  }, [token, projectId, loadReportsTabData]);

  const handleGenerate = async () => {
    if (!token) return;
    setAgentBusy(true); setError("");
    try {
      await generateAgent(token, projectId, {
        task_type: taskType,
        date_from: dateFrom || null,
        date_to: dateTo || null,
      });
    } catch (e) { setError(getErrorMessage(e, "生成失败")); }
    finally { setAgentBusy(false); }
  };

  const toggleExpanded = (runId: number) => {
    setExpandedRunIds((prev) => {
      const next = new Set(prev);
      if (next.has(runId)) next.delete(runId);
      else next.add(runId);
      return next;
    });
  };

  const handleCopy = async (body: string) => {
    try {
      await navigator.clipboard.writeText(body);
      feedback.success("报告内容已复制");
    } catch {
      feedback.error("复制失败，请手动选择文本复制");
    }
  };

  if (busy) return <PageLoadingSkeleton />;

  return (
    <div className="space-y-4">
      {error && <ErrorBanner message={error} />}

      <Card>
        <CardHeader><CardTitle className="text-base">智能体报告</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          {canWrite ? <div className="flex gap-2">
            <Select value={taskType} onValueChange={setTaskType}>
              <SelectTrigger className="w-44"><SelectValue /></SelectTrigger>
              <SelectContent>{agentTaskOptions.map((t) => (<SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>))}</SelectContent>
            </Select>
            <Input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} className="w-36" />
            <Input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} className="w-36" />
            <Button onClick={handleGenerate} disabled={agentBusy} isLoading={agentBusy}>
              <Play className="mr-2 h-4 w-4" />{agentBusy ? "生成中..." : "生成"}
            </Button>
          </div> : <p className="text-sm text-muted-foreground">只读成员可以查看已生成报告，不能创建新的智能体任务。</p>}
        </CardContent>
      </Card>

      {agentRuns.length === 0 ? (
        <Card className="border-dashed">
          <CardContent className="flex flex-col items-center justify-center py-12 text-center">
            <FileText className="h-12 w-12 text-muted-foreground/50 mb-4" />
            <p className="text-lg font-medium text-muted-foreground">还没有生成过报告</p>
            <p className="text-sm text-muted-foreground/70 mt-1">使用上方工具生成实验总结、周报、阶段报告、图谱概览、文献综述或异常检测</p>
            {canWrite && <Button className="mt-4" variant="outline" onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}>
              <Play className="mr-2 h-4 w-4" />去 AI 问答生成
            </Button>}
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-3">
            <CardTitle className="text-base">
              运行记录 ({sortedAndFilteredRuns.length}
              {onlySuccess ? ` / 全部 ${agentRuns.length}` : ""})
            </CardTitle>
            <label className="flex items-center gap-1.5 text-xs font-normal text-muted-foreground cursor-pointer hover:text-foreground">
              <input
                type="checkbox"
                checked={onlySuccess}
                onChange={(e) => setOnlySuccess(e.target.checked)}
                className="h-3.5 w-3.5 rounded border-gray-300 text-primary focus:ring-primary"
              />
              仅看成功与就绪记录
            </label>
          </CardHeader>
          <CardContent className="space-y-2">
            {sortedAndFilteredRuns.map((run) => {
              const expanded = expandedRunIds.has(run.id);
              const collapsible = run.body.length > BODY_PREVIEW_LENGTH;
              return (
                <div key={run.id} className="rounded-md border p-3 text-sm">
                  <div className="flex items-center justify-between gap-2">
                    <p className="font-medium">{run.title || run.task_type}</p>
                    {run.body && (
                      <Button size="sm" variant="ghost" className="h-7 px-2 text-xs" onClick={() => handleCopy(run.body)}>
                        <Copy className="mr-1 h-3 w-3" />复制
                      </Button>
                    )}
                  </div>
                  <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                    <span>状态:</span>
                    <span
                      className={`inline-flex items-center rounded px-1.5 py-0.5 text-[11px] font-medium ${
                        run.status === "completed"
                          ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-400"
                          : run.status === "failed"
                          ? "bg-destructive/10 text-destructive cursor-help"
                          : run.status === "needs_review"
                          ? "bg-amber-50 text-amber-800 dark:bg-amber-950/40 dark:text-amber-300"
                          : "bg-muted text-muted-foreground"
                      }`}
                      title={run.status === "failed" ? (run.message || "执行中断或超出Token上限，已记录在错误日志中") : undefined}
                    >
                      {agentStatusText[run.status] || run.status}
                    </span>
                    <span>{" · 生成时间: "}</span>
                    <span>{new Date(run.created_at).toLocaleString("zh-CN")}</span>
                  </div>
                  {run.status === "failed" && (
                    <div className="mt-2 rounded bg-destructive/5 border border-destructive/20 p-2.5 text-xs text-destructive flex items-start gap-2">
                      <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
                      <div>
                        <p className="font-medium">任务执行中断</p>
                        <p className="text-[11px] text-muted-foreground mt-0.5">
                          {run.message || "由于历史模型 max_tokens 限制或网络波动中断；可在上方重新发起任务。"}
                        </p>
                      </div>
                    </div>
                  )}
                  {run.status === "needs_review" && (
                    <p className="mt-2 rounded bg-amber-50 px-2 py-1 text-xs text-amber-800">
                      引用校验未完全通过。请人工核对来源后再使用此草稿。
                    </p>
                  )}
                  {run.body && (
                    <>
                      <div className={`mt-3 rounded-lg border bg-background p-4 text-sm leading-7 ${expanded || !collapsible ? "" : "max-h-80 overflow-hidden"}`}>
                        {renderReportBody(run.body)}
                      </div>
                      <div className="mt-2 flex flex-wrap gap-2 text-xs text-muted-foreground">
                        <span>来源笔记 {run.source_note_ids_json.length}</span>
                        <span>来源资料 {run.source_file_ids_json.length}</span>
                        <span>图谱依据 {run.source_graph_relation_ids_json.length}</span>
                      </div>
                      {collapsible && (
                        <Button size="sm" variant="ghost" className="mt-1 h-7 px-2 text-xs"
                          onClick={() => toggleExpanded(run.id)}>
                          {expanded
                            ? <><ChevronsDownUp className="mr-1 h-3 w-3" />收起</>
                            : <><ChevronsUpDown className="mr-1 h-3 w-3" />展开全文</>}
                        </Button>
                      )}
                    </>
                  )}
                </div>
              );
            })}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
