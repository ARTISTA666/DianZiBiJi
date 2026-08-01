"use client";

import { useState, useEffect } from "react";
import { useParams } from "next/navigation";
import { Database, Send, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useAuthStore, useProjectStore } from "@/stores";
import { getErrorMessage } from "@/lib/utils";
import { useActionFeedback } from "@/hooks/use-action-feedback";

const modes = [
  { value: "auto", label: "自动选择" },
  { value: "project_rag", label: "项目级 RAG" },
  { value: "kg_enhanced_rag", label: "图谱增强 RAG" },
  { value: "pure_llm", label: "纯 LLM" },
  { value: "bm25_rag", label: "BM25 RAG" },
];

export default function AIPage() {
  const { id } = useParams();
  const projectId = Number(id);
  const token = useAuthStore((s) => s.token);
  const user = useAuthStore((s) => s.user);
  const ragAnswer = useProjectStore((s) => s.ragAnswer);
  const ragStatus = useProjectStore((s) => s.ragStatus);
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
  const feedback = useActionFeedback();
  const membership = members.find((member) => member.user_id === user?.id);
  const canManage = user?.role === "super_admin"
    || selectedProject?.owner_user_id === user?.id
    || membership?.can_manage === true
    || membership?.project_role === "owner";
  const ragReady = ragStatus?.initialized === true;

  useEffect(() => {
    if (token) loadAITabData(token, projectId);
  }, [token, projectId, loadAITabData]);

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

  const handleAsk = async () => {
    if (!token || !question.trim() || busy || !ragReady) return;
    setBusy(true); setError("");
    try {
      await queryRag(token, projectId, question.trim(), mode);
      setQuestion("");
    }
    catch (e) {
      const msg = getErrorMessage(e, "查询失败");
      setError(msg);
      feedback.error(msg);
    }
    finally { setBusy(false); }
  };

  return (
    <div className="space-y-4">
      {error && <p className="rounded-md bg-destructive/10 px-4 py-2 text-sm text-destructive">{error}</p>}

      <Card>
        <CardContent className="flex items-center justify-between py-4">
          <div className="flex items-center gap-3">
            <Database className="h-5 w-5 text-primary" />
            <div>
              <p className="text-sm font-medium">项目资料库</p>
              <p className="text-xs text-muted-foreground">
                {ragStatus === null
                  ? "状态暂不可用"
                  : ragReady
                    ? `已初始化 · ${ragStatus.synced_count} 个文件已入库`
                    : "尚未初始化，初始化后才能使用 AI 问答"}
              </p>
            </div>
          </div>
          {!ragReady && ragStatus !== null && canManage && (
            <Button size="sm" onClick={handleInit} disabled={initBusy}>
              {initBusy ? "初始化中..." : "初始化资料库"}
            </Button>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base"><Sparkles className="h-5 w-5 text-primary" />AI 智能问答</CardTitle>
          <CardDescription>基于项目资料库和知识图谱回答实验相关问题</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex gap-2">
            <Select value={mode} onValueChange={setMode}>
              <SelectTrigger className="w-36"><SelectValue /></SelectTrigger>
              <SelectContent>{modes.map((m) => (<SelectItem key={m.value} value={m.value}>{m.label}</SelectItem>))}</SelectContent>
            </Select>
            <Input value={question} onChange={(e) => setQuestion(e.target.value)}
              placeholder={ragReady ? "输入问题..." : "请先初始化项目资料库"}
              onKeyDown={(e) => e.key === "Enter" && handleAsk()}
              disabled={!ragReady || busy}
              className="flex-1" />
            <Button onClick={handleAsk} disabled={!ragReady || busy || !question.trim()}>
              <Send className="mr-2 h-4 w-4" />{busy ? "查询中..." : "提问"}
            </Button>
          </div>
          {ragAnswer && (
            <div className="mt-4">
              <Card className="bg-muted/50"><CardContent className="py-4">
                <p className="text-sm whitespace-pre-wrap">{ragAnswer.answer}</p>
                {ragAnswer.sources && ragAnswer.sources.length > 0 && (
                  <div className="mt-3 pt-3 border-t">
                    <p className="text-xs text-muted-foreground mb-1">来源：</p>
                    {ragAnswer.sources.map((src, i) => (
                      <p key={i} className="text-xs text-muted-foreground">· {src.filename || src.snippet?.slice(0, 80)}</p>
                    ))}
                  </div>
                )}
              </CardContent></Card>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
