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
  ChevronUp,
  Minimize2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  ApiRequestError,
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
  actionId?: string;
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
  const [chainOfThought, setChainOfThought] = useState<Array<{ step: string; detail: string; status: string; confirmation?: boolean; actionId?: string }>>([]);
  const [showChain, setShowChain] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [expandedMessageIds, setExpandedMessageIds] = useState<Set<string>>(new Set());
  const messageId = useRef(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const sectionRef = useRef<HTMLElement>(null);
  const toggleButtonRef = useRef<HTMLButtonElement>(null);
  const ragRequestId = useRef(0);
  const serverSessionId = useRef<string | null>(null);
  const eventStreamCleanup = useRef<(() => void) | null>(null);
  const seenEventIds = useRef(new Set<string>());
  const eventStreamTerminal = useRef(false);
  const contextEpoch = useRef(0);
  const confirmationQueue = useRef<PendingConfirmation[]>([]);
  const presentedConfirmation = useRef<PendingConfirmation | null>(null);
  const pendingEventActionIds = useRef(new Set<string>());
  const settledActionIds = useRef(new Set<string>());
  const bottomRef = useRef<HTMLDivElement>(null);

  const toggleExpandMessage = (id: string) => {
    setExpandedMessageIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  // 点击外部区域或按 Escape 自动收起侧栏，防止遮挡底层页面按钮（如“调整阈值”）
  useEffect(() => {
    if (!open) return;
    const handleClickOutside = (event: MouseEvent) => {
      const target = event.target as Node;
      if (
        sectionRef.current &&
        !sectionRef.current.contains(target) &&
        toggleButtonRef.current &&
        !toggleButtonRef.current.contains(target)
      ) {
        setOpen(false);
      }
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [open]);

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
    contextEpoch.current += 1;
    ragRequestId.current += 1;
    setBusy(false);
    setUploading(false);
    setInput("");
    setRagReady(null);
    setMessages(initialMessages);
    setPendingConfirmation(null);
    confirmationQueue.current = [];
    presentedConfirmation.current = null;
    pendingEventActionIds.current.clear();
    settledActionIds.current.clear();
    setPendingPlan(null);
    setAgentProfile("fast");
    setLiveAgentStatus(null);
    setChainOfThought([]);
    eventStreamCleanup.current?.();
    eventStreamCleanup.current = null;
    serverSessionId.current = null;
    seenEventIds.current.clear();
    eventStreamTerminal.current = false;
    return () => {
      contextEpoch.current += 1;
      ragRequestId.current += 1;
      eventStreamCleanup.current?.();
      eventStreamCleanup.current = null;
      serverSessionId.current = null;
    };
  }, [currentProjectId, token, user?.id]);

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

  // Every asynchronous operation owns the project and identity that started it.
  const contextGuard = () => {
    const requestEpoch = contextEpoch.current;
    const userId = user.id;
    return () => requestEpoch === contextEpoch.current
      && useAuthStore.getState().token === token
      && useAuthStore.getState().user?.id === userId
      && (currentProjectId === null || useProjectStore.getState().selectedProjectId === currentProjectId);
  };

  const addMessage = (message: Omit<AgentMessage, "id">) => {
    messageId.current += 1;
    const id = globalThis.crypto.randomUUID();
    setMessages((current) => [...current, { ...message, id }]);
  };

  const showNextConfirmation = () => {
    const next = confirmationQueue.current[0] ?? null;
    if (next === presentedConfirmation.current) return;
    presentedConfirmation.current = next;
    setPendingConfirmation(next);
    if (next) addMessage({ role: "assistant", content: `${next.description}\n\n这是可能改变或不可逆的操作。回复“确认”继续，回复“取消”放弃。` });
  };

  const removeConfirmation = (confirmation: PendingConfirmation) => {
    confirmationQueue.current = confirmationQueue.current.filter((item) => item !== confirmation);
    presentedConfirmation.current = null;
    setPendingConfirmation(null);
  };

  const askConfirmation = (description: string, action: () => Promise<string>, cancel?: () => Promise<void>, actionId?: string) => {
    if (actionId && (settledActionIds.current.has(actionId) || confirmationQueue.current.some((item) => item.actionId === actionId))) return;
    const wasEmpty = confirmationQueue.current.length === 0;
    confirmationQueue.current.push({ description, action, cancel, actionId });
    if (wasEmpty) showNextConfirmation();
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

  const renderAgentTurnResult = (snapshot: AgentRuntimeSnapshot, isCurrent: () => boolean) => {
    if (!isCurrent()) return;
    const assistant = [...snapshot.messages].reverse().find((message) => message.role === "assistant");
    const recentSteps = snapshot.steps.slice(-8);
    addMessage({
      role: "assistant",
      content: assistant?.content || "服务端 Agent 已完成本轮处理。",
      meta: recentSteps.length
        ? recentSteps.map((step) => `${step.tool_name}: ${step.status}`).join(" · ")
        : `${snapshot.session.provider} / ${snapshot.session.model_name}`,
    });
    for (const pending of snapshot.pending_actions.filter((action) => action.status === "pending")) {
      askConfirmation(
        `确认执行 ${pending.tool_name}（${pending.arguments_summary}）？`,
        async () => {
          if (!isCurrent()) return "";
          const approved = await approveAgentPendingAction(token || "", pending.id);
          if (!isCurrent()) return "";
          settledActionIds.current.add(pending.id);
          pendingEventActionIds.current.delete(pending.id);
          setLiveAgentStatus(confirmationQueue.current.length || pendingEventActionIds.current.size ? "等待确认高风险操作" : null);
          return approved.execution_status === "completed"
            ? `${pending.tool_name} 已执行完成。`
            : `${pending.tool_name} 已确认，当前状态：${approved.execution_status}。`;
        },
        async () => {
          if (!isCurrent()) return;
          await rejectAgentPendingAction(token || "", pending.id);
          if (isCurrent()) {
            settledActionIds.current.add(pending.id);
            pendingEventActionIds.current.delete(pending.id);
            setLiveAgentStatus(confirmationQueue.current.length || pendingEventActionIds.current.size ? "等待确认高风险操作" : null);
          }
        },
        pending.id,
      );
    }
  };

  const approvePendingPlan = async () => {
    if (!pendingPlan || !token || !serverSessionId.current) return;
    const isCurrent = contextGuard();
    if (!isCurrent()) return;
    const plan = pendingPlan;
    const sessionId = serverSessionId.current;
    setPendingPlan(null);
    setBusy(true);
    addMessage({ role: "assistant", content: "计划已确认，正在按计划执行…" });
    try {
      const result = await startAgentTurn(token, sessionId, plan.turnId, plan.planHash);
      if (!isCurrent()) return;
      renderAgentTurnResult(result, isCurrent);
    } catch (error) {
      if (!isCurrent()) return;
      setLiveAgentStatus(null);
      const message = error instanceof ApiRequestError && error.status === 409
        ? "计划已变更、已处理或不可用；本次未执行，请重新生成计划。"
        : agentErrorMessage(error, "深度 Agent 执行失败，未自动重试。");
      addMessage({ role: "assistant", content: message });
    } finally {
      if (isCurrent()) setBusy(false);
    }
  };

  const cancelPendingPlan = async () => {
    if (!pendingPlan || !token || !serverSessionId.current) return;
    const isCurrent = contextGuard();
    if (!isCurrent()) return;
    const plan = pendingPlan;
    setPendingPlan(null);
    setBusy(true);
    try {
      await cancelAgentTurn(token, serverSessionId.current, plan.turnId);
      if (!isCurrent()) return;
      addMessage({ role: "assistant", content: "深度计划已取消，未执行任何工具。" });
    } catch (error) {
      if (!isCurrent()) return;
      addMessage({ role: "assistant", content: agentErrorMessage(error, "取消计划失败，请刷新会话确认当前状态。") });
    } finally {
      if (isCurrent()) setBusy(false);
    }
  };

  const sendMessage = async (rawText: string) => {
    const text = rawText.trim();
    if (!text || busy || uploading) return;
    const isCurrent = contextGuard();
    if (!isCurrent()) return;
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
            removeConfirmation(pendingConfirmation);
            addMessage({ role: "assistant", content: "正在执行已确认的操作…" });
            const result = await action();
            if (isCurrent()) {
              addMessage({ role: "assistant", content: result });
              showNextConfirmation();
            }
          } else if (/^(取消|不用|不要|否|no|cancel)$/i.test(text)) {
            removeConfirmation(pendingConfirmation);
            await pendingConfirmation.cancel?.();
            if (!isCurrent()) return;
            addMessage({ role: "assistant", content: "已取消。" });
            showNextConfirmation();
          } else {
            addMessage({ role: "assistant", content: "请回复“确认”或“取消”。" });
          }
          return;
        }
        let sessionId = serverSessionId.current;
        if (!sessionId) {
          const created = await createAgentSession(token, currentProjectId);
          if (!isCurrent()) return;
          sessionId = created.session.id;
          serverSessionId.current = sessionId;
          eventStreamCleanup.current?.();
          seenEventIds.current.clear();
          eventStreamTerminal.current = false;
          eventStreamCleanup.current = subscribeAgentSessionEvents(token, sessionId, (event) => {
            if (!isCurrent() || serverSessionId.current !== sessionId) return;
            if (event.id) {
              if (seenEventIds.current.has(event.id)) return;
              seenEventIds.current.add(event.id);
            }
            if (["turn.started", "plan.preview", "tool.started", "confirmation.required"].includes(event.event)) {
              eventStreamTerminal.current = false;
            }
            const tool = typeof event.data.tool === "string" ? event.data.tool : "工具";
            if (event.event === "plan.preview") {
              const planText = (event.data as { plan?: { text?: unknown } }).plan?.text ?? "";
              const planTextString = typeof planText === "string" ? planText : "";
              setChainOfThought((current) => [...current, { step: "生成研究计划", detail: planTextString.slice(0, 240), status: "done" }]);
            } else if (event.event === "tool.started") {
              setLiveAgentStatus(`正在执行：${tool}`);
              setChainOfThought((current) => [...current, { step: `调用 ${tool}`, detail: String(event.data.arguments_summary ?? ""), status: "running" }]);
            } else if (event.event === "confirmation.required") {
              const result = event.data.result as { structuredContent?: { pending_action_id?: unknown } } | undefined;
              const actionId = event.data.action_id ?? result?.structuredContent?.pending_action_id ?? event.data.id;
              if (typeof actionId === "string" && settledActionIds.current.has(actionId)) return;
              if (typeof actionId === "string") pendingEventActionIds.current.add(actionId);
              setLiveAgentStatus("等待确认高风险操作");
              setChainOfThought((current) => [...current, { step: `高风险操作 ${tool} 等待确认`, detail: "", status: "waiting", confirmation: true, actionId: typeof actionId === "string" ? actionId : undefined }]);
            } else if (event.event === "tool.completed") {
              const alreadyCompleted = event.data.status === "already_completed";
              const detail = alreadyCompleted ? "此前已完成，本次未执行" : "";
              setLiveAgentStatus(alreadyCompleted ? `${tool}：${detail}` : `已完成：${tool}`);
              setChainOfThought((current) => current.map((entry, index) => index === current.length - 1 && entry.status === "running" ? { ...entry, status: "done", detail: detail || entry.detail } : entry));
            } else if (event.event === "tool.failed") {
              setLiveAgentStatus(`执行失败：${tool}`);
              setChainOfThought((current) => current.map((entry, index) => index === current.length - 1 && entry.status === "running" ? { ...entry, status: "failed", detail: "工具执行失败，未确认本次操作成功" } : entry));
            } else if (event.event === "confirmation.rejected" || event.event === "confirmation.expired") {
              eventStreamTerminal.current = event.data.terminal === true;
              if (typeof event.data.action_id === "string") {
                pendingEventActionIds.current.delete(event.data.action_id);
                settledActionIds.current.add(event.data.action_id);
              }
              const wasCurrent = confirmationQueue.current[0]?.actionId === event.data.action_id;
              confirmationQueue.current = confirmationQueue.current.filter((item) => item.actionId !== event.data.action_id);
              if (wasCurrent) showNextConfirmation();
              const expired = event.event === "confirmation.expired";
              setLiveAgentStatus(pendingEventActionIds.current.size || confirmationQueue.current.length ? "等待确认高风险操作" : expired ? "高风险操作已过期，未执行工具" : "高风险操作已取消，未执行工具");
              setChainOfThought((current) => current.map((entry) => entry.confirmation && entry.actionId === event.data.action_id && entry.status === "waiting" ? { ...entry, status: expired ? "failed" : "cancelled", detail: expired ? "确认已过期，未执行工具" : "已拒绝确认，未执行工具" } : entry));
            } else if (event.event === "confirmation.completed") {
              eventStreamTerminal.current = event.data.terminal === true;
              if (typeof event.data.action_id === "string") {
                pendingEventActionIds.current.delete(event.data.action_id);
                settledActionIds.current.add(event.data.action_id);
              }
              const wasCurrent = confirmationQueue.current[0]?.actionId === event.data.action_id;
              confirmationQueue.current = confirmationQueue.current.filter((item) => item.actionId !== event.data.action_id);
              if (wasCurrent) showNextConfirmation();
              const detail = event.data.replayed === true ? "此前已完成，本次未执行" : "已确认执行完成";
              setLiveAgentStatus(pendingEventActionIds.current.size || confirmationQueue.current.length ? "等待确认高风险操作" : detail);
              setChainOfThought((current) => current.map((entry) => entry.confirmation && entry.actionId === event.data.action_id && entry.status === "waiting" ? { ...entry, status: "done", detail } : entry));
            } else if (event.event === "turn.completed" || event.event === "turn.cancelled") {
              eventStreamTerminal.current = event.event === "turn.cancelled" || event.data.terminal === true;
              setLiveAgentStatus(null);
              setChainOfThought((current) => current.map((entry) => entry.status === "running" ? { ...entry, status: "waiting", detail: event.event === "turn.cancelled" ? "本轮已取消，执行结果请查会话记录" : "未收到工具完成结果，请查会话记录" } : entry));
            } else if (event.event === "error") {
              eventStreamTerminal.current = true;
              setLiveAgentStatus("服务端 Agent 发生错误");
              setChainOfThought((current) => current.map((entry) => entry.status === "running" ? { ...entry, status: "failed", detail: "本轮发生错误，工具执行结果请查会话记录" } : entry));
            }
          }, () => {
            if (isCurrent() && serverSessionId.current === sessionId && !eventStreamTerminal.current) {
              setLiveAgentStatus((current) => ["高风险操作已取消，未执行工具", "高风险操作已过期，未执行工具", "此前已完成，本次未执行", "已确认执行完成"].includes(current || "")
                ? current : "事件连接中断，正在重连；操作不会自动重试");
            }
          });
        }
        const response = await createAgentTurn(token, sessionId, text, agentProfile);
        if (!isCurrent()) return;
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
        renderAgentTurnResult(response, isCurrent);
        return;
      }

      if (pendingConfirmation) {
        if (/^(确认|确定|是|执行|继续|好|好的|yes|ok)$/i.test(text)) {
          const action = pendingConfirmation.action;
          removeConfirmation(pendingConfirmation);
          addMessage({ role: "assistant", content: "正在执行已确认的操作…" });
          const result = await action();
          if (isCurrent()) {
            addMessage({ role: "assistant", content: result });
            showNextConfirmation();
          }
        } else if (/^(取消|不用|不要|否|no|cancel)$/i.test(text)) {
          removeConfirmation(pendingConfirmation);
          addMessage({ role: "assistant", content: "已取消。" });
          showNextConfirmation();
        } else {
          addMessage({ role: "assistant", content: `请确认是否${pendingConfirmation.description.split("\n")[0]}。回复“确认”或“取消”。` });
        }
        return;
      }

      await runAgentCommands({
        ...commandContext,
        router: { ...router, push: (...args) => { if (isCurrent()) router.push(...args); } },
        addMessage: (message) => { if (isCurrent()) addMessage(message); },
        setRagReady: (ready) => { if (isCurrent()) setRagReady(ready); },
        askConfirmation: (description, action, cancel) => {
          if (isCurrent()) askConfirmation(description,
            async () => isCurrent() ? action() : "",
            async () => { if (isCurrent()) await cancel?.(); });
        },
      }, text);
    } catch (error) {
      if (!isCurrent()) return;
      const settled = Boolean(pendingConfirmation?.actionId && settledActionIds.current.has(pendingConfirmation.actionId));
      const retryable = pendingConfirmation?.actionId && !settled
        && (!(error instanceof ApiRequestError) || error.status >= 500 || error.status === 408 || error.status === 429);
      if (retryable && !confirmationQueue.current.some((item) => item.actionId === pendingConfirmation.actionId)) {
        confirmationQueue.current.unshift(pendingConfirmation);
      }
      if (pendingConfirmation?.actionId && !retryable) {
        pendingEventActionIds.current.delete(pendingConfirmation.actionId);
        settledActionIds.current.add(pendingConfirmation.actionId);
      }
      const message = settled
        ? "该操作已由服务端处理，结果以会话记录为准；没有自动再次提交。"
        : retryable
          ? `${agentErrorMessage(error, "请求响应失败。")}\n请求结果尚未确认；请回复“确认”或“取消”手动重试。系统不会自动再次提交。`
          : pendingConfirmation && error instanceof ApiRequestError && error.status === 409
            ? "确认已过期、已处理或不可用；本次确认未成功，请查看会话记录。"
            : agentErrorMessage(error, "Agent 执行失败，请稍后重试。");
      setLiveAgentStatus(confirmationQueue.current.length || pendingEventActionIds.current.size ? "等待确认高风险操作" : null);
      setChainOfThought((current) => current.map((entry) => !settled && entry.confirmation && entry.actionId === pendingConfirmation?.actionId && entry.status === "waiting"
        ? { ...entry, status: retryable ? "waiting" : "failed", detail: retryable ? "请求结果尚未确认，等待手动重试" : message } : entry));
      addMessage({ role: "assistant", content: message });
      if (pendingConfirmation) showNextConfirmation();
    } finally {
      if (isCurrent()) setBusy(false);
    }
  };

  const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file || !token) return;
    const isCurrent = contextGuard();
    if (!isCurrent()) return;
    if (currentProjectId === null) {
      addMessage({ role: "assistant", content: "请先进入项目，再上传资料。" });
      return;
    }
    setUploading(true);
    try {
      const uploaded = await uploadFile(token, currentProjectId, file);
      if (!isCurrent()) return;
      addMessage({ role: "assistant", content: `资料「${uploaded.original_filename}」已上传。后续可以说“审核通过资料 ${uploaded.id}”或“同步资料 ${uploaded.id}”。` });
    } catch (error) {
      if (!isCurrent()) return;
      addMessage({ role: "assistant", content: agentErrorMessage(error, "资料上传失败，请稍后重试。") });
    } finally {
      if (isCurrent()) setUploading(false);
    }
  };

  return (
    <div className="fixed bottom-5 right-5 z-[60] flex flex-col items-end gap-3">
      {open && (
        <section ref={sectionRef} aria-label="Agent 助手" className="flex h-[min(680px,calc(100vh-7rem))] w-[min(430px,calc(100vw-2rem))] flex-col overflow-hidden rounded-2xl border bg-background shadow-2xl ring-1 ring-black/5 animate-in fade-in slide-in-from-bottom-2 duration-200">
          <div className="flex items-center justify-between bg-primary px-4 py-3 text-primary-foreground">
            <div className="flex items-center gap-3">
              <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-white/15"><Bot className="h-5 w-5" /></div>
              <div>
                <p className="text-sm font-semibold">Agent 助手</p>
                <p className="text-xs text-primary-foreground/75">{currentProject?.name || "跨项目工作区"}</p>
              </div>
            </div>
            <div className="flex items-center gap-1.5">
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
              <Button aria-label="收起 Agent 浮层" variant="ghost" size="icon" className="h-8 w-8 text-primary-foreground hover:bg-white/15 hover:text-primary-foreground" title="一键收起（点击外部亦可收起）" onClick={() => setOpen(false)}><Minimize2 className="h-4 w-4" /></Button>
              <Button aria-label="关闭 Agent" variant="ghost" size="icon" className="h-8 w-8 text-primary-foreground hover:bg-white/15 hover:text-primary-foreground" title="关闭" onClick={() => setOpen(false)}><X className="h-4 w-4" /></Button>
            </div>
          </div>

          <div className="flex-1 space-y-3 overflow-y-auto bg-muted/20 p-4" aria-live="polite">
            {messages.map((message) => {
              const isAssistant = message.role === "assistant";
              const isLong = isAssistant && message.content.length > 180;
              const isExpanded = expandedMessageIds.has(message.id);
              const displayContent = isLong && !isExpanded
                ? message.content.slice(0, 140) + "…"
                : message.content;

              return (
                <div key={message.id} className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}>
                  <div className={`max-w-[90%] ${isAssistant ? "space-y-1" : ""}`}>
                    <div className={message.role === "user" ? "rounded-2xl rounded-br-md bg-primary px-3.5 py-2.5 text-sm text-primary-foreground" : "whitespace-pre-wrap rounded-2xl rounded-bl-md border bg-background px-3.5 py-2.5 text-sm leading-6 shadow-sm"}>
                      {displayContent}
                      {isLong && (
                        <div className="mt-1.5 pt-1.5 border-t border-border/40 flex justify-end">
                          <button
                            type="button"
                            onClick={() => toggleExpandMessage(message.id)}
                            className="inline-flex items-center gap-1 text-[11px] font-medium text-primary hover:underline cursor-pointer"
                          >
                            {isExpanded ? (
                              <>
                                <ChevronUp className="h-3 w-3" />
                                收起全文
                              </>
                            ) : (
                              <>
                                <ChevronDown className="h-3 w-3" />
                                展开全文 ({message.content.length} 字)
                              </>
                            )}
                          </button>
                        </div>
                      )}
                    </div>
                    {message.meta && <p className="px-1 text-[11px] text-muted-foreground">{message.meta}</p>}
                  </div>
                </div>
              );
            })}
            {chainOfThought.length > 0 && (
              <div className="rounded-xl border bg-background p-2.5 text-sm shadow-sm">
                <button type="button" className="flex w-full items-center gap-1.5 text-xs font-medium text-muted-foreground" onClick={() => setShowChain((v) => !v)}>
                  {showChain ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
                  <BrainCircuit className="h-3.5 w-3.5" />
                  执行轨迹（{chainOfThought.length} 步）
                </button>
                {showChain && (
                  <ol className="mt-2 space-y-1.5 border-l border-border/60 pl-3 text-xs">
                    {chainOfThought.map((entry, index) => (
                      <li key={index} className="relative">
                        <span className={`absolute -left-[13px] top-1 h-1.5 w-1.5 rounded-full ${entry.status === "done" ? "bg-emerald-500" : entry.status === "failed" ? "bg-rose-500" : entry.status === "running" ? "animate-pulse bg-primary" : "bg-amber-400"}`} />
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
        <Button ref={toggleButtonRef} aria-label={open ? "关闭 Agent 助手" : "打开 Agent 助手"} aria-expanded={open} size="icon" className="relative h-14 w-14 rounded-full shadow-lg transition-transform hover:scale-105" onClick={() => setOpen((current) => !current)}>{open ? <X className="h-5 w-5" /> : <Bot className="h-6 w-6" />}</Button>
      </div>
    </div>
  );
}
