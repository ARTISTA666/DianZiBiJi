import { agentTaskOptions } from "@/components/constants";
import type { AgentGenerationRun, Project } from "@/lib/api";
import { getErrorMessage } from "@/lib/utils";

import type { AgentMessage, ParsedFields } from "./types";

/** 任务别名：把自然语言说法映射到服务端任务类型。 */
export const taskAliases: Record<string, string[]> = {
  experiment_summary: ["实验总结", "实验报告", "总结实验", "帮我总结", "总结一下", "实验进展总结"],
  weekly_report: ["周报", "本周进展", "每周报告", "这周进展", "最近进展"],
  stage_report: ["阶段报告", "阶段总结", "项目阶段", "这个阶段"],
  graph_overview: ["图谱概览", "实验过程图谱", "关系图谱", "看看图谱"],
  literature_review: ["文献综述", "文献回顾", "整理文献", "梳理文献"],
  anomaly_detection: ["异常检测", "异常分析", "找异常", "看看异常"],
};

export const taskLabels = Object.fromEntries(agentTaskOptions.map((item) => [item.value, item.label]));

export const initialMessages: AgentMessage[] = [
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

/** 从路由路径提取项目 ID（`/projects/12/...` → 12）。 */
export function projectIdFromPath(pathname: string): number | null {
  const match = pathname.match(/^\/projects\/(\d+)(?:\/|$)/);
  return match ? Number(match[1]) : null;
}

export function cleanValue(value: string): string {
  return value.trim().replace(/^['"“”]|['"“”]$/g, "").replace(/[。！]$/, "").trim();
}

export function isAmbiguousReference(value: string): boolean {
  const normalized = cleanValue(value).replace(/\s+/g, "");
  return !normalized || /^(?:这|那|该|当前|刚才|刚刚|它)(?:个|份|条|项|张)?(?:的)?(?:资料|文件|附件|笔记|记录|项目)?$/.test(normalized);
}

export function isListIntent(text: string): boolean {
  return /列出|有哪些|都有哪些|查看|看看|看一下|看下|了解一下|都有谁|谁在|谁是|查查|找找/.test(text);
}

export function isMemberListIntent(text: string): boolean {
  return isListIntent(text) && /成员|参与者|协作者/.test(text);
}

export function isFileListIntent(text: string): boolean {
  return /列出|有哪些|都有哪些|有多少|看看|看一下|看下|查查|找找/.test(text) && /资料|文件|附件/.test(text);
}

export function isSearchIntent(text: string): boolean {
  return /^(?:帮我|请|我想|我要)?\s*(?:搜索|检索|查找|搜一下|找一下|查一下|搜搜|查查|找找)/.test(text);
}

export function isProjectListIntent(text: string): boolean {
  return isListIntent(text)
    && /项目/.test(text)
    && !/(?:项目)\s*(?:#|ID|编号)?\s*\d+/i.test(text)
    && !/资料|文件|附件|成员|用户|账号|群组|小组/.test(text);
}

export function isGroupListIntent(text: string): boolean {
  return isListIntent(text) && /群组|小组/.test(text);
}

export function isUserListIntent(text: string): boolean {
  return isListIntent(text) && /用户|账号/.test(text);
}

export function isLikelyOperation(text: string): boolean {
  return /^(?:帮我|请|我想|我要|能不能|可以|带我|让我)?\s*(?:把|将)?\s*(?:打开|进入|跳转|前往|去|查看|看看|看一下|看下|了解|处理|整理|归档|同步|审核|重命名|提交|审批|新建|创建|修改|更新|删除|移除|添加|初始化|重建|提取|抽取|上传|禁用|停用)/.test(text);
}

export function redactSensitiveText(value: string): string {
  return value.replace(/(密码\s*[=:：]\s*)[^,，;；\s]+/gi, "$1••••••");
}

export function parseFields(text: string): ParsedFields {
  const fields: ParsedFields = {};
  const aliases = Object.entries(fieldAliases).flatMap(([key, values]) => values.map((value) => ({ key, value })));
  const pattern = aliases.map(({ value }) => value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|");
  const matcher = new RegExp(`(${pattern})\\s*[=:：]\\s*([^,，;；]+)`, "g");
  for (const match of text.matchAll(matcher)) {
    const alias = match[1];
    const fieldKey = aliases.find((item) => item.value === alias)?.key;
    if (fieldKey) fields[fieldKey] = cleanValue(match[2]);
  }
  return fields;
}

export function field(fields: ParsedFields, key: string): string | undefined {
  return fields[key]?.trim() || undefined;
}

export function entityId(text: string, words: string[]): number | null {
  const aliases = words.map((word) => word.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|");
  const match = text.match(new RegExp(`(?:${aliases})\\s*(?:#|ID|编号)?\\s*(\\d+)`, "i"));
  return match ? Number(match[1]) : null;
}

export function projectFromText(text: string, projects: Project[], fallback: number | null): number | null {
  const id = entityId(text, ["项目", "project"]);
  if (id) return id;
  return projects.find((project) => text.includes(project.name))?.id ?? fallback;
}

export function taskTypeFromText(text: string): string | null {
  const task = agentTaskOptions.find((option) =>
    [option.label, ...(taskAliases[option.value] || [])].some((alias) => text.includes(alias)),
  );
  return task?.value || null;
}

export function reportSummary(run: AgentGenerationRun): string {
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

export function agentErrorMessage(error: unknown, fallback: string): string {
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

export function navigationTarget(text: string, projectId: number | null): string | null {
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

export function answerCapabilities(): string {
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

export function formatAgentBudget(budget: Record<string, unknown>): string {
  const seconds = Number(budget.wall_clock_seconds || 0);
  const steps = Number(budget.max_tool_steps || 0);
  const calls = Number(budget.max_model_calls || 0);
  const duration = seconds >= 600 ? `${Math.round(seconds / 60)} 分钟` : `${seconds} 秒`;
  return `${duration} · 最多 ${steps} 个工具步骤 · ${calls} 次模型调用`;
}
