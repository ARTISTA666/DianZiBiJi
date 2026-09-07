"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import {
  Bot,
  FileText,
  FolderOpen,
  Loader2,
  Network,
  Paperclip,
  Send,
  Users,
  X,
  BrainCircuit,
  ChevronDown,
  ChevronRight,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  approveAgentPendingAction,
  cancelAgentTurn,
  createAgentSession,
  createAgentTurn,
  getProjectRagStatus,
  rejectAgentPendingAction,
  startAgentTurn,
  subscribeAgentSessionEvents,
  type AgentProfile,
  type AgentRuntimeSnapshot,
} from "@/lib/api";
import { useAuthStore, useProjectStore } from "@/stores";

import { runAgentCommands } from "./agent-assistant/commands";
import {
  agentErrorMessage,
  formatAgentBudget,
  initialMessages,
  projectIdFromPath,
  redactSensitiveText,
} from "./agent-assistant/intents";
import type { AgentCommandContext, AgentMessage } from "./agent-assistant/types";

type QuickAction = {
  label: string;
  prompt: string;
  icon: typeof FileText;
};

type PendingConfirmation = {
  description: string;
  action: () => Promise<string>;
  cancel?: () => Promise<void>;
};

type PendingPlan = {
  turnId: string;
  planHash: string;
  text: string;
  budget: Record<string, unknown>;
};

export function AgentAssistant() {
  const pathname = usePathname();
  const router = useRouter();
  const token = useAuthStore((state) => state.token);
  const user = useAuthStore((state) => state.user);
  const selectedProject = useProjectStore((state) => state.selectedProject);
  const selectedProjectId = useProjectStore((state) => state.selectedProjectId);
  const projects = useProjectStore((state) => state.projects);
  const notes = useProjectStore((state) => state.notes);
  const files = useProjectStore((state) => state.files);
  const members = useProjectStore((state) => state.members);
  const storeRagStatus = useProjectStore((state) => state.ragStatus);
  const uploadFile = useProjectStore((state) => state.uploadFile);

  const [open, setOpen] = useState(false);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [ragReady, setRagReady] = useState<boolean | null>(null);
  const [messages, setMessages] = useState<AgentMessage[]>(initialMessages);
  const [pendingConfirmation, setPendingConfirmation] = useState<PendingConfirmation | null>(null);
  const [pendingPlan, setPendingPlan] = useState<PendingPlan | null>(null);
  const [agentProfile, setAgentProfile] = useState<AgentProfile>("fast");
  const [liveAgentStatus, setLiveAgentStatus] = useState<string | null>(null);
  const [chainOfThought, setChainOfThought] = useState<Array<{ step: string; detail: string; status: string }>>([]);
  const [showChain, setShowChain] = useState(false);
  const [uploading, setUploading] = useState(false);
  const messageId = useRef(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const ragRequestId = useRef(0);
  const serverSessionId = useRef<string | null>(null);
  const eventStreamCleanup = useRef<(() => void) | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  const currentProjectId = projectIdFromPath(pathname);
  const currentProject = selectedProject?.id === currentProjectId ? selectedProject : null;

  const quickActions = useMemo<QuickAction[]>(() => {
    if (currentProjectId === null) {
      return [
        { label: "列出项目", prompt: "我现在可以访问哪些项目？", icon: FolderOpen },
        { label: "打开管理", prompt: "打开管理页面", icon: Users },
      ];
    }
    return [
      { label: "总结本周进展", prompt: "生成本周周报", icon: FileText },
      { label: "查看项目成员", prompt: "列出当前项目成员", icon: Users },
      { label: "打开实验图谱", prompt: "打开实验图谱", icon: Network },
    ];
  }, [currentProjectId]);

  useEffect(() => {
    if (storeRagStatus !== null && selectedProjectId === currentProjectId) {
      setRagReady(storeRagStatus.initialized);
    }
  }, [currentProjectId, selectedProjectId, storeRagStatus]);

  useEffect(() => {
    setRagReady(null);
    setMessages(initialMessages);
    setPendingConfirmation(null);
    setPendingPlan(null);
    setAgentProfile("fast");
    setLiveAgentStatus(null);
    setChainOfThought([]);
    eventStreamCleanup.current?.();
    eventStreamCleanup.current = null;
    serverSessionId.current = null;
  }, [currentProjectId]);

  useEffect(() => () => {
    eventStreamCleanup.current?.();
    eventStreamCleanup.current = null;
  }, []);

  useEffect(() => {
    if (!open || !token || currentProjectId === null) return;
    const requestId = ++ragRequestId.current;
    getProjectRagStatus(token, currentProjectId)
      .then((status) => {
        if (requestId === ragRequestId.current) setRagReady(status.initialized);
      })
      .catch(() => {
        if (requestId === ragRequestId.current) setRagReady(null);
      });
  }, [currentProjectId, open, token]);

  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open]);

  if (!user) return null;

  const addMessage = (message: Omit<AgentMessage, "id">) => {
    messageId.current += 1;
    const id = globalThis.crypto.randomUUID();
    setMessages((current) => [...current, { ...message, id }]);
  };

  const askConfirmation = (description: string, action: () => Promise<string>, cancel?: () => Promise<void>) => {
    setPendingConfirmation({ description, action, cancel });
    addMessage({ role: "assistant", content: `${description}\n\n这是可能改变或不可逆的操作。回复“确认”继续，回复“取消”放弃。` });
  };

  const commandContext: AgentCommandContext = {
    token: token || "",
    currentProjectId,
    projects,
    notes,
    files,
    members,
    ragReady,
    setRagReady: (ready) => setRagReady(ready),
    router,
    addMessage,
    askConfirmation,
  };

  const renderAgentTurnResult = (snapshot: AgentRuntimeSnapshot) => {
    const assistant = [...snapshot.messages].reverse().find((message) => message.role === "assistant");
    const recentSteps = snapshot.steps.slice(-8);
    addMessage({
      role: "assistant",
      content: assistant?.content || "服务端 Agent 已完成本轮处理。",
      meta: recentSteps.length
        ? recentSteps.map((step) => `${step.tool_name}: ${step.status}`).join(" · ")
        : `${snapshot.session.provider} / ${snapshot.session.model_name}`,
    });
    const pending = [...snapshot.pending_actions].reverse().find((action) => action.status === "pending");
    if (pending) {
      askConfirmation(
        `确认执行 ${pending.tool_name}（${pending.arguments_summary}）？`,
        async () => {
          const approved = await approveAgentPendingAction(token || "", pending.id);
          return approved.execution_status === "completed"
            ? `${pending.tool_name} 已执行完成。`
            : `${pending.tool_name} 已确认，当前状态：${approved.execution_status}。`;
        },
        async () => { await rejectAgentPendingAction(token || "", pending.id); },
      );
    }
  };

  const approvePendingPlan = async () => {
    if (!pendingPlan || !token || !serverSessionId.current) return;
    const plan = pendingPlan;
    const sessionId = serverSessionId.current;
    setPendingPlan(null);
    setBusy(true);
    addMessage({ role: "assistant", content: "计划已确认，正在按计划执行…" });
    try {
      const result = await startAgentTurn(token, sessionId, plan.turnId, plan.planHash);
      renderAgentTurnResult(result);
    } catch (error) {
      addMessage({ role: "assistant", content: agentErrorMessage(error, "深度 Agent 执行失败，未自动重试。") });
    } finally {
      setBusy(false);
    }
  };

  const cancelPendingPlan = async () => {
    if (!pendingPlan || !token || !serverSessionId.current) return;
    const plan = pendingPlan;
    setPendingPlan(null);
    setBusy(true);
    try {
      await cancelAgentTurn(token, serverSessionId.current, plan.turnId);
      addMessage({ role: "assistant", content: "深度计划已取消，未执行任何工具。" });
    } catch (error) {
      addMessage({ role: "assistant", content: agentErrorMessage(error, "取消计划失败，请刷新会话确认当前状态。") });
    } finally {
      setBusy(false);
    }
  };

  const sendMessage = async (rawText: string) => {
    const text = rawText.trim();
    if (!text || busy || uploading) return;
    addMessage({ role: "user", content: redactSensitiveText(text) });
    setInput("");
    setBusy(true);

    try {
      if (!token) {
        addMessage({ role: "assistant", content: "登录状态已失效，请重新登录后再试。" });
        return;
      }

      if (process.env.NEXT_PUBLIC_NEW_AGENT_ENABLED === "true") {
        if (pendingPlan) {
          if (/^(确认|确定|是|执行|继续|好|好的|yes|ok)$/i.test(text)) {
            await approvePendingPlan();
          } else if (/^(取消|不用|不要|否|no|cancel)$/i.test(text)) {
            await cancelPendingPlan();
          } else {
            addMessage({ role: "assistant", content: "当前已有待确认的深度计划，请点击确认/取消，或直接回复“确认”/“取消”。" });
          }
          return;
        }
        if (pendingConfirmation) {
          if (/^(确认|确定|是|执行|继续|好|好的|yes|ok)$/i.test(text)) {
            const action = pendingConfirmation.action;
            setPendingConfirmation(null);
            addMessage({ role: "assistant", content: "正在执行已确认的操作…" });
            addMessage({ role: "assistant", content: await action() });
          } else if (/^(取消|不用|不要|否|no|cancel)$/i.test(text)) {
            await pendingConfirmation.cancel?.();
            setPendingConfirmation(null);
            addMessage({ role: "assistant", content: "已取消。" });
          } else {
            addMessage({ role: "assistant", content: "请回复“确认”或“取消”。" });
          }
          return;
        }
        let sessionId = serverSessionId.current;
        if (!sessionId) {
          const created = await createAgentSession(token, currentProjectId);
          sessionId = created.session.id;
          serverSessionId.current = sessionId;
          eventStreamCleanup.current?.();
          eventStreamCleanup.current = subscribeAgentSessionEvents(token, sessionId, (event) => {
            const tool = typeof event.data.tool === "string" ? event.data.tool : "工具";
            if (event.event === "plan.preview") {
              const planText = (event.data as { plan?: { text?: unknown } }).plan?.text ?? "";
              const planTextString = typeof planText === "string" ? planText : "";
              setChainOfThought((current) => [...current, { step: "生成研究计划", detail: planTextString.slice(0, 240), status: "done" }]);
            } else if (event.event === "tool.started") {
              setLiveAgentStatus(`正在执行：${tool}`);
              setChainOfThought((current) => [...current, { step: `调用 ${tool}`, detail: String(event.data.arguments_summary ?? ""), status: "running" }]);
            } else if (event.event === "confirmation.required") {
              setLiveAgentStatus("等待确认高风险操作");
              setChainOfThought((current) => [...current, { step: `高风险操作 ${tool} 等待确认`, detail: "", status: "waiting" }]);
            } else if (event.event === "tool.completed") {
              setLiveAgentStatus(`已完成：${tool}`);
              setChainOfThought((current) => current.map((entry, index) => index === current.length - 1 && entry.status === "running" ? { ...entry, status: "done" } : entry));
            } else if (event.event === "turn.completed" || event.event === "turn.cancelled") {
              setLiveAgentStatus(null);
              setChainOfThought((current) => current.map((entry) => entry.status === "running" ? { ...entry, status: "done" } : entry));
            } else if (event.event === "error") {
              setLiveAgentStatus("服务端 Agent 发生错误");
            }
          }, () => setLiveAgentStatus("事件连接中断，当前操作不会自动重试"));
        }
        const response = await createAgentTurn(token, sessionId, text, agentProfile);
        if ("plan_hash" in response) {
          setPendingPlan({
            turnId: response.turn_id,
            planHash: response.plan_hash,
            text: response.plan.text || "服务端未返回可展示的计划正文。",
            budget: response.budget,
          });
          addMessage({
            role: "assistant",
            content: `深度模式已生成执行计划：\n\n${response.plan.text || "（计划正文为空）"}`,
            meta: `计划待确认 · ${formatAgentBudget(response.budget)}`,
          });
          return;
        }
        renderAgentTurnResult(response);
        return;
      }

      if (pendingConfirmation) {
        if (/^(确认|确定|是|执行|继续|好|好的|yes|ok)$/i.test(text)) {
          const action = pendingConfirmation.action;
          setPendingConfirmation(null);
          addMessage({ role: "assistant", content: "正在执行已确认的操作…" });
          addMessage({ role: "assistant", content: await action() });
        } else if (/^(取消|不用|不要|否|no|cancel)$/i.test(text)) {
          setPendingConfirmation(null);
          addMessage({ role: "assistant", content: "已取消。" });
        } else {
          addMessage({ role: "assistant", content: `请确认是否${pendingConfirmation.description.split("\n")[0]}。回复“确认”或“取消”。` });
        }
        return;
      }

      await runAgentCommands(commandContext, text);
    } catch (error) {
      addMessage({ role: "assistant", content: agentErrorMessage(error, "Agent 执行失败，请稍后重试。") });
    } finally {
      setBusy(false);
    }
  };

  const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file || !token) return;
    if (currentProjectId === null) {
      addMessage({ role: "assistant", content: "请先进入项目，再上传资料。" });
      return;
    }
    setUploading(true);
    try {
      const uploaded = await uploadFile(token, currentProjectId, file);
      addMessage({ role: "assistant", content: `资料「${uploaded.original_filename}」已上传。后续可以说“审核通过资料 ${uploaded.id}”或“同步资料 ${uploaded.id}”。` });
    } catch (error) {
      addMessage({ role: "assistant", content: agentErrorMessage(error, "资料上传失败，请稍后重试。") });
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="fixed bottom-5 right-5 z-[60] flex flex-col items-end gap-3">
      {open && (
        <section aria-label="Agent 助手" className="flex h-[min(680px,calc(100vh-7rem))] w-[min(430px,calc(100vw-2rem))] flex-col overflow-hidden rounded-2xl border bg-background shadow-2xl ring-1 ring-black/5">
          <div className="flex items-center justify-between bg-primary px-4 py-3 text-primary-foreground">
            <div className="flex items-center gap-3">
              <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-white/15"><Bot className="h-5 w-5" /></div>
              <div>
                <p className="text-sm font-semibold">Agent 助手</p>
                <p className="text-xs text-primary-foreground/75">{currentProject?.name || "跨项目工作区"}</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <label className="sr-only" htmlFor="agent-profile">Agent 模式</label>
              <select
                id="agent-profile"
                value={agentProfile}
                onChange={(event) => setAgentProfile(event.target.value as AgentProfile)}
                disabled={busy || Boolean(pendingPlan)}
                className="h-8 rounded-md border border-white/20 bg-white/10 px-2 text-xs text-primary-foreground outline-none"
              >
                <option value="fast" className="text-foreground">快速</option>
                <option value="deep" className="text-foreground">深度（需确认计划）</option>
              </select>
              <Button aria-label="关闭 Agent" variant="ghost" size="icon" className="h-8 w-8 text-primary-foreground hover:bg-white/15 hover:text-primary-foreground" onClick={() => setOpen(false)}><X className="h-4 w-4" /></Button>
            </div>
          </div>

          <div className="flex-1 space-y-3 overflow-y-auto bg-muted/20 p-4" aria-live="polite">
            {messages.map((message) => (
              <div key={message.id} className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}>
                <div className={`max-w-[90%] ${message.role === "assistant" ? "space-y-1" : ""}`}>
                  <div className={message.role === "user" ? "rounded-2xl rounded-br-md bg-primary px-3.5 py-2.5 text-sm text-primary-foreground" : "whitespace-pre-wrap rounded-2xl rounded-bl-md border bg-background px-3.5 py-2.5 text-sm leading-6 shadow-sm"}>{message.content}</div>
                  {message.meta && <p className="px-1 text-[11px] text-muted-foreground">{message.meta}</p>}
                </div>
              </div>
            ))}
            {chainOfThought.length > 0 && (
              <div className="rounded-xl border bg-background p-2.5 text-sm shadow-sm">
                <button type="button" className="flex w-full items-center gap-1.5 text-xs font-medium text-muted-foreground" onClick={() => setShowChain((v) => !v)}>
                  {showChain ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
                  <BrainCircuit className="h-3.5 w-3.5" />
                  思维链（{chainOfThought.length} 步）
                </button>
                {showChain && (
                  <ol className="mt-2 space-y-1.5 border-l border-border/60 pl-3 text-xs">
                    {chainOfThought.map((entry, index) => (
                      <li key={index} className="relative">
                        <span className={`absolute -left-[13px] top-1 h-1.5 w-1.5 rounded-full ${entry.status === "done" ? "bg-emerald-500" : entry.status === "running" ? "animate-pulse bg-primary" : "bg-amber-400"}`} />
                        <p className="font-medium">{entry.step}</p>
                        {entry.detail && <p className="whitespace-pre-wrap text-[11px] text-muted-foreground">{entry.detail}</p>}
                      </li>
                    ))}
                  </ol>
                )}
              </div>
            )}
            {pendingPlan && (
              <div className="space-y-2 rounded-xl border border-amber-300/70 bg-amber-50/80 p-3 text-sm dark:bg-amber-950/20">
                <div className="font-medium text-amber-950 dark:text-amber-100">深度计划待确认</div>
                <p className="text-xs leading-5 text-amber-900/80 dark:text-amber-100/80">{formatAgentBudget(pendingPlan.budget)}</p>
                <div className="flex gap-2">
                  <Button type="button" size="sm" disabled={busy} onClick={() => { void approvePendingPlan(); }}>确认执行</Button>
                  <Button type="button" size="sm" variant="outline" disabled={busy} onClick={() => { void cancelPendingPlan(); }}>取消计划</Button>
                </div>
              </div>
            )}
            {messages.length === 1 && (
              <div className="flex flex-wrap gap-2 pt-1">
                {quickActions.map((action) => {
                  const Icon = action.icon;
                  return <button key={action.label} type="button" className="inline-flex items-center gap-1.5 rounded-full border bg-background px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:border-primary/40 hover:bg-primary/5 hover:text-primary" onClick={() => { void sendMessage(action.prompt); }}><Icon className="h-3.5 w-3.5" />{action.label}</button>;
                })}
              </div>
            )}
            {(busy || uploading) && <div className="flex items-center gap-2 text-xs text-muted-foreground"><Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />{liveAgentStatus || "Agent 正在处理…"}</div>}
            {!busy && liveAgentStatus && <div className="text-[11px] text-muted-foreground">{liveAgentStatus}</div>}
            <div ref={bottomRef} />
          </div>

          <form className="flex gap-2 border-t bg-background p-3" onSubmit={(event) => { event.preventDefault(); void sendMessage(input); }}>
            <input ref={fileInputRef} type="file" className="hidden" onChange={handleFileUpload} />
            <Button type="button" variant="ghost" size="icon" aria-label="上传资料" title="上传资料" disabled={busy || uploading} onClick={() => fileInputRef.current?.click()}><Paperclip className="h-4 w-4" /></Button>
            <Input ref={inputRef} value={input} onChange={(event) => setInput(event.target.value)} placeholder={agentProfile === "deep" ? "深度模式：先生成计划再执行" : "试试：创建笔记 / 审批笔记 12 / 打开资料"} disabled={busy || uploading} aria-label="输入 Agent 指令" className="h-10" />
            <Button type="submit" size="icon" aria-label="发送" disabled={busy || uploading || !input.trim()}><Send className="h-4 w-4" /></Button>
          </form>
        </section>
      )}

      <div className="relative">
        {!open && <span className="absolute inset-0 animate-ping rounded-full bg-primary/30" aria-hidden="true" />}
        <Button aria-label={open ? "关闭 Agent 助手" : "打开 Agent 助手"} aria-expanded={open} size="icon" className="relative h-14 w-14 rounded-full shadow-lg transition-transform hover:scale-105" onClick={() => setOpen((current) => !current)}>{open ? <X className="h-5 w-5" /> : <Bot className="h-6 w-6" />}</Button>
      </div>
    </div>
  );
}
