"use client";

import { useState, useEffect } from "react";
import { useParams } from "next/navigation";
import { Play, BarChart3, RotateCw, Download, CheckCircle2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useAuthStore, useProjectStore } from "@/stores";
import { downloadRagExperiment } from "@/lib/api";
import { getErrorMessage } from "@/lib/utils";

const experimentStatusText: Record<string, string> = {
  running: "运行中", completed: "已完成",
  failed: "失败", interrupted: "已中断", pending: "等待中",
};
const ragModeText: Record<string, string> = {
  auto: "自动选择", project_rag: "项目级 RAG",
  kg_enhanced_rag: "图谱增强 RAG", pure_llm: "纯 LLM", bm25_rag: "BM25 RAG",
};

export default function SystemTestPage() {
  const { id } = useParams();
  const projectId = Number(id);
  const token = useAuthStore((s) => s.token);
  const maturityStatus = useProjectStore((s) => s.maturityStatus);
  const experimentRuns = useProjectStore((s) => s.experimentRuns);
  const queryLogs = useProjectStore((s) => s.queryLogs);
  const runExperiment = useProjectStore((s) => s.runExperiment);
  const refreshExperimentRuns = useProjectStore((s) => s.refreshExperimentRuns);
  const resumeExperiment = useProjectStore((s) => s.resumeExperiment);
  const busy = useProjectStore((s) => s.busy);
  const loadTabProjectData = useProjectStore((s) => s.loadTabProjectData);
  const [error, setError] = useState("");

  useEffect(() => {
    if (token) loadTabProjectData(token, projectId);
  }, [token, projectId, loadTabProjectData]);

  // Experiment form
  const [expName, setExpName] = useState("普通 RAG 与图谱增强 RAG 对照实验");
  const [expQs, setExpQs] = useState("PCR 实验用了哪些关键试剂？\nPCR 实验的关键结果是什么？");
  const [expReps, setExpReps] = useState("3");
  const [expSeed, setExpSeed] = useState("20260712");
  const [expBusy, setExpBusy] = useState(false);
  const [expMessage, setExpMessage] = useState("");

  const handleRunExperiment = async () => {
    if (!token) return;
    setExpBusy(true); setError(""); setExpMessage("");
    try {
      await runExperiment(token, projectId, {
        name: expName,
        questions: expQs.split("\n").filter(Boolean),
        modes: ["pure_llm", "bm25_rag", "project_rag", "structured_query", "kg_enhanced_rag"],
        random_seed: Number(expSeed) || null,
        repetitions: Number(expReps) || 1,
      });
      for (let attempt = 0; attempt < 240; attempt += 1) {
        const runs = await refreshExperimentRuns(token, projectId);
        if (!runs) return;
        const run = runs.find((candidate) => candidate.name === expName);
        if (run && ["completed", "completed_with_errors", "failed"].includes(run.status)) {
          setExpMessage(`对照实验 #${run.id} 已结束：成功 ${run.completed_cases}，失败 ${run.failed_cases}`);
          return;
        }
        await new Promise((resolve) => window.setTimeout(resolve, 500));
      }
      throw new Error("实验运行超时，请在实验结果中检查状态");
    } catch (e) { setError(getErrorMessage(e, "实验失败")); }
    finally { setExpBusy(false); }
  };

  const handleResume = async (runId: number) => {
    if (!token) return;
    try {
      await resumeExperiment(token, runId);
      await refreshExperimentRuns(token, projectId);
    } catch (e) { setError(getErrorMessage(e, "续跑失败")); }
  };

  const handleDownload = async (runId: number) => {
    if (!token) return;
    try {
      const blob = await downloadRagExperiment(token, runId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = `experiment-${runId}.csv`; a.click();
      URL.revokeObjectURL(url);
    } catch (e) { setError(getErrorMessage(e, "下载失败")); }
  };

  if (busy) return <p className="text-sm text-muted-foreground py-8 text-center">加载中...</p>;

  return (
    <div className="space-y-4">
      {error && <p className="rounded-md bg-destructive/10 px-4 py-2 text-sm text-destructive">{error}</p>}
      {expMessage && <p className="rounded-md bg-green-50 px-4 py-2 text-sm text-green-700">{expMessage}</p>}

      <div className="flex items-center gap-2">
        <CheckCircle2 className="h-5 w-5 text-muted-foreground" />
        <p className="text-sm text-muted-foreground">系统性能测试与可信性验证 — 不会出现在常规用户工作流中</p>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <Card>
          <CardHeader><CardTitle className="text-base">成熟度检查</CardTitle></CardHeader>
          <CardContent>
            <p className="text-3xl font-bold">{maturityStatus?.passed ? "✅ 通过" : "⏳ 未通过"}</p>
            <p className="text-xs text-muted-foreground mt-1">发布就绪验证</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle className="text-base">对照实验</CardTitle></CardHeader>
          <CardContent>
            <p className="text-3xl font-bold">{experimentRuns.length}</p>
            <p className="text-xs text-muted-foreground mt-1">运行次数</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle className="text-base">查询日志</CardTitle></CardHeader>
          <CardContent>
            <p className="text-3xl font-bold">{queryLogs.length}</p>
            <p className="text-xs text-muted-foreground mt-1">日志条数</p>
          </CardContent>
        </Card>
      </div>

      <Tabs defaultValue="experiment">
        <TabsList>
          <TabsTrigger value="experiment"><Play className="mr-1 h-4 w-4" />对照实验</TabsTrigger>
          <TabsTrigger value="runs"><BarChart3 className="mr-1 h-4 w-4" />实验结果</TabsTrigger>
          <TabsTrigger value="logs"><BarChart3 className="mr-1 h-4 w-4" />查询日志</TabsTrigger>
        </TabsList>

        {/* 运行对照实验 */}
        <TabsContent value="experiment" className="space-y-4 mt-4">
          <Card>
            <CardHeader><CardTitle className="text-base">运行对照实验</CardTitle>
              <CardDescription>多模式 RAG 对比测试，评估检索质量和回答准确率</CardDescription></CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="experiment-name">实验名称</Label>
                <Input id="experiment-name" value={expName} onChange={(e) => setExpName(e.target.value)} placeholder="如：RAG 模式对比实验" />
              </div>
              <div className="space-y-2">
                <Label htmlFor="experiment-questions">测试问题（每行一个）</Label>
                <Textarea id="experiment-questions" rows={3} value={expQs} onChange={(e) => setExpQs(e.target.value)}
                  placeholder="每行输入一个测试问题" />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="experiment-repetitions">每种方法重复次数</Label>
                  <Input id="experiment-repetitions" type="number" min={1} max={10} value={expReps} onChange={(e) => setExpReps(e.target.value)} />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="experiment-seed">随机种子</Label>
                  <Input id="experiment-seed" value={expSeed} onChange={(e) => setExpSeed(e.target.value)} placeholder="如：20260712" />
                </div>
              </div>
              <Button onClick={handleRunExperiment} disabled={expBusy}>
                <Play className="mr-2 h-4 w-4" />{expBusy ? "运行中..." : "运行五方法对照实验"}
              </Button>
            </CardContent>
          </Card>
        </TabsContent>

        {/* 实验结果 */}
        <TabsContent value="runs" className="space-y-4 mt-4">
          {experimentRuns.length === 0 ? (
            <Card className="border-dashed"><CardContent className="py-12 text-center"><p className="text-sm text-muted-foreground">暂无实验记录</p></CardContent></Card>
          ) : (
            <div className="space-y-3">
              {experimentRuns.map((run) => (
                <Card key={run.id}>
                  <CardContent className="flex items-center justify-between py-4">
                    <div>
                      <p className="font-medium">{run.name}</p>
                      <div className="flex gap-2 mt-1">
                        <Badge variant={run.status === "completed" ? "default" : "secondary"}>{experimentStatusText[run.status] || run.status}</Badge>
                        <span className="text-xs text-muted-foreground">
                          {run.questions_json?.length || 0} 题 · {run.completed_cases || 0}/{run.total_cases || 0}
                        </span>
                      </div>
                      {run.status === "interrupted" && (
                        <Button size="sm" variant="outline" className="mt-2" onClick={() => handleResume(run.id)}>
                          <RotateCw className="mr-1 h-3 w-3" />续跑
                        </Button>
                      )}
                    </div>
                    <Button size="sm" variant="outline" onClick={() => handleDownload(run.id)}>
                      <Download className="mr-1 h-4 w-4" />导出 CSV
                    </Button>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>

        {/* 查询日志 */}
        <TabsContent value="logs" className="space-y-4 mt-4">
          {queryLogs.length === 0 ? (
            <Card className="border-dashed"><CardContent className="py-12 text-center"><p className="text-sm text-muted-foreground">暂无查询日志</p></CardContent></Card>
          ) : (
            <div className="space-y-3">
              {queryLogs.map((log) => (
                <Card key={log.id}>
                  <CardHeader className="pb-2">
                    <div className="flex items-start justify-between">
                      <p className="text-sm font-medium">{log.question}</p>
                      <Badge variant="outline" className="text-xs">{ragModeText[log.rag_mode] || log.rag_mode}</Badge>
                    </div>
                    <p className="text-xs text-muted-foreground mt-1">
                      来源: {log.source_count} · 图谱命中: {log.graph_hit_count} · {(log.response_ms / 1000).toFixed(1)}s
                    </p>
                  </CardHeader>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}
