import path from "node:path";
import { APIRequestContext, APIResponse, expect, Page, request, test } from "@playwright/test";

const API_URL = process.env.E2E_API_URL || "http://127.0.0.1:18000";
const RUN_ID = process.env.E2E_RUN_ID || Date.now().toString();
const PASSWORD = "LabMember123";

const USERS = {
  pi: { username: `lab_pi_${RUN_ID}`, displayName: "课题负责人 PI", role: "pi" },
  leader: { username: `lab_leader_${RUN_ID}`, displayName: "课题组长", role: "group_leader" },
  owner: { username: `lab_owner_${RUN_ID}`, displayName: "项目负责人", role: "project_owner" },
  recorder: { username: `lab_recorder_${RUN_ID}`, displayName: "实验记录员", role: "member" },
  reviewer: { username: `lab_reviewer_${RUN_ID}`, displayName: "资料与笔记审核人", role: "reviewer" },
  viewer: { username: `lab_viewer_${RUN_ID}`, displayName: "只读成员", role: "member" },
  evaluator: { username: `lab_evaluator_${RUN_ID}`, displayName: "独立 AI 评价人", role: "reviewer" },
} as const;

const PROJECTS = [
  {
    key: "bio",
    name: `课题一｜PCR 条件优化 ${RUN_ID}`,
    description: "生物医学：PCR 退火温度与扩增质量记录",
    owner: "owner",
    noteTitle: `PCR 条件优化记录 ${RUN_ID}`,
    noteText: "58℃ 退火时条带最清晰，60℃ 作为复核条件；记录样本、试剂和下一步复验计划。",
    file: path.resolve(__dirname, "fixtures/bio-pcr-protocol.txt"),
    question: "GSE111619 数据包记录了哪些验证边界？",
  },
  {
    key: "htr",
    name: `课题二｜手写文档识别 ${RUN_ID}`,
    description: "文档分析：乌克兰手写识别数据处理实验",
    owner: "leader",
    noteTitle: `手写识别数据处理记录 ${RUN_ID}`,
    noteText: "比较扫描件与手机拍摄样本，记录手写区域、印刷区域和 OCR 复核结果。",
    file: path.resolve(__dirname, "fixtures/htr-dataset-notes.txt"),
    question: "RUKOPYS 数据集覆盖哪些文档变化？",
  },
  {
    key: "history",
    name: `课题三｜历史工程实验记录 ${RUN_ID}`,
    description: "历史工程：1881 年录音圆盘实验资料整理",
    owner: "pi",
    noteTitle: `历史工程资料整理记录 ${RUN_ID}`,
    noteText: "核对原始页、复核转录和实验上下文，记录资料来源及不可推断内容。",
    file: path.resolve(__dirname, "fixtures/historical-engineering-notes.txt"),
    question: "Smithsonian 资料当前的使用边界是什么？",
  },
  {
    key: "system",
    name: `课题四｜系统工程验证 ${RUN_ID}`,
    description: "系统工程：ELN 业务流程与 AI 闭环验证",
    owner: "owner",
    noteTitle: `系统工程验证记录 ${RUN_ID}`,
    noteText: "验证成员权限、审批状态、RAG 入库状态、引用提示和 Agent 待复核状态。",
    file: path.resolve(__dirname, "fixtures/system-validation-notes.txt"),
    question: "系统验证链包含哪些业务闭环？",
  },
] as const;

type UserKey = keyof typeof USERS;
type Project = (typeof PROJECTS)[number];

let adminApi: APIRequestContext;
const userIds = new Map<UserKey, number>();
const projectIds = new Map<string, number>();

test.describe.configure({ mode: "serial" });

async function checkedJson(response: APIResponse) {
  expect(response.ok(), await response.text()).toBeTruthy();
  return response.json();
}

async function login(page: Page, username: string, password: string) {
  await page.goto("/login", { waitUntil: "networkidle" });
  await page.getByLabel("账号").fill(username);
  await page.getByLabel("密码").fill(password);
  await page.getByRole("button", { name: "登录" }).click();
  await expect(page.getByRole("link", { name: "项目", exact: true })).toBeVisible();
}

async function logout(page: Page) {
  await page.getByRole("button", { name: "账户菜单" }).click();
  await page.getByRole("menuitem", { name: "退出登录" }).click();
  await expect(page.getByLabel("账号")).toBeVisible();
}

async function openProject(page: Page, projectId: number, projectName: string) {
  await page.goto(`/projects/${projectId}`, { waitUntil: "networkidle" });
  await expect(page.getByRole("button", { name: projectName, exact: true })).toBeVisible();
}

async function addMember(projectId: number, userId: number, flags: Record<string, unknown>) {
  await checkedJson(await adminApi.post(`/projects/${projectId}/members`, {
    data: {
      user_id: userId,
      project_role: "member",
      can_read: true,
      can_write: false,
      can_review: false,
      can_evaluate: false,
      can_manage: false,
      ...flags,
    },
  }));
}

async function mcpCall(method: string, params: Record<string, unknown> = {}) {
  const payload = await checkedJson(await adminApi.post("/api/mcp", {
    data: { jsonrpc: "2.0", id: Date.now(), method, params },
  }));
  expect(payload.jsonrpc).toBe("2.0");
  expect(payload.error).toBeUndefined();
  return payload.result;
}

async function createNote(page: Page, project: Project, actor: UserKey) {
  const projectId = projectIds.get(project.key)!;
  await login(page, USERS[actor].username, PASSWORD);
  await openProject(page, projectId, project.name);
  await page.getByRole("button", { name: "新建笔记" }).click();
  await page.getByLabel("标题").fill(project.noteTitle);
  await page.getByLabel("实验日期").fill("2026-08-09");
  await page.getByLabel("内容").fill(project.noteText);
  await page.getByRole("button", { name: "保存", exact: true }).click();
  await expect(page.getByText("笔记已保存", { exact: true })).toBeVisible();
  await page.getByText(project.noteTitle, { exact: true }).click();
  await page.getByRole("button", { name: "提交审核" }).click();
  await expect(page.getByText("待审核", { exact: true })).toBeVisible();
  await logout(page);
}

async function reviewNote(page: Page, project: Project) {
  const projectId = projectIds.get(project.key)!;
  await login(page, USERS.reviewer.username, PASSWORD);
  await page.goto(`/projects/${projectId}/approvals`, { waitUntil: "networkidle" });
  const card = page.locator('[data-testid^="approval-note-"]').filter({ hasText: project.noteTitle });
  await expect(card).toBeVisible();
  await card.getByPlaceholder("审核意见").fill("记录完整，实验上下文和下一步计划清晰，批准归档。");
  await card.getByRole("button", { name: "通过", exact: true }).click();
  await expect(page.getByText("所有笔记已审批完毕")).toBeVisible();
  await logout(page);
}

async function uploadAndReviewFile(page: Page, project: Project) {
  const projectId = projectIds.get(project.key)!;
  const filename = path.basename(project.file);
  await login(page, USERS.recorder.username, PASSWORD);
  await page.goto(`/projects/${projectId}/data`, { waitUntil: "networkidle" });
  await page.getByLabel("文件类别").click();
  await page.getByRole("option", { name: "知识文档" }).click();
  await page.getByLabel("选择上传文件").setInputFiles(project.file);
  await page.getByRole("button", { name: "上传", exact: true }).click();
  await expect(page.locator(`[data-testid^="file-row-"]`).filter({ hasText: filename })).toBeVisible();
  await logout(page);

  await login(page, USERS.reviewer.username, PASSWORD);
  await page.goto(`/projects/${projectId}/data`, { waitUntil: "networkidle" });
  const row = page.locator(`[data-testid^="file-row-"]`).filter({ hasText: filename });
  await row.getByRole("button", { name: `通过 ${filename}` }).click();
  await expect(row.getByText("已审核", { exact: true })).toBeVisible();
  await logout(page);
}

async function runAiFlow(page: Page, project: Project) {
  const projectId = projectIds.get(project.key)!;
  await login(page, USERS[project.owner].username, PASSWORD);
  await openProject(page, projectId, project.name);
  await page.getByRole("tab", { name: "AI 问答", exact: true }).click();
  const initializeButton = page.getByRole("button", { name: "初始化资料库" });
  if (await initializeButton.isVisible()) {
    await initializeButton.click();
    await expect(page.getByText("项目资料库已初始化", { exact: true })).toBeVisible();
  } else {
    await expect(page.getByText("项目资料库", { exact: true })).toBeVisible();
  }
  await page.getByRole("tab", { name: "资料", exact: true }).click();
  const filename = path.basename(project.file);
  const row = page.locator(`[data-testid^="file-row-"]`).filter({ hasText: filename });
  const syncButton = row.getByRole("button", { name: /(?:本地|重试)向量入库/ });
  if (await syncButton.count() > 0) {
    await syncButton.click();
    await expect(page.getByText("资料已同步到 AI 知识库")).toBeVisible({ timeout: 120_000 });
  } else {
    await expect(row.getByText("已入库", { exact: true })).toBeVisible();
  }
  await page.getByRole("tab", { name: "AI 问答", exact: true }).click();
  await expect(page.getByText(/已初始化 · 1 个文件已入库/)).toBeVisible();
  await page.getByPlaceholder("输入问题...").fill(project.question);
  await page.getByRole("button", { name: "提问", exact: true }).click();
  await expect(page.getByText(/E2E 固定回答/).first()).toBeVisible({ timeout: 60_000 });
  await expect(page.getByText(/引用校验/).first()).toBeVisible();

  await page.goto(`/projects/${projectId}/reports`, { waitUntil: "networkidle" });
  await page.getByRole("button", { name: "生成", exact: true }).click();
  await expect(page.getByText(/实验总结/).first()).toBeVisible({ timeout: 60_000 });
  await expect(page.getByText("待人工复核").first()).toBeVisible();
  await expect(page.getByText("引用校验未完全通过。请人工核对来源后再使用此草稿。", { exact: true })).toBeVisible();
  await logout(page);
}

test.beforeAll(async () => {
  const anonymous = await request.newContext({ baseURL: API_URL });
  const loginResponse = await anonymous.post("/auth/login", {
    data: { username: "admin", password: "admin123" },
  });
  const loginData = await checkedJson(loginResponse);
  await anonymous.dispose();
  adminApi = await request.newContext({
    baseURL: API_URL,
    extraHTTPHeaders: { Authorization: `Bearer ${loginData.access_token}` },
  });

  for (const [key, user] of Object.entries(USERS) as [UserKey, (typeof USERS)[UserKey]][]) {
    const created = await checkedJson(await adminApi.post("/users", {
      data: { username: user.username, password: PASSWORD, display_name: user.displayName, role: user.role },
    }));
    userIds.set(key, created.id);
  }

  for (const project of PROJECTS) {
    const ownerId = userIds.get(project.owner)!;
    const created = await checkedJson(await adminApi.post("/projects", {
      data: {
        name: project.name,
        description: project.description,
        is_sensitive: false,
        approval_enabled: true,
        owner_user_id: ownerId,
      },
    }));
    projectIds.set(project.key, created.id);
    for (const key of ["pi", "leader", "owner", "recorder", "reviewer", "viewer"] as UserKey[]) {
      if (key === project.owner) continue;
      await addMember(created.id, userIds.get(key)!, {
        can_write: key === "leader" || key === "owner" || key === "recorder" || key === "reviewer",
        can_review: key === "reviewer",
        can_manage: key === "owner",
      });
    }
  }

  await checkedJson(await adminApi.post(`/projects/${projectIds.get("bio")}/reviewers`, {
    data: { user_id: userIds.get("evaluator"), review_scope: "all" },
  }));
});

test.afterAll(async () => {
  await adminApi?.dispose();
});

test("真实课题组四项目全员协作与 AI 验收", async ({ page }) => {
  const [bio, htr, history, system] = PROJECTS;

  // 记录员、组长、PI 分担不同项目的实验记录。
  await createNote(page, bio, "recorder");
  await createNote(page, htr, "leader");
  await createNote(page, history, "pi");
  await createNote(page, system, "recorder");

  // 审核人逐项目审核笔记；资料也必须经过审核才能进入 RAG。
  for (const project of PROJECTS) await reviewNote(page, project);
  for (const project of PROJECTS) await uploadAndReviewFile(page, project);

  // 项目负责人分别完成初始化、向量入库、问答和 Agent 草稿复核。
  for (const project of PROJECTS) await runAiFlow(page, project);

  // MCP 端到端：工具发现、审核笔记检索、RAG 文档检索和 Agent 任务发现。
  const tools = await mcpCall("tools/list");
  expect(tools.tools.map((tool: { name: string }) => tool.name)).toEqual(expect.arrayContaining([
    "search_notes",
    "retrieve_documents",
    "list_agent_tasks",
  ]));
  const notes = await mcpCall("tools/call", {
    name: "search_notes",
    arguments: { project_id: projectIds.get("bio"), keyword: bio.noteTitle },
  });
  expect(notes.structuredContent.notes).toHaveLength(1);
  const documents = await mcpCall("tools/call", {
    name: "retrieve_documents",
    arguments: { project_id: projectIds.get("system"), query: system.question },
  });
  expect(documents.structuredContent.chunks.length).toBeGreaterThan(0);
  const agentTasks = await mcpCall("tools/call", { name: "list_agent_tasks" });
  expect(agentTasks.structuredContent.tasks.length).toBeGreaterThanOrEqual(5);

  // 独立评价人只能进入盲评入口，不能读取项目原始内容。
  await login(page, USERS.evaluator.username, PASSWORD);
  await openProject(page, projectIds.get("bio")!, bio.name);
  await expect(page.getByRole("heading", { name: "独立人工盲评" })).toBeVisible();
  await expect(page.getByRole("tab", { name: "笔记", exact: true })).toHaveCount(0);
  await logout(page);

  // 只读成员可查阅 AI 结果，但不具备写入、审核、生成权限。
  await login(page, USERS.viewer.username, PASSWORD);
  await openProject(page, systemId(), system.name);
  await expect(page.getByRole("button", { name: "新建笔记" })).toHaveCount(0);
  await page.getByRole("tab", { name: "AI 问答", exact: true }).click();
  await expect(page.getByPlaceholder("输入问题...")).toBeVisible();
  await expect(page.getByRole("button", { name: "初始化资料库" })).toHaveCount(0);
  await page.getByRole("tab", { name: "报告", exact: true }).click();
  await expect(page.getByRole("button", { name: "生成", exact: true })).toHaveCount(0);
  await logout(page);

  // 项目负责人实际进入设置页，确认成员权限在 UI 中可解释、可核对。
  await login(page, USERS.owner.username, PASSWORD);
  await openProject(page, projectIds.get("bio")!, bio.name);
  await page.getByRole("tab", { name: "设置", exact: true }).click();
  await expect(page.getByText(/项目成员 \(\d+\)/)).toBeVisible();
  await expect(page.getByText(/只读成员 \(#\d+\)/)).toBeVisible();
  await logout(page);
});

function systemId() {
  return projectIds.get("system")!;
}
