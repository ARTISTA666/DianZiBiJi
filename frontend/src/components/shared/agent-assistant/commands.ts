import {
  addProjectMember,
  approveNote,
  archiveFile,
  archiveNote,
  createGroup as apiCreateGroup,
  createUser as apiCreateUser,
  disableUser as apiDisableUser,
  extractOcr,
  getGroups as apiGetGroups,
  getProjectFiles,
  getProjectMembers,
  getProjectNotes,
  getUsers as apiGetUsers,
  reindexSearch,
  removeProjectMember,
  reviewFile,
  searchDocuments as apiSearchDocuments,
  submitNote,
  syncFileToRag,
  updateGroup as apiUpdateGroup,
  updateUser as apiUpdateUser,
  voidNote,
  type Note,
  type StoredFile,
} from "@/lib/api";
import { useProjectStore } from "@/stores";

import {
  answerCapabilities,
  cleanValue,
  entityId,
  field,
  isAmbiguousReference,
  isFileListIntent,
  isGroupListIntent,
  isLikelyOperation,
  isMemberListIntent,
  isProjectListIntent,
  isSearchIntent,
  isUserListIntent,
  navigationTarget,
  parseFields,
  projectFromText,
  reportSummary,
  taskLabels,
  taskTypeFromText,
} from "./intents";
import type { AgentCommandContext, AgentMessage, ParsedFields } from "./types";

/** 单条本地指令：`match` 命中后执行 `run`，按注册顺序优先匹配。 */
type AgentCommand = {
  match: (text: string, ctx: AgentCommandContext) => boolean;
  run: (ctx: AgentCommandContext, text: string) => Promise<void>;
};

/** 追加一条助手消息。 */
function say(ctx: AgentCommandContext, content: string, meta?: string) {
  ctx.addMessage({ role: "assistant", content, meta });
}

/** 目标项目 ID：显式编号 > 名称匹配 > 当前项目。 */
function requestedProject(ctx: AgentCommandContext, text: string): number | null {
  return projectFromText(text, ctx.projects, ctx.currentProjectId);
}

/** 从解析字段中挑选出现的键，构造 API 更新载荷。 */
function pickFields(fields: ParsedFields, keys: string[]): Record<string, unknown> {
  return Object.fromEntries(
    keys.flatMap((key) => (field(fields, key) !== undefined ? [[key, field(fields, key)]] : [])),
  );
}

async function resolveNote(ctx: AgentCommandContext, text: string, projectId: number): Promise<Note | null> {
  const id = entityId(text, ["笔记", "实验记录", "note"]);
  if (id) return ctx.notes.find((note) => note.id === id) || ({ id } as Note);
  const fields = parseFields(text);
  const query = field(fields, "title") || text.replace(/.*?(?:笔记|实验记录)\s*/, "").trim();
  if (isAmbiguousReference(query)) return null;
  const exact = ctx.notes.find((note) => note.title === query);
  if (exact) return exact;
  const localMatches = ctx.notes.filter((note) => note.title.includes(query) || query.includes(note.title));
  if (localMatches.length === 1) return localMatches[0];
  const result = await getProjectNotes(ctx.token, projectId, { search: query, limit: 50 });
  return result.items.length === 1 ? result.items[0] : null;
}

function resolveFile(ctx: AgentCommandContext, text: string): StoredFile | null {
  const id = entityId(text, ["资料", "文件", "附件", "file"]);
  if (id) return ctx.files.find((file) => file.id === id) || ({ id } as StoredFile);
  const query = text
    .replace(/^(?:帮我|请)?\s*(?:把|将)?\s*/i, "")
    .replace(/审核通过|通过审核|拒绝|驳回|审核|归档|同步|重命名|OCR|识别/gi, " ")
    .replace(/资料|文件|附件/gi, " ")
    .replace(/一下(?:子)?|到知识库|进入知识库|提交到知识库/gi, " ")
    .replace(/\s+/g, " ")
    .trim();
  if (isAmbiguousReference(query)) return null;
  const matches = ctx.files.filter((file) => file.original_filename.includes(query) || query.includes(file.original_filename));
  return matches.length === 1 ? matches[0] : null;
}

/** 发起一次高危操作确认（确认提示消息由 askConfirmation 统一追加）。 */
function sayConfirmation(ctx: AgentCommandContext, description: string, action: () => Promise<string>) {
  ctx.askConfirmation(description, action);
}

/**
 * 本地指令表：行为与旧的 if/else 链完全一致，顺序即优先级。
 * 新增指令只需追加一条记录，无需改动组件代码。
 */
const commands: AgentCommand[] = [
  {
    match: (text) => /^(你能做什么|你会什么|帮助|能力|help|菜单)/i.test(text),
    run: async (ctx) => say(ctx, answerCapabilities()),
  },
  {
    match: isProjectListIntent,
    run: async (ctx) => {
      if (ctx.projects.length === 0) await useProjectStore.getState().loadProjects(ctx.token, 0, 20);
      const currentProjects = useProjectStore.getState().projects;
      say(
        ctx,
        currentProjects.length
          ? currentProjects.map((project) => `#${project.id} ${project.name}（${project.status}）`).join("\n")
          : "当前没有可访问的项目。",
      );
    },
  },
  {
    match: isMemberListIntent,
    run: async (ctx, text) => {
      const projectId = requestedProject(ctx, text);
      if (projectId === null) {
        say(ctx, "请说明要查看哪个项目的成员，例如：看看项目 2 的成员。");
        return;
      }
      const targetMembers = projectId === ctx.currentProjectId
        ? ctx.members
        : await getProjectMembers(ctx.token, projectId);
      say(
        ctx,
        targetMembers.length
          ? targetMembers.map((member) => `#${member.user_id} ${member.display_name || "未命名用户"} · ${member.project_role}`).join("\n")
          : projectId === ctx.currentProjectId
            ? "当前项目还没有加载到成员信息。"
            : `项目 #${projectId} 还没有加载到成员信息。`,
      );
    },
  },
  {
    match: isFileListIntent,
    run: async (ctx, text) => {
      const projectId = requestedProject(ctx, text);
      if (projectId === null) {
        say(ctx, "请说明要查看哪个项目的资料，例如：看看项目 2 的资料。");
        return;
      }
      const targetFiles = projectId === ctx.currentProjectId
        ? ctx.files
        : (await getProjectFiles(ctx.token, projectId)).items;
      say(
        ctx,
        targetFiles.length
          ? targetFiles.slice(0, 20).map((file) => `#${file.id} ${file.original_filename} · ${file.status} · ${file.knowledge_sync_status}`).join("\n")
          : "当前项目还没有资料。",
        targetFiles.length > 20 ? `已显示前 20 份资料，共 ${targetFiles.length} 份` : `共 ${targetFiles.length} 份资料`,
      );
    },
  },
  {
    match: isGroupListIntent,
    run: async (ctx) => {
      const groups = await apiGetGroups(ctx.token);
      say(ctx, groups.length ? groups.map((group) => `#${group.id} ${group.name}${group.description ? ` · ${group.description}` : ""}`).join("\n") : "当前没有群组。");
    },
  },
  {
    match: isUserListIntent,
    run: async (ctx) => {
      const users = await apiGetUsers(ctx.token);
      say(ctx, users.items.length ? users.items.slice(0, 30).map((item) => `#${item.id} ${item.display_name} · ${item.username} · ${item.role} · ${item.status}`).join("\n") : "当前没有用户。");
    },
  },
  {
    match: (text, ctx) => navigationTarget(text, requestedProject(ctx, text)) !== null,
    run: async (ctx, text) => {
      const target = navigationTarget(text, requestedProject(ctx, text));
      if (target) {
        ctx.router.push(target);
        say(ctx, "好的，正在打开对应页面。");
      }
    },
  },
  {
    match: (text, ctx) => /^(?:帮我)?\s*(打开|进入|前往|切换到|去)\s*项目/.test(text) && requestedProject(ctx, text) !== null,
    run: async (ctx, text) => {
      const projectId = requestedProject(ctx, text);
      if (projectId !== null) {
        ctx.router.push(`/projects/${projectId}`);
        say(ctx, `正在打开项目 #${projectId}。`);
      }
    },
  },
  {
    match: isSearchIntent,
    run: async (ctx, text) => {
      const query = text.replace(/^(?:帮我|请|我想|我要)?\s*(搜索|检索|查找|搜一下|找一下|查一下|搜搜|查查|找找)\s*/, "").replace(/(?:文档|资料|笔记)$/, "").trim();
      if (!query) {
        say(ctx, "请告诉我搜索关键词，例如：搜索资料中的 PCR 引物。");
        return;
      }
      const results = await apiSearchDocuments(ctx.token, query, ctx.currentProjectId ?? undefined);
      say(
        ctx,
        results.length
          ? results.slice(0, 8).map((result) => `#${result.note_id} ${result.title}\n${result.snippet}`).join("\n\n")
          : "没有找到匹配的笔记或资料。",
        `搜索到 ${results.length} 条结果`,
      );
    },
  },
  {
    match: (text) => /^(?:帮我)?\s*(?:新建|创建)(?:一个)?项目(?:\s*(?:名称|名|为|叫|：|:)|\s*$)/.test(text),
    run: async (ctx, text) => {
      const fields = parseFields(text);
      const tail = text.match(/(?:新建|创建)(?:一个)?项目(?:名称|名)?\s*(?:为|叫|：|:)\s*(.+)$/)?.[1];
      const name = field(fields, "name") || cleanValue(tail?.split(/[,，]/)[0] || "");
      if (!name || /^(项目|一个)$/.test(name)) {
        say(ctx, "请提供项目名称，例如：创建项目：名称=PCR 优化，描述=验证引物条件。");
        return;
      }
      const project = await useProjectStore.getState().createProject(ctx.token, { name, description: field(fields, "description") || null });
      say(ctx, `项目「${project.name}」已创建（#${project.id}），正在打开。`);
      ctx.router.push(`/projects/${project.id}`);
    },
  },
  {
    match: (text) => /^(?:帮我)?\s*(?:修改|更新|重命名)(?:当前)?项目/.test(text),
    run: async (ctx, text) => {
      const projectId = requestedProject(ctx, text);
      const fields = parseFields(text);
      const name = field(fields, "name") || text.match(/(?:改成|改为|叫做)\s*["“]?([^"”]+)["”]?/)?.[1]?.trim();
      const description = field(fields, "description");
      if (!projectId || (!name && description === undefined)) {
        say(ctx, "请提供目标项目和修改内容，例如：把项目 12 改名为 PCR 优化，或修改项目 12：描述=新的实验目标。");
        return;
      }
      await useProjectStore.getState().updateProject(ctx.token, projectId, { ...(name ? { name } : {}), ...(description !== undefined ? { description } : {}) });
      say(ctx, `项目 #${projectId} 已更新。`);
    },
  },
  {
    match: (text) => /(新建|创建|记录).*(笔记|实验记录)/.test(text),
    run: async (ctx, text) => {
      const projectId = requestedProject(ctx, text);
      if (projectId === null) {
        say(ctx, "请先进入项目，或在指令中写明项目 ID。");
        return;
      }
      const fields = parseFields(text);
      const title = field(fields, "title") || text.match(/(?:新建|创建|记录)(?:一条)?(?:笔记|实验记录)\s*(?:为|叫|：|:)\s*([^,，]+)/)?.[1]?.trim();
      if (!title) {
        say(ctx, "请提供笔记标题，例如：创建笔记：标题=PCR-01，类型=PCR，内容=完成扩增。");
        return;
      }
      const note = await useProjectStore.getState().createNote(ctx.token, {
        project_id: projectId,
        title,
        experiment_type: field(fields, "type") || "通用实验",
        experiment_date: field(fields, "date"),
        fixed_fields_json: {},
        content_json: { text: field(fields, "content") || "" },
      });
      say(ctx, `笔记「${note.title}」已创建（#${note.id}）。`);
    },
  },
  {
    match: (text) => /(修改|更新|编辑).*(笔记|实验记录)/.test(text),
    run: async (ctx, text) => {
      if (ctx.currentProjectId === null) { say(ctx, "请先进入项目。"); return; }
      const note = await resolveNote(ctx, text, ctx.currentProjectId);
      const fields = parseFields(text);
      if (!note) { say(ctx, "没有找到目标笔记，请使用“修改笔记 12：标题=新标题”。"); return; }
      const payload = {
        ...(field(fields, "title") ? { title: field(fields, "title") } : {}),
        ...(field(fields, "type") ? { experiment_type: field(fields, "type") } : {}),
        ...(field(fields, "date") ? { experiment_date: field(fields, "date") } : {}),
        ...(field(fields, "content") !== undefined ? { content_json: { text: field(fields, "content") || "" } } : {}),
        change_summary: "通过 Agent 修改",
      };
      if (Object.keys(payload).length === 1) { say(ctx, "请提供要修改的字段，例如：修改笔记 12：标题=新标题，内容=补充记录。"); return; }
      await useProjectStore.getState().updateNote(ctx.token, note.id, payload);
      say(ctx, `笔记 #${note.id} 已更新。`);
    },
  },
  {
    match: (text) => /(提交|审批通过|通过审批|审批|退回|归档|作废).*(?:笔记|实验记录)/.test(text),
    run: async (ctx, text) => {
      const projectId = requestedProject(ctx, text);
      if (!projectId) {
        say(ctx, "请先进入目标项目，或写明项目 ID。");
        return;
      }
      const note = await resolveNote(ctx, text, projectId);
      if (!note) {
        say(ctx, "没有找到目标笔记。请使用“审批笔记 12”或提供笔记标题。");
        return;
      }
      const action = text.match(/(提交|审批通过|通过审批|审批|退回|归档|作废)/)?.[1] ?? "";
      const comment = field(parseFields(text), "comment") || "";
      const actionTask = async () => {
        if (action === "提交") { await submitNote(ctx.token, note.id); return `笔记 #${note.id} 已提交审核。`; }
        if (action === "审批" || action === "审批通过" || action === "通过审批") { await approveNote(ctx.token, note.id, comment); return `笔记 #${note.id} 已审批通过。`; }
        if (action === "退回") { await useProjectStore.getState().returnNote(ctx.token, note.id, comment); return `笔记 #${note.id} 已退回。`; }
        if (action === "归档") { await archiveNote(ctx.token, note.id); return `笔记 #${note.id} 已归档。`; }
        await voidNote(ctx.token, note.id, comment);
        return `笔记 #${note.id} 已作废。`;
      };
      if (action === "归档" || action === "作废") {
        sayConfirmation(ctx, `确认${action}笔记 #${note.id}？`, actionTask);
      } else {
        say(ctx, await actionTask());
      }
    },
  },
  {
    match: (text, ctx) => {
      const fileAction = text.match(/(审核通过|通过审核|拒绝|驳回|审核|归档|同步|重命名|OCR|识别)/i);
      const hasFileReference = /资料|文件|附件|\.(?:pdf|txt|docx?|png|jpe?g|csv|xlsx?)\b/i.test(text)
        || ctx.files.some((file) => text.includes(file.original_filename));
      return Boolean(fileAction) && hasFileReference;
    },
    run: async (ctx, text) => {
      const file = resolveFile(ctx, text);
      if (!file) {
        say(ctx, "没有找到唯一目标资料，请提供资料 ID 或完整文件名。");
        return;
      }
      const action = (text.match(/(审核通过|通过审核|拒绝|驳回|审核|归档|同步|重命名|OCR|识别)/i)?.[1] ?? "").toLowerCase();
      const fields = parseFields(text);
      if (action === "审核") {
        say(ctx, "请明确审核结果：审核通过还是拒绝？");
      } else if (action === "审核通过" || action === "通过审核" || action === "拒绝" || action === "驳回") {
        const reviewAction = action === "审核通过" || action === "通过审核" ? "approve" : "reject";
        await reviewFile(ctx.token, file.id, reviewAction, field(fields, "comment") || "");
        say(ctx, `资料「${file.original_filename}」已${reviewAction === "approve" ? "审核通过" : "拒绝"}。`);
      } else if (action === "归档") {
        sayConfirmation(ctx, `确认归档资料「${file.original_filename}」？`, async () => {
          await archiveFile(ctx.token, file.id);
          return `资料「${file.original_filename}」已归档。`;
        });
      } else if (action === "同步") {
        await syncFileToRag(ctx.token, file.id);
        say(ctx, `资料「${file.original_filename}」已提交到 RAG 同步。`);
      } else if (action === "重命名") {
        const newName = field(fields, "new_name");
        if (!newName) {
          say(ctx, "请提供新文件名，例如：重命名资料 8：新文件名=protocol-v2.pdf。");
          return;
        }
        await useProjectStore.getState().updateFile(ctx.token, file.id, newName);
        say(ctx, `资料已重命名为「${newName}」。`);
      } else {
        const result = await extractOcr(ctx.token, file.id);
        say(ctx, `已完成资料「${file.original_filename}」的 OCR 提取，共 ${result.character_count} 个字符；请打开资料页校对并确认。`);
      }
    },
  },
  {
    match: (text) => /初始化.*(?:资料库|知识库|RAG)/.test(text),
    run: async (ctx) => {
      if (ctx.currentProjectId === null) { say(ctx, "请先进入项目。"); return; }
      await useProjectStore.getState().initRag(ctx.token, ctx.currentProjectId);
      ctx.setRagReady(true);
      say(ctx, "当前项目资料库已初始化。");
    },
  },
  {
    match: (text) => /重建.*(?:图谱|知识图谱)/.test(text),
    run: async (ctx) => {
      if (ctx.currentProjectId === null) { say(ctx, "请先进入项目。"); return; }
      await useProjectStore.getState().rebuildKg(ctx.token, ctx.currentProjectId);
      say(ctx, "当前项目知识图谱已重建。");
    },
  },
  {
    match: (text) => /(提取|抽取).*(?:图谱|知识)/.test(text),
    run: async (ctx, text) => {
      if (ctx.currentProjectId === null) { say(ctx, "请先进入项目。"); return; }
      const note = await resolveNote(ctx, text, ctx.currentProjectId);
      if (!note) { say(ctx, "请指定要提取的笔记，例如：提取笔记 12 的知识图谱。"); return; }
      await useProjectStore.getState().extractNoteKg(ctx.token, note.id);
      say(ctx, `笔记 #${note.id} 的知识图谱已提取。`);
    },
  },
  {
    match: (text) => /重建.*(?:搜索|索引)|重新索引/.test(text),
    run: async (ctx) => {
      await reindexSearch(ctx.token, ctx.currentProjectId === null ? undefined : ctx.currentProjectId);
      say(ctx, "搜索索引已重建。");
    },
  },
  {
    match: (text) => /(新建|创建).*(用户|账号)/.test(text),
    run: async (ctx, text) => {
      const fields = parseFields(text);
      const username = field(fields, "username");
      const password = field(fields, "password");
      const displayName = field(fields, "display_name") || username;
      if (!username || !password || !displayName) {
        say(ctx, "请提供账号信息，例如：创建用户：账号=alice，密码=********，显示名=Alice，角色=member。");
        return;
      }
      const created = await apiCreateUser(ctx.token, {
        username,
        password,
        display_name: displayName,
        role: field(fields, "role") || "member",
      });
      say(ctx, `用户「${created.display_name}」已创建（#${created.id}）。`);
    },
  },
  {
    match: (text) => /(禁用|停用).*(用户|账号)/.test(text),
    run: async (ctx, text) => {
      const id = entityId(text, ["用户", "账号", "user"]);
      if (!id) { say(ctx, "请指定用户 ID，例如：禁用用户 12。"); return; }
      sayConfirmation(ctx, `确认禁用用户 #${id}？`, async () => {
        await apiDisableUser(ctx.token, id);
        return `用户 #${id} 已禁用。`;
      });
    },
  },
  {
    match: (text) => /(修改|更新).*(用户|账号)/.test(text),
    run: async (ctx, text) => {
      const id = entityId(text, ["用户", "账号", "user"]);
      const fields = parseFields(text);
      if (!id) { say(ctx, "请指定用户 ID，例如：修改用户 12：角色=reviewer。"); return; }
      const payload = pickFields(fields, ["display_name", "email", "role"]);
      if (Object.keys(payload).length === 0) { say(ctx, "请提供要修改的字段，例如：修改用户 12：显示名=新名字，角色=reviewer。"); return; }
      await apiUpdateUser(ctx.token, id, payload);
      say(ctx, `用户 #${id} 已更新。`);
    },
  },
  {
    match: (text) => /(新建|创建).*(群组|小组)/.test(text),
    run: async (ctx, text) => {
      const fields = parseFields(text);
      const name = field(fields, "name") || text.match(/(?:新建|创建)(?:一个)?(?:群组|小组)\s*(?:为|叫|：|:)\s*([^,，]+)/)?.[1]?.trim();
      if (!name) { say(ctx, "请提供群组名称，例如：创建群组：名称=生物实验组，描述=负责细胞实验。"); return; }
      const group = await apiCreateGroup(ctx.token, { name, description: field(fields, "description") });
      say(ctx, `群组「${group.name}」已创建（#${group.id}）。`);
    },
  },
  {
    match: (text) => /(修改|更新).*(群组|小组)/.test(text),
    run: async (ctx, text) => {
      const id = entityId(text, ["群组", "小组", "group"]);
      const fields = parseFields(text);
      if (!id) { say(ctx, "请指定群组 ID，例如：修改群组 3：名称=核心实验组。"); return; }
      const payload = pickFields(fields, ["name", "description"]);
      if (Object.keys(payload).length === 0) { say(ctx, "请提供要修改的字段，例如：修改群组 3：描述=新的研究方向。"); return; }
      await apiUpdateGroup(ctx.token, id, payload);
      say(ctx, `群组 #${id} 已更新。`);
    },
  },
  {
    match: (text) => /(添加|加入).*(项目成员|成员)/.test(text),
    run: async (ctx, text) => {
      if (ctx.currentProjectId === null) { say(ctx, "请先进入项目。"); return; }
      const userId = entityId(text, ["用户", "账号", "成员", "user"]);
      if (!userId) { say(ctx, "请指定用户 ID，例如：添加用户 12 为项目成员。"); return; }
      const fields = parseFields(text);
      const permissionText = `${text} ${field(fields, "role") || ""}`;
      await addProjectMember(ctx.token, ctx.currentProjectId, {
        user_id: userId,
        project_role: field(fields, "role") || "member",
        can_read: true,
        can_write: /写|编辑/.test(permissionText),
        can_review: /审|审核/.test(permissionText),
        can_evaluate: /评|评价/.test(permissionText),
        can_manage: /管|管理/.test(permissionText),
      });
      say(ctx, `用户 #${userId} 已添加到当前项目。`);
    },
  },
  {
    match: (text) => /(移除|删除).*(项目成员|成员)/.test(text),
    run: async (ctx, text) => {
      if (ctx.currentProjectId === null) { say(ctx, "请先进入项目。"); return; }
      const projectId = ctx.currentProjectId;
      const userId = entityId(text, ["用户", "账号", "成员", "user"]);
      if (!userId) { say(ctx, "请指定用户 ID，例如：移除项目成员 12。"); return; }
      sayConfirmation(ctx, `确认移除当前项目成员 #${userId}？`, async () => {
        await removeProjectMember(ctx.token, projectId, userId);
        return `项目成员 #${userId} 已移除。`;
      });
    },
  },
  {
    match: (text) => taskTypeFromText(text) !== null,
    run: async (ctx, text) => {
      const taskType = taskTypeFromText(text);
      if (!taskType) return;
      if (ctx.currentProjectId === null) {
        say(ctx, "请先进入一个项目，我才能基于项目数据执行这个 Agent 任务。");
        return;
      }
      const run = await useProjectStore.getState().generateAgent(ctx.token, ctx.currentProjectId, { task_type: taskType });
      say(ctx, reportSummary(run), `已调用${taskLabels[taskType] || "Agent"} · 可在「报告」页面查看完整内容`);
    },
  },
  {
    match: isLikelyOperation,
    run: async (ctx) => say(ctx, "我理解这是一个操作请求，但目标或动作还不够明确。请补充项目、笔记或资料的名称/编号，例如：看看项目成员、打开 AI 问答、归档资料 8。"),
  },
  {
    match: () => true,
    run: async (ctx, text) => {
      if (ctx.currentProjectId === null) {
        say(ctx, "我可以操作项目、用户、群组和页面。进入项目后，还可以操作笔记、资料、审批、RAG、图谱和 Agent 报告。");
        return;
      }
      if (ctx.ragReady !== true) {
        say(ctx, ctx.ragReady === null ? "我还在读取当前项目的知识库状态，请稍后再试。" : "当前项目资料库还没有初始化。你可以说“初始化资料库”或“打开 AI 问答”。");
        return;
      }
      const result = await useProjectStore.getState().queryRag(ctx.token, ctx.currentProjectId, text, "auto");
      say(ctx, result.answer, result.sources.length > 0 ? `基于 ${result.sources.length} 条资料证据回答` : "基于当前项目知识库回答");
    },
  },
];

/** 按注册顺序执行第一条命中的指令，未命中时走表尾的知识库问答兜底。 */
export async function runAgentCommands(ctx: AgentCommandContext, text: string): Promise<void> {
  for (const command of commands) {
    if (command.match(text, ctx)) {
      await command.run(ctx, text);
      return;
    }
  }
}

// 显式导出类型，避免上层直接依赖实现细节。
export type { AgentCommandContext, AgentMessage };
