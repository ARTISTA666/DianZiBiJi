import type { Note, Project, ProjectMember, StoredFile } from "@/lib/api";

/** 聊天消息：对话区的最小数据单元。 */
export type AgentMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  meta?: string;
};

/** 解析出的字段集合（例如 `名称=PCR 优化` → `{ name: "PCR 优化" }`）。 */
export type ParsedFields = Record<string, string>;

/**
 * 指令执行上下文：组件把只读数据与副作用入口打包后交给指令表。
 * 指令模块只依赖本接口，不感知 React 状态管理细节，便于独立测试与扩展。
 */
export type AgentCommandContext = {
  token: string;
  currentProjectId: number | null;
  projects: Project[];
  notes: Note[];
  files: StoredFile[];
  members: ProjectMember[];
  ragReady: boolean | null;
  setRagReady: (ready: boolean) => void;
  router: { push: (href: string) => void };
  addMessage: (message: Omit<AgentMessage, "id">) => void;
  askConfirmation: (
    description: string,
    action: () => Promise<string>,
    cancel?: () => Promise<void>,
  ) => void;
};
