"use client";

import { useState, useEffect } from "react";
import { useParams } from "next/navigation";
import { Play, FileText, Copy, ChevronsDownUp, ChevronsUpDown } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useAuthStore, useProjectStore } from "@/stores";
import { getErrorMessage } from "@/lib/utils";
import { agentTaskOptions } from "@/components/constants";
import { useActionFeedback } from "@/hooks/use-action-feedback";

const BODY_PREVIEW_LENGTH = 200;

const agentStatusText: Record<string, string> = {
  running: "运行中", completed: "已完成",
  failed: "失败", pending: "等待中", cancelled: "已取消",
};

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
  const feedback = useActionFeedback();
  const membership = members.find((member) => member.user_id === user?.id);
  const canWrite = user?.role === "super_admin" || membership?.can_write === true;

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

  if (busy) return <p className="text-sm text-muted-foreground py-8 text-center">加载中...</p>;

  return (
    <div className="space-y-4">
      {error && <p className="rounded-md bg-destructive/10 px-4 py-2 text-sm text-destructive">{error}</p>}

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
            <Button onClick={handleGenerate} disabled={agentBusy}>
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
          <CardHeader><CardTitle className="text-base">运行记录</CardTitle></CardHeader>
          <CardContent className="space-y-2">
            {agentRuns.map((run) => {
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
                  <p className="mt-1 text-xs text-muted-foreground">
                    状态: {agentStatusText[run.status] || run.status}
                    {" · 生成时间: "}
                    {new Date(run.created_at).toLocaleString("zh-CN")}
                  </p>
                  {run.body && (
                    <>
                      <div className="mt-2 rounded bg-muted/30 p-2 text-xs whitespace-pre-wrap max-h-64 overflow-y-auto">
                        {expanded || !collapsible ? run.body : `${run.body.slice(0, BODY_PREVIEW_LENGTH)}…`}
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
