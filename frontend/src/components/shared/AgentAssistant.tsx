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
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { agentTaskOptions } from "@/components/constants";
import {
  addProjectMember,
  archiveFile,
  archiveNote,
  approveNote,
  approveAgentPendingAction,
  cancelAgentTurn,
  createAgentTurn,
  createAgentSession,
  createGroup as apiCreateGroup,
  createUser as apiCreateUser,
  disableUser as apiDisableUser,
  extractOcr,
  getGroups as apiGetGroups,
  getProjectFiles,
  getProjectMembers,
  getProjectNotes,
  getProjectRagStatus,
  getUsers as apiGetUsers,
  reindexSearch,
  removeProjectMember,
  reviewFile,
  rejectAgentPendingAction,
  startAgentTurn,
  subscribeAgentSessionEvents,
  searchDocuments as apiSearchDocuments,
  submitNote,
  syncFileToRag,
  updateGroup as apiUpdateGroup,
  updateUser as apiUpdateUser,
  voidNote,
  type AgentGenerationRun,
  type AgentProfile,
  type AgentRuntimeSnapshot,
  type Note,
  type Project,
  type StoredFile,
} from "@/lib/api";
import { getErrorMessage } from "@/lib/utils";
import { useAuthStore, useProjectStore } from "@/stores";

type AgentMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  meta?: string;
};

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

type ParsedFields = Record<string, string>;

const taskAliases: Record<string, string[]> = {
  experiment_summary: ["实验总结", "实验报告", "总结实验", "帮我总结", "总结一下", "实验进展总结"],
  weekly_report: ["周报", "本周进展", "每周报告", "这周进展", "最近进展"],
  stage_report: ["阶段报告", "阶段总结", "项目阶段", "这个阶段"],
  graph_overview: ["图谱概览", "实验过程图谱", "关系图谱", "看看图谱"],
  literature_review: ["文献综述", "文献回顾", "整理文献", "梳理文献"],
  anomaly_detection: ["异常检测", "异常分析", "找异常", "看看异常"],
};

const taskLabels = Object.fromEntries(agentTaskOptions.map((item) => [item.value, item.label]));

const initialMessages: AgentMessage[] = [
  {
    id: "initial",
    role: "assistant",
    content: "你好，我是你的工作区 Agent。只要是当前账号权限范围内的操作，我都可以直接帮你执行。",
  },
];

const fieldAliases: Record<string, string[]> = {
  name: ["名称", "项目名", "项目名称", "群组名", "群组名称"],
  title: ["标题", "笔记标题"],
  description: ["描述", "项目描述"],
  type: ["类型", "实验类型"],
  date: ["日期", "实验日期"],
  content: ["内容", "正文"],
  username: ["用户名", "账号"],
  password: ["密码"],
  display_name: ["显示名", "姓名"],
  role: ["角色"],
  email: ["邮箱", "邮件"],
  comment: ["评论", "意见", "备注"],
  score: ["分数", "评分"],
  questions: ["问题", "问题列表"],
  new_name: ["新名称", "新文件名", "改名为"],
};

function projectIdFromPath(pathname: string): number | null {
  const match = pathname.match(/^\/projects\/(\d+)(?:\/|$)/);
  return match ? Number(match[1]) : null;
}

function cleanValue(value: string): string {
  return value.trim().replace(/^['"“”]|['"“”]$/g, "").replace(/[。！]$/, "").trim();
}

function isAmbiguousReference(value: string): boolean {
  const normalized = cleanValue(value).replace(/\s+/g, "");
  return !normalized || /^(?:这|那|该|当前|刚才|刚刚|它)(?:个|份|条|项|张)?(?:的)?(?:资料|文件|附件|笔记|记录|项目)?$/.test(normalized);
}

function isListIntent(text: string): boolean {
  return /列出|有哪些|都有哪些|查看|看看|看一下|看下|了解一下|都有谁|谁在|谁是|查查|找找/.test(text);
}

function isMemberListIntent(text: string): boolean {
  return isListIntent(text) && /成员|参与者|协作者/.test(text);
}

function isFileListIntent(text: string): boolean {
  return /列出|有哪些|都有哪些|有多少|看看|看一下|看下|查查|找找/.test(text) && /资料|文件|附件/.test(text);
}

function isSearchIntent(text: string): boolean {
  return /^(?:帮我|请|我想|我要)?\s*(?:搜索|检索|查找|搜一下|找一下|查一下|搜搜|查查|找找)/.test(text);
}

function isProjectListIntent(text: string): boolean {
  return isListIntent(text)
    && /项目/.test(text)
    && !/(?:项目)\s*(?:#|ID|编号)?\s*\d+/i.test(text)
    && !/资料|文件|附件|成员|用户|账号|群组|小组/.test(text);
}

function isGroupListIntent(text: string): boolean {
  return isListIntent(text) && /群组|小组/.test(text);
}

function isUserListIntent(text: string): boolean {
  return isListIntent(text) && /用户|账号/.test(text);
}

function isLikelyOperation(text: string): boolean {
  return /^(?:帮我|请|我想|我要|能不能|可以|带我|让我)?\s*(?:把|将)?\s*(?:打开|进入|跳转|前往|去|查看|看看|看一下|看下|了解|处理|整理|归档|同步|审核|重命名|提交|审批|新建|创建|修改|更新|删除|移除|添加|初始化|重建|提取|抽取|上传|禁用|停用)/.test(text);
}

function redactSensitiveText(value: string): string {
  return value.replace(/(密码\s*[=:：]\s*)[^,，;；\s]+/gi, "$1••••••");
}

function parseFields(text: string): ParsedFields {
  const fields: ParsedFields = {};
  const aliases = Object.entries(fieldAliases).flatMap(([key, values]) => values.map((value) => ({ key, value })));
  const pattern = aliases.map(({ value }) => value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|");
  const matcher = new RegExp(`(${pattern})\\s*[=:：]\\s*([^,，;；]+)`, "g");
  for (const match of text.matchAll(matcher)) {
    const alias = match[1];
    const field = aliases.find((item) => item.value === alias)?.key;
    if (field) fields[field] = cleanValue(match[2]);
  }
  return fields;
}

function field(fields: ParsedFields, key: string): string | undefined {
  return fields[key]?.trim() || undefined;
}

function entityId(text: string, words: string[]): number | null {
  const aliases = words.map((word) => word.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|");
  const match = text.match(new RegExp(`(?:${aliases})\\s*(?:#|ID|编号)?\\s*(\\d+)`, "i"));
  return match ? Number(match[1]) : null;
}

function projectFromText(text: string, projects: Project[], fallback: number | null): number | null {
  const id = entityId(text, ["项目", "project"]);
  if (id) return id;
  return projects.find((project) => text.includes(project.name))?.id ?? fallback;
}

function taskTypeFromText(text: string): string | null {
  const task = agentTaskOptions.find((option) =>
    [option.label, ...(taskAliases[option.value] || [])].some((alias) => text.includes(alias)),
  );
  return task?.value || null;
}

function reportSummary(run: AgentGenerationRun): string {
  const statusText: Record<string, string> = {
    completed: "已完成",
    needs_review: "已生成，等待人工复核",
    failed: "生成失败",
  };
  const status = statusText[run.status] || run.status;
  if (!run.body) return `${status}：${run.message || "没有返回内容，请稍后重试。"}`;
  const preview = run.body.length > 900 ? `${run.body.slice(0, 900)}\n\n……报告较长，完整内容已保存到「报告」页面。` : run.body;
  return `${status}：${run.title}\n\n${preview}`;
}

function agentErrorMessage(error: unknown, fallback: string): string {
  const message = getErrorMessage(error, fallback);
  if (/嵌入模型已变更|当前状态不允许此操作|重新初始化资料库/.test(message)) {
    return "当前项目知识库索引状态已失效，暂时无法完成问答。请先初始化资料库并重建搜索索引后再试；本次没有执行写入。";
  }
  if (/403|权限|禁止|forbidden/i.test(message)) {
    return "当前账号没有执行这项操作的权限，后端已拒绝请求；没有产生写入。";
  }
  if (/failed to fetch|network|网络|连接失败/i.test(message)) {
    return "网络连接失败，操作没有完成。请检查服务状态后重试。";
  }
  return message;
}

function navigationTarget(text: string, projectId: number | null): string | null {
  const isNavigation = /^(?:帮我|请|我想|我要|能不能|可以|带我|让我)?\s*(打开(?:一下)?|进入|跳转到|前往|去(?:看看|一下)?|查看(?:一下)?|看(?:看|一下|下)?|切换到)/.test(text);
  if (!isNavigation) return null;
  if (/项目列表|所有项目/.test(text)) return "/projects";
  if (/管理|用户管理|群组|审计/.test(text)) return "/admin";
  if (projectId === null) return null;
  if (/资料|附件|文件|OCR/.test(text)) return `/projects/${projectId}/data`;
  if (/AI|问答|知识库|RAG/.test(text)) return `/projects/${projectId}/ai`;
  if (/图谱|关系/.test(text)) return `/projects/${projectId}/kg`;
  if (/报告|智能体|周报/.test(text)) return `/projects/${projectId}/reports`;
  if (/设置|成员|权限/.test(text)) return `/projects/${projectId}/settings`;
  if (/审批|待审批/.test(text)) return `/projects/${projectId}/approvals`;
  if (/笔记|实验记录/.test(text)) return `/projects/${projectId}`;
  return null;
}

function answerCapabilities(): string {
  return [
    "我可以直接执行当前账号权限范围内的工作：",
    "• 项目：列出、打开、新建、修改项目",
    "• 笔记：新建、编辑、提交、审批、退回、归档、作废",
    "• 资料：上传、重命名、审核、归档、OCR、同步到知识库",
    "• AI：知识库问答、初始化 RAG、重建图谱、搜索索引",
    "• Agent：实验总结、周报、阶段报告、文献综述、异常检测",
    "• 管理：用户、群组、项目成员、权限和审计页面",
    "• 页面：打开项目、笔记、审批、资料、AI、图谱、报告、设置",
    "\n示例：创建笔记：标题=PCR-01，类型=PCR，内容=完成扩增；审批笔记 12；审核通过资料 8；打开图谱。",
  ].join("\n");
}

function formatAgentBudget(budget: Record<string, unknown>): string {
  const seconds = Number(budget.wall_clock_seconds || 0);
  const steps = Number(budget.max_tool_steps || 0);
  const calls = Number(budget.max_model_calls || 0);
  const duration = seconds >= 600 ? `${Math.round(seconds / 60)} 分钟` : `${seconds} 秒`;
  return `${duration} · 最多 ${steps} 个工具步骤 · ${calls} 次模型调用`;
}

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
  const loadProjects = useProjectStore((state) => state.loadProjects);
  const createProject = useProjectStore((state) => state.createProject);
  const updateProject = useProjectStore((state) => state.updateProject);
  const createNote = useProjectStore((state) => state.createNote);
  const updateNote = useProjectStore((state) => state.updateNote);
  const uploadFile = useProjectStore((state) => state.uploadFile);
  const queryRag = useProjectStore((state) => state.queryRag);
  const initRag = useProjectStore((state) => state.initRag);
  const rebuildKg = useProjectStore((state) => state.rebuildKg);
  const extractNoteKg = useProjectStore((state) => state.extractNoteKg);
  const generateAgent = useProjectStore((state) => state.generateAgent);

  const [open, setOpen] = useState(false);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [ragReady, setRagReady] = useState<boolean | null>(null);
  const [messages, setMessages] = useState<AgentMessage[]>(initialMessages);
  const [pendingConfirmation, setPendingConfirmation] = useState<PendingConfirmation | null>(null);
  const [pendingPlan, setPendingPlan] = useState<PendingPlan | null>(null);
  const [agentProfile, setAgentProfile] = useState<AgentProfile>("fast");
  const [liveAgentStatus, setLiveAgentStatus] = useState<string | null>(null);
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

  const resolveNote = async (text: string, projectId: number): Promise<Note | null> => {
    const id = entityId(text, ["笔记", "实验记录", "note"]);
    if (id) return notes.find((note) => note.id === id) || { id } as Note;
    const fields = parseFields(text);
    const query = field(fields, "title") || text.replace(/.*?(?:笔记|实验记录)\s*/, "").trim();
    if (isAmbiguousReference(query)) return null;
    const exact = notes.find((note) => note.title === query);
    if (exact) return exact;
    const localMatches = notes.filter((note) => note.title.includes(query) || query.includes(note.title));
    if (localMatches.length === 1) return localMatches[0];
    const result = await getProjectNotes(token || "", projectId, { search: query, limit: 50 });
    return result.items.length === 1 ? result.items[0] : null;
  };

  const resolveFile = (text: string): StoredFile | null => {
    const id = entityId(text, ["资料", "文件", "附件", "file"]);
    if (id) return files.find((file) => file.id === id) || { id } as StoredFile;
    const query = text
      .replace(/^(?:帮我|请)?\s*(?:把|将)?\s*/i, "")
      .replace(/审核通过|通过审核|拒绝|驳回|审核|归档|同步|重命名|OCR|识别/gi, " ")
      .replace(/资料|文件|附件/gi, " ")
      .replace(/一下(?:子)?|到知识库|进入知识库|提交到知识库/gi, " ")
      .replace(/\s+/g, " ")
      .trim();
    if (isAmbiguousReference(query)) return null;
    const matches = files.filter((file) => file.original_filename.includes(query) || query.includes(file.original_filename));
    return matches.length === 1 ? matches[0] : null;
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
            if (event.event === "tool.started") setLiveAgentStatus(`正在执行：${tool}`);
            else if (event.event === "confirmation.required") setLiveAgentStatus("等待确认高风险操作");
            else if (event.event === "tool.completed") setLiveAgentStatus(`已完成：${tool}`);
            else if (event.event === "turn.completed" || event.event === "turn.cancelled") setLiveAgentStatus(null);
            else if (event.event === "error") setLiveAgentStatus("服务端 Agent 发生错误");
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

      if (/^(你能做什么|你会什么|帮助|能力|help|菜单)/i.test(text)) {
        addMessage({ role: "assistant", content: answerCapabilities() });
        return;
      }

      const requestedProjectId = projectFromText(text, projects, currentProjectId);

      if (isProjectListIntent(text)) {
        if (projects.length === 0) await loadProjects(token, 0, 20);
        const currentProjects = useProjectStore.getState().projects;
        addMessage({
          role: "assistant",
          content: currentProjects.length
            ? currentProjects.map((project) => `#${project.id} ${project.name}（${project.status}）`).join("\n")
            : "当前没有可访问的项目。",
        });
        return;
      }

      if (isMemberListIntent(text)) {
        if (requestedProjectId === null) {
          addMessage({ role: "assistant", content: "请说明要查看哪个项目的成员，例如：看看项目 2 的成员。" });
          return;
        }
        const targetMembers = requestedProjectId === currentProjectId
          ? members
          : await getProjectMembers(token, requestedProjectId);
        addMessage({
          role: "assistant",
          content: targetMembers.length
            ? targetMembers.map((member) => `#${member.user_id} ${member.display_name || "未命名用户"} · ${member.project_role}`).join("\n")
            : requestedProjectId === currentProjectId
              ? "当前项目还没有加载到成员信息。"
              : `项目 #${requestedProjectId} 还没有加载到成员信息。`,
        });
        return;
      }

      if (isFileListIntent(text)) {
        if (requestedProjectId === null) {
          addMessage({ role: "assistant", content: "请说明要查看哪个项目的资料，例如：看看项目 2 的资料。" });
          return;
        }
        const targetFiles = requestedProjectId === currentProjectId
          ? files
          : (await getProjectFiles(token, requestedProjectId)).items;
        addMessage({
          role: "assistant",
          content: targetFiles.length
            ? targetFiles.slice(0, 20).map((file) => `#${file.id} ${file.original_filename} · ${file.status} · ${file.knowledge_sync_status}`).join("\n")
            : "当前项目还没有资料。",
          meta: targetFiles.length > 20 ? `已显示前 20 份资料，共 ${targetFiles.length} 份` : `共 ${targetFiles.length} 份资料`,
        });
        return;
      }

      if (isGroupListIntent(text)) {
        const groups = await apiGetGroups(token);
        addMessage({ role: "assistant", content: groups.length ? groups.map((group) => `#${group.id} ${group.name}${group.description ? ` · ${group.description}` : ""}`).join("\n") : "当前没有群组。" });
        return;
      }

      if (isUserListIntent(text)) {
        const users = await apiGetUsers(token);
        addMessage({ role: "assistant", content: users.items.length ? users.items.slice(0, 30).map((item) => `#${item.id} ${item.display_name} · ${item.username} · ${item.role} · ${item.status}`).join("\n") : "当前没有用户。" });
        return;
      }

      const target = navigationTarget(text, requestedProjectId);
      if (target) {
        router.push(target);
        addMessage({ role: "assistant", content: "好的，正在打开对应页面。" });
        return;
      }

      if (/^(?:帮我)?\s*(打开|进入|前往|切换到|去)\s*项目/.test(text) && requestedProjectId !== null) {
        router.push(`/projects/${requestedProjectId}`);
        addMessage({ role: "assistant", content: `正在打开项目 #${requestedProjectId}。` });
        return;
      }

      if (isSearchIntent(text)) {
        const query = text.replace(/^(?:帮我|请|我想|我要)?\s*(搜索|检索|查找|搜一下|找一下|查一下|搜搜|查查|找找)\s*/, "").replace(/(?:文档|资料|笔记)$/, "").trim();
        if (!query) {
          addMessage({ role: "assistant", content: "请告诉我搜索关键词，例如：搜索资料中的 PCR 引物。" });
          return;
        }
        const results = await apiSearchDocuments(token, query, currentProjectId ?? undefined);
        addMessage({
          role: "assistant",
          content: results.length
            ? results.slice(0, 8).map((result) => `#${result.note_id} ${result.title}\n${result.snippet}`).join("\n\n")
            : "没有找到匹配的笔记或资料。",
          meta: `搜索到 ${results.length} 条结果`,
        });
        return;
      }

      if (/^(?:帮我)?\s*(?:新建|创建)(?:一个)?项目(?:\s*(?:名称|名|为|叫|：|:)|\s*$)/.test(text)) {
        const fields = parseFields(text);
        const tail = text.match(/(?:新建|创建)(?:一个)?项目(?:名称|名)?\s*(?:为|叫|：|:)\s*(.+)$/)?.[1];
        const name = field(fields, "name") || cleanValue(tail?.split(/[,，]/)[0] || "");
        if (!name || /^(项目|一个)$/.test(name)) {
          addMessage({ role: "assistant", content: "请提供项目名称，例如：创建项目：名称=PCR 优化，描述=验证引物条件。" });
          return;
        }
        const project = await createProject(token, { name, description: field(fields, "description") || null });
        addMessage({ role: "assistant", content: `项目「${project.name}」已创建（#${project.id}），正在打开。` });
        router.push(`/projects/${project.id}`);
        return;
      }

      if (/^(?:帮我)?\s*(?:修改|更新|重命名)(?:当前)?项目/.test(text)) {
        const projectId = requestedProjectId;
        const fields = parseFields(text);
        const name = field(fields, "name") || text.match(/(?:改成|改为|叫做)\s*["“]?([^"”]+)["”]?/)?.[1]?.trim();
        const description = field(fields, "description");
        if (!projectId || (!name && description === undefined)) {
          addMessage({ role: "assistant", content: "请提供目标项目和修改内容，例如：把项目 12 改名为 PCR 优化，或修改项目 12：描述=新的实验目标。" });
          return;
        }
        await updateProject(token, projectId, { ...(name ? { name } : {}), ...(description !== undefined ? { description } : {}) });
        addMessage({ role: "assistant", content: `项目 #${projectId} 已更新。` });
        return;
      }

      if (/(新建|创建|记录).*(笔记|实验记录)/.test(text)) {
        const projectId = requestedProjectId;
        if (projectId === null) {
          addMessage({ role: "assistant", content: "请先进入项目，或在指令中写明项目 ID。" });
          return;
        }
        const fields = parseFields(text);
        const title = field(fields, "title") || text.match(/(?:新建|创建|记录)(?:一条)?(?:笔记|实验记录)\s*(?:为|叫|：|:)\s*([^,，]+)/)?.[1]?.trim();
        if (!title) {
          addMessage({ role: "assistant", content: "请提供笔记标题，例如：创建笔记：标题=PCR-01，类型=PCR，内容=完成扩增。" });
          return;
        }
        const note = await createNote(token, {
          project_id: projectId,
          title,
          experiment_type: field(fields, "type") || "通用实验",
          experiment_date: field(fields, "date"),
          fixed_fields_json: {},
          content_json: { text: field(fields, "content") || "" },
        });
        addMessage({ role: "assistant", content: `笔记「${note.title}」已创建（#${note.id}）。` });
        return;
      }

      if (/(修改|更新|编辑).*(笔记|实验记录)/.test(text)) {
        if (currentProjectId === null) { addMessage({ role: "assistant", content: "请先进入项目。" }); return; }
        const note = await resolveNote(text, currentProjectId);
        const fields = parseFields(text);
        if (!note) { addMessage({ role: "assistant", content: "没有找到目标笔记，请使用“修改笔记 12：标题=新标题”。" }); return; }
        const payload = {
          ...(field(fields, "title") ? { title: field(fields, "title") } : {}),
          ...(field(fields, "type") ? { experiment_type: field(fields, "type") } : {}),
          ...(field(fields, "date") ? { experiment_date: field(fields, "date") } : {}),
          ...(field(fields, "content") !== undefined ? { content_json: { text: field(fields, "content") || "" } } : {}),
          change_summary: "通过 Agent 修改",
        };
        if (Object.keys(payload).length === 1) { addMessage({ role: "assistant", content: "请提供要修改的字段，例如：修改笔记 12：标题=新标题，内容=补充记录。" }); return; }
        await updateNote(token, note.id, payload);
        addMessage({ role: "assistant", content: `笔记 #${note.id} 已更新。` });
        return;
      }

      const noteAction = text.match(/(提交|审批通过|通过审批|审批|退回|归档|作废).*(?:笔记|实验记录)/);
      if (noteAction) {
        const projectId = requestedProjectId;
        if (!projectId) {
          addMessage({ role: "assistant", content: "请先进入目标项目，或写明项目 ID。" });
          return;
        }
        const note = await resolveNote(text, projectId);
        if (!note) {
          addMessage({ role: "assistant", content: "没有找到目标笔记。请使用“审批笔记 12”或提供笔记标题。" });
          return;
        }
        const action = noteAction[1];
        const comment = field(parseFields(text), "comment") || "";
        const actionTask = async () => {
          if (action === "提交") { await submitNote(token, note.id); return `笔记 #${note.id} 已提交审核。`; }
          if (action === "审批" || action === "审批通过" || action === "通过审批") { await approveNote(token, note.id, comment); return `笔记 #${note.id} 已审批通过。`; }
          if (action === "退回") { await useProjectStore.getState().returnNote(token, note.id, comment); return `笔记 #${note.id} 已退回。`; }
          if (action === "归档") { await archiveNote(token, note.id); return `笔记 #${note.id} 已归档。`; }
          await voidNote(token, note.id, comment);
          return `笔记 #${note.id} 已作废。`;
        };
        if (action === "归档" || action === "作废") {
          askConfirmation(`确认${action}笔记 #${note.id}？`, actionTask);
        } else {
          addMessage({ role: "assistant", content: await actionTask() });
        }
        return;
      }

      const fileAction = text.match(/(审核通过|通过审核|拒绝|驳回|审核|归档|同步|重命名|OCR|识别)/i);
      const hasFileReference = /资料|文件|附件|\.(?:pdf|txt|docx?|png|jpe?g|csv|xlsx?)\b/i.test(text)
        || files.some((file) => text.includes(file.original_filename));
      if (fileAction && hasFileReference) {
        const file = resolveFile(text);
        if (!file) {
          addMessage({ role: "assistant", content: "没有找到唯一目标资料，请提供资料 ID 或完整文件名。" });
          return;
        }
        const action = fileAction[1].toLowerCase();
        const fields = parseFields(text);
        if (action === "审核") {
          addMessage({ role: "assistant", content: "请明确审核结果：审核通过还是拒绝？" });
        } else if (action === "审核通过" || action === "通过审核" || action === "拒绝" || action === "驳回") {
          const reviewAction = action === "审核通过" || action === "通过审核" ? "approve" : "reject";
          await reviewFile(token, file.id, reviewAction, field(fields, "comment") || "");
          addMessage({ role: "assistant", content: `资料「${file.original_filename}」已${reviewAction === "approve" ? "审核通过" : "拒绝"}。` });
        } else if (action === "归档") {
          askConfirmation(`确认归档资料「${file.original_filename}」？`, async () => {
            await archiveFile(token, file.id);
            return `资料「${file.original_filename}」已归档。`;
          });
        } else if (action === "同步") {
          await syncFileToRag(token, file.id);
          addMessage({ role: "assistant", content: `资料「${file.original_filename}」已提交到 RAG 同步。` });
        } else if (action === "重命名") {
          const newName = field(fields, "new_name");
          if (!newName) {
            addMessage({ role: "assistant", content: "请提供新文件名，例如：重命名资料 8：新文件名=protocol-v2.pdf。" });
            return;
          }
          await useProjectStore.getState().updateFile(token, file.id, newName);
          addMessage({ role: "assistant", content: `资料已重命名为「${newName}」。` });
        } else {
          const result = await extractOcr(token, file.id);
          addMessage({ role: "assistant", content: `已完成资料「${file.original_filename}」的 OCR 提取，共 ${result.character_count} 个字符；请打开资料页校对并确认。` });
        }
        return;
      }

      if (/初始化.*(?:资料库|知识库|RAG)/.test(text)) {
        if (currentProjectId === null) { addMessage({ role: "assistant", content: "请先进入项目。" }); return; }
        await initRag(token, currentProjectId);
        setRagReady(true);
        addMessage({ role: "assistant", content: "当前项目资料库已初始化。" });
        return;
      }

      if (/重建.*(?:图谱|知识图谱)/.test(text)) {
        if (currentProjectId === null) { addMessage({ role: "assistant", content: "请先进入项目。" }); return; }
        await rebuildKg(token, currentProjectId);
        addMessage({ role: "assistant", content: "当前项目知识图谱已重建。" });
        return;
      }

      if (/(提取|抽取).*(?:图谱|知识)/.test(text)) {
        if (currentProjectId === null) { addMessage({ role: "assistant", content: "请先进入项目。" }); return; }
        const note = await resolveNote(text, currentProjectId);
        if (!note) { addMessage({ role: "assistant", content: "请指定要提取的笔记，例如：提取笔记 12 的知识图谱。" }); return; }
        await extractNoteKg(token, note.id);
        addMessage({ role: "assistant", content: `笔记 #${note.id} 的知识图谱已提取。` });
        return;
      }

      if (/重建.*(?:搜索|索引)|重新索引/.test(text)) {
        await reindexSearch(token, currentProjectId === null ? undefined : currentProjectId);
        addMessage({ role: "assistant", content: "搜索索引已重建。" });
        return;
      }

      if (/(新建|创建).*(用户|账号)/.test(text)) {
        const fields = parseFields(text);
        const username = field(fields, "username");
        const password = field(fields, "password");
        const displayName = field(fields, "display_name") || username;
        if (!username || !password || !displayName) {
          addMessage({ role: "assistant", content: "请提供账号信息，例如：创建用户：账号=alice，密码=********，显示名=Alice，角色=member。" });
          return;
        }
        const created = await apiCreateUser(token, {
          username,
          password,
          display_name: displayName,
          role: field(fields, "role") || "member",
        });
        addMessage({ role: "assistant", content: `用户「${created.display_name}」已创建（#${created.id}）。` });
        return;
      }

      if (/(禁用|停用).*(用户|账号)/.test(text)) {
        const id = entityId(text, ["用户", "账号", "user"]);
        if (!id) { addMessage({ role: "assistant", content: "请指定用户 ID，例如：禁用用户 12。" }); return; }
        askConfirmation(`确认禁用用户 #${id}？`, async () => {
          await apiDisableUser(token, id);
          return `用户 #${id} 已禁用。`;
        });
        return;
      }

      if (/(修改|更新).*(用户|账号)/.test(text)) {
        const id = entityId(text, ["用户", "账号", "user"]);
        const fields = parseFields(text);
        if (!id) { addMessage({ role: "assistant", content: "请指定用户 ID，例如：修改用户 12：角色=reviewer。" }); return; }
        const payload = Object.fromEntries(["display_name", "email", "role"].flatMap((key) => field(fields, key) ? [[key, field(fields, key)]] : []));
        if (Object.keys(payload).length === 0) { addMessage({ role: "assistant", content: "请提供要修改的字段，例如：修改用户 12：显示名=新名字，角色=reviewer。" }); return; }
        await apiUpdateUser(token, id, payload);
        addMessage({ role: "assistant", content: `用户 #${id} 已更新。` });
        return;
      }

      if (/(新建|创建).*(群组|小组)/.test(text)) {
        const fields = parseFields(text);
        const name = field(fields, "name") || text.match(/(?:新建|创建)(?:一个)?(?:群组|小组)\s*(?:为|叫|：|:)\s*([^,，]+)/)?.[1]?.trim();
        if (!name) { addMessage({ role: "assistant", content: "请提供群组名称，例如：创建群组：名称=生物实验组，描述=负责细胞实验。" }); return; }
        const group = await apiCreateGroup(token, { name, description: field(fields, "description") });
        addMessage({ role: "assistant", content: `群组「${group.name}」已创建（#${group.id}）。` });
        return;
      }

      if (/(修改|更新).*(群组|小组)/.test(text)) {
        const id = entityId(text, ["群组", "小组", "group"]);
        const fields = parseFields(text);
        if (!id) { addMessage({ role: "assistant", content: "请指定群组 ID，例如：修改群组 3：名称=核心实验组。" }); return; }
        const payload = Object.fromEntries(["name", "description"].flatMap((key) => field(fields, key) !== undefined ? [[key, field(fields, key)]] : []));
        if (Object.keys(payload).length === 0) { addMessage({ role: "assistant", content: "请提供要修改的字段，例如：修改群组 3：描述=新的研究方向。" }); return; }
        await apiUpdateGroup(token, id, payload);
        addMessage({ role: "assistant", content: `群组 #${id} 已更新。` });
        return;
      }

      if (/(添加|加入).*(项目成员|成员)/.test(text)) {
        if (currentProjectId === null) { addMessage({ role: "assistant", content: "请先进入项目。" }); return; }
        const userId = entityId(text, ["用户", "账号", "成员", "user"]);
        if (!userId) { addMessage({ role: "assistant", content: "请指定用户 ID，例如：添加用户 12 为项目成员。" }); return; }
        const fields = parseFields(text);
        const permissionText = `${text} ${field(fields, "role") || ""}`;
        await addProjectMember(token, currentProjectId, {
          user_id: userId,
          project_role: field(fields, "role") || "member",
          can_read: true,
          can_write: /写|编辑/.test(permissionText),
          can_review: /审|审核/.test(permissionText),
          can_evaluate: /评|评价/.test(permissionText),
          can_manage: /管|管理/.test(permissionText),
        });
        addMessage({ role: "assistant", content: `用户 #${userId} 已添加到当前项目。` });
        return;
      }

      if (/(移除|删除).*(项目成员|成员)/.test(text)) {
        if (currentProjectId === null) { addMessage({ role: "assistant", content: "请先进入项目。" }); return; }
        const userId = entityId(text, ["用户", "账号", "成员", "user"]);
        if (!userId) { addMessage({ role: "assistant", content: "请指定用户 ID，例如：移除项目成员 12。" }); return; }
        askConfirmation(`确认移除当前项目成员 #${userId}？`, async () => {
          await removeProjectMember(token, currentProjectId, userId);
          return `项目成员 #${userId} 已移除。`;
        });
        return;
      }

      const taskType = taskTypeFromText(text);
      if (taskType) {
        if (currentProjectId === null) {
          addMessage({ role: "assistant", content: "请先进入一个项目，我才能基于项目数据执行这个 Agent 任务。" });
          return;
        }
        const run = await generateAgent(token, currentProjectId, { task_type: taskType });
        addMessage({ role: "assistant", content: reportSummary(run), meta: `已调用${taskLabels[taskType] || "Agent"} · 可在「报告」页面查看完整内容` });
        return;
      }

      if (isLikelyOperation(text)) {
        addMessage({ role: "assistant", content: "我理解这是一个操作请求，但目标或动作还不够明确。请补充项目、笔记或资料的名称/编号，例如：看看项目成员、打开 AI 问答、归档资料 8。" });
        return;
      }

      if (currentProjectId === null) {
        addMessage({ role: "assistant", content: "我可以操作项目、用户、群组和页面。进入项目后，还可以操作笔记、资料、审批、RAG、图谱和 Agent 报告。" });
        return;
      }
      if (ragReady !== true) {
        addMessage({ role: "assistant", content: ragReady === null ? "我还在读取当前项目的知识库状态，请稍后再试。" : "当前项目资料库还没有初始化。你可以说“初始化资料库”或“打开 AI 问答”。" });
        return;
      }

      const result = await queryRag(token, currentProjectId, text, "auto");
      addMessage({ role: "assistant", content: result.answer, meta: result.sources.length > 0 ? `基于 ${result.sources.length} 条资料证据回答` : "基于当前项目知识库回答" });
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
