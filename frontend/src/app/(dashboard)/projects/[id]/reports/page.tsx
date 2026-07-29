"use client";

import { useState, useEffect } from "react";
import { useParams } from "next/navigation";
import { Play } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useAuthStore, useProjectStore } from "@/stores";
import { getErrorMessage } from "@/lib/utils";

const tasks = [
  { value: "experiment_summary", label: "实验总结" },
  { value: "weekly_report", label: "周报" },
  { value: "stage_report", label: "项目阶段报告" },
];

const agentStatusText: Record<string, string> = {
  running: "运行中", completed: "已完成",
  failed: "失败", pending: "等待中", cancelled: "已取消",
};

export default function ReportsPage() {
  const { id } = useParams();
  const projectId = Number(id);
  const token = useAuthStore((s) => s.token);
  const agentRuns = useProjectStore((s) => s.agentRuns);
  const generateAgent = useProjectStore((s) => s.generateAgent);
  const loadTabProjectData = useProjectStore((s) => s.loadTabProjectData);
  const busy = useProjectStore((s) => s.busy);
  const [error, setError] = useState("");
  const [taskType, setTaskType] = useState("experiment_summary");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [agentBusy, setAgentBusy] = useState(false);

  useEffect(() => {
    if (token) loadTabProjectData(token, projectId);
  }, [token, projectId, loadTabProjectData]);

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

  if (busy) return <p className="text-sm text-muted-foreground py-8 text-center">加载中...</p>;

  return (
    <div className="space-y-4">
      {error && <p className="rounded-md bg-destructive/10 px-4 py-2 text-sm text-destructive">{error}</p>}

      <Card>
        <CardHeader><CardTitle className="text-base">智能体报告</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <div className="flex gap-2">
            <Select value={taskType} onValueChange={setTaskType}>
              <SelectTrigger className="w-44"><SelectValue /></SelectTrigger>
              <SelectContent>{tasks.map((t) => (<SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>))}</SelectContent>
            </Select>
            <Input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} className="w-36" />
            <Input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} className="w-36" />
            <Button onClick={handleGenerate} disabled={agentBusy}>
              <Play className="mr-2 h-4 w-4" />{agentBusy ? "生成中..." : "生成"}
            </Button>
          </div>
        </CardContent>
      </Card>

      {agentRuns.length > 0 && (
        <Card>
          <CardHeader><CardTitle className="text-base">运行记录</CardTitle></CardHeader>
          <CardContent className="space-y-2">
            {agentRuns.map((run) => (
              <div key={run.id} className="rounded-md border p-3 text-sm">
                <p className="font-medium">{run.title || run.task_type}</p>
                <p className="text-xs text-muted-foreground mt-1">状态: {agentStatusText[run.status] || run.status}</p>
                {run.body && (
                  <div className="mt-2 rounded bg-muted/30 p-2 text-xs whitespace-pre-wrap max-h-32 overflow-y-auto">
                    {run.body}
                  </div>
                )}
              </div>
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
