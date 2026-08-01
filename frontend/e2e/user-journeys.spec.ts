import path from "node:path";
import { APIRequestContext, APIResponse, expect, Page, request, test } from "@playwright/test";

const API_URL = process.env.E2E_API_URL || "http://127.0.0.1:18000";
const RUN_ID = process.env.E2E_RUN_ID || Date.now().toString();
const PROJECT_NAME = `用户验收-PCR 优化 ${RUN_ID}`;
const NOTE_TITLE = `退回后修订的 PCR 笔记 ${RUN_ID}`;
const AUTHOR = `journey_author_${RUN_ID}`;
const REVIEWER = `journey_reviewer_${RUN_ID}`;
const VIEWER = `journey_viewer_${RUN_ID}`;
const PASSWORD = "UserJourney123!";
const OCR_CORRECTION = "实验记录：退火温度调整为 60℃ 后复核，扩增条带清晰。";
const IMAGE_PATH = path.resolve(
  __dirname,
  "../../data/real/smithsonian_joseph_henry/images/SIA-SIA2012-6685.jpg",
);

let adminApi: APIRequestContext;
let authorId: number;
let reviewerId: number;
let viewerId: number;
let projectId: number;

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
  await expect(page.getByRole("link", { name: "项目" })).toBeVisible();
}

async function logout(page: Page) {
  await page.getByRole("button", { name: "账户菜单" }).click();
  await page.getByRole("menuitem", { name: "退出登录" }).click();
  await expect(page.getByLabel("账号")).toBeVisible();
}

async function openProject(page: Page) {
  await page.getByText(PROJECT_NAME, { exact: true }).click();
  await expect(page.getByRole("button", { name: PROJECT_NAME, exact: true })).toBeVisible();
}

async function addProjectMember(
  page: Page,
  userId: number,
  configure?: (dialog: ReturnType<Page["getByRole"]>) => Promise<void>,
) {
  await page.getByRole("tab", { name: "设置", exact: true }).click();
  await page.getByRole("button", { name: "添加成员" }).click();
  const dialog = page.getByRole("dialog", { name: "添加成员" });
  await dialog.getByPlaceholder("输入用户ID").fill(String(userId));
  if (configure) await configure(dialog);
  await dialog.getByRole("button", { name: "添加成员" }).click();
  await expect(page.getByText("成员已添加", { exact: true })).toBeVisible();
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

  const createUser = async (username: string, displayName: string) => checkedJson(
    await adminApi.post("/users", {
      data: { username, password: PASSWORD, display_name: displayName, role: "member" },
    }),
  );
  authorId = (await createUser(AUTHOR, "用户旅程实验记录员")).id;
  reviewerId = (await createUser(REVIEWER, "用户旅程审核人")).id;
  viewerId = (await createUser(VIEWER, "用户旅程只读成员")).id;
});

test.afterAll(async () => {
  await adminApi?.dispose();
});

test("项目负责人、记录员和审核人完成退回修订审批闭环", async ({ page }) => {
  await login(page, "admin", "admin123");
  await page.getByRole("button", { name: "新建项目" }).click();
  await page.getByLabel("项目名称").fill(PROJECT_NAME);
  await page.getByLabel("项目描述").fill("以真实协作职责验收记录、修订与审核流程");
  await page.getByRole("button", { name: "创建", exact: true }).click();
  await expect(page).toHaveURL(/\/projects\/\d+$/);
  projectId = Number(page.url().match(/\/projects\/(\d+)/)?.[1]);
  expect(projectId).toBeGreaterThan(0);

  await addProjectMember(page, authorId);
  await addProjectMember(page, reviewerId, async (dialog) => {
    const permissions = dialog.locator("fieldset").getByRole("checkbox");
    await permissions.nth(1).uncheck();
    await permissions.nth(2).check();
  });
  await logout(page);

  await login(page, AUTHOR, PASSWORD);
  await openProject(page);
  await page.getByRole("button", { name: "新建笔记" }).click();
  await page.getByLabel("标题").fill(NOTE_TITLE);
  await page.getByLabel("实验日期").fill("2026-08-01");
  await page.getByLabel("内容").fill("初版：PCR 扩增出现弱条带，待复核退火温度。");
  await page.getByRole("button", { name: "保存", exact: true }).click();
  await expect(page.getByText("笔记已保存", { exact: true })).toBeVisible();
  await page.getByText(NOTE_TITLE, { exact: true }).click();
  await page.getByRole("button", { name: "提交审核" }).click();
  await expect(page.getByText("待审核", { exact: true })).toBeVisible();
  await logout(page);

  await login(page, REVIEWER, PASSWORD);
  await openProject(page);
  await page.getByRole("tab", { name: "审批", exact: true }).click();
  const approvalCard = page.locator('[data-testid^="approval-note-"]').filter({ hasText: NOTE_TITLE });
  await expect(approvalCard).toBeVisible();
  await approvalCard.getByPlaceholder("审核意见").fill("请补充退火温度和复核结论。");
  await approvalCard.getByRole("button", { name: "退回" }).click();
  await expect(page.getByText("所有笔记已审批完毕")).toBeVisible();
  await logout(page);

  await login(page, AUTHOR, PASSWORD);
  await openProject(page);
  await page.getByText(NOTE_TITLE, { exact: true }).click();
  await page.getByRole("button", { name: "编辑" }).click();
  await page.getByLabel("内容").fill("修订版：退火温度调整为 60℃ 后复核，扩增条带清晰。");
  await page.getByRole("button", { name: "保存", exact: true }).click();
  await page.getByText(NOTE_TITLE, { exact: true }).click();
  await page.getByRole("button", { name: "提交审核" }).click();
  await logout(page);

  await login(page, REVIEWER, PASSWORD);
  await openProject(page);
  await page.getByRole("tab", { name: "审批", exact: true }).click();
  const revisedCard = page.locator('[data-testid^="approval-note-"]').filter({ hasText: NOTE_TITLE });
  await revisedCard.getByPlaceholder("审核意见").fill("温度与复核结论完整，批准归档。");
  await revisedCard.getByRole("button", { name: "通过" }).click();
  await expect(page.getByText("所有笔记已审批完毕")).toBeVisible();

  await logout(page);
  await login(page, AUTHOR, PASSWORD);
  await openProject(page);
  await page.getByText(NOTE_TITLE, { exact: true }).click();
  await expect(page.getByText("最新版本（v2）")).toBeVisible();
  await expect(page.getByText("温度与复核结论完整，批准归档。")).toBeVisible();
  await expect(page.getByRole("dialog").getByText("已审核", { exact: true })).toBeVisible();
});

test("多角色完成 AI 资料、图谱、问答与报告协作闭环", async ({ page }) => {
  const filename = path.basename(IMAGE_PATH);

  await login(page, AUTHOR, PASSWORD);
  await openProject(page);
  await page.goto(`/projects/${projectId}/data`, { waitUntil: "networkidle" });
  await page.getByLabel("文件类别").click();
  await page.getByRole("option", { name: "知识文档" }).click();
  await page.getByLabel("选择上传文件").setInputFiles(IMAGE_PATH);
  await page.getByRole("button", { name: "上传", exact: true }).click();
  const fileRow = page.locator('[data-testid^="file-row-"]').filter({ hasText: filename });
  await expect(fileRow).toBeVisible();
  await logout(page);

  await login(page, REVIEWER, PASSWORD);
  await openProject(page);
  await page.goto(`/projects/${projectId}/data`, { waitUntil: "networkidle" });
  const reviewerFileRow = page.locator('[data-testid^="file-row-"]').filter({ hasText: filename });
  await reviewerFileRow.getByRole("button", { name: `通过 ${filename}` }).click();
  await reviewerFileRow.getByRole("button", { name: `提取文本 ${filename}` }).click();
  const correction = page.getByLabel("OCR 校对文本");
  await expect(correction).toBeVisible({ timeout: 120_000 });
  await correction.fill(OCR_CORRECTION);
  await page.getByRole("button", { name: "确认校对并签名" }).click();
  await expect(page.getByText("文本校对已确认，图片资料现可进入 RAG 入库流程")).toBeVisible();
  await logout(page);

  await login(page, "admin", "admin123");
  await openProject(page);
  await page.getByRole("tab", { name: "AI 问答", exact: true }).click();
  await page.getByRole("button", { name: "初始化资料库" }).click();
  await expect(page.getByText("项目资料库已初始化", { exact: true })).toBeVisible();
  await page.getByRole("tab", { name: "资料", exact: true }).click();
  const ownerFileRow = page.locator('[data-testid^="file-row-"]').filter({ hasText: filename });
  await ownerFileRow.getByRole("button", { name: "本地向量入库" }).click();
  await expect(page.getByText("资料已同步到 AI 知识库")).toBeVisible({ timeout: 120_000 });
  await logout(page);

  await login(page, AUTHOR, PASSWORD);
  await openProject(page);
  await page.goto(`/projects/${projectId}/kg`, { waitUntil: "networkidle" });
  const noteRow = page.getByText(NOTE_TITLE, { exact: true }).locator("..");
  await noteRow.getByRole("button", { name: "提取" }).click();
  await expect(page.getByText("实体已提取", { exact: true })).toBeVisible({ timeout: 60_000 });
  await page.getByRole("tab", { name: "AI 问答", exact: true }).click();
  await expect(page.getByText("已初始化 · 1 个文件已入库", { exact: true })).toBeVisible();
  await page.getByPlaceholder("输入问题...").fill("这份项目资料的实验结论是什么？");
  await page.getByRole("button", { name: "提问", exact: true }).click();
  await expect(page.getByText(/E2E 固定回答/).first()).toBeVisible({ timeout: 60_000 });
  await page.goto(`/projects/${projectId}/reports`, { waitUntil: "networkidle" });
  await page.getByRole("button", { name: "生成", exact: true }).click();
  await expect(page.getByText(/实验总结/).first()).toBeVisible({ timeout: 60_000 });
});

test("只读成员只能查阅，不能看到写入或项目管理操作", async ({ page }) => {
  await login(page, "admin", "admin123");
  await page.goto(`/projects/${projectId}/settings`, { waitUntil: "networkidle" });
  await addProjectMember(page, viewerId, async (dialog) => {
    await dialog.locator("fieldset").getByRole("checkbox").nth(1).uncheck();
  });
  await logout(page);

  await login(page, VIEWER, PASSWORD);
  await openProject(page);
  await expect(page.getByRole("button", { name: "新建笔记" })).toHaveCount(0);
  await expect(page.getByRole("tab", { name: "设置", exact: true })).toHaveCount(0);
  await page.getByText(NOTE_TITLE, { exact: true }).click();
  await expect(page.getByRole("button", { name: "提交审核" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "编辑" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "作废" })).toHaveCount(0);

  await page.goto(`/projects/${projectId}/data`, { waitUntil: "networkidle" });
  await expect(page.getByRole("button", { name: "上传", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: `归档 ${path.basename(IMAGE_PATH)}` })).toHaveCount(0);
  await expect(page.getByRole("button", { name: `通过 ${path.basename(IMAGE_PATH)}` })).toHaveCount(0);
  await page.goto(`/projects/${projectId}/kg`, { waitUntil: "networkidle" });
  await expect(page.getByRole("button", { name: "重建图谱" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "提取" })).toHaveCount(0);
  await page.goto(`/projects/${projectId}/reports`, { waitUntil: "networkidle" });
  await expect(page.getByRole("button", { name: "生成", exact: true })).toHaveCount(0);
  await expect(page.getByText("只读成员可以查看已生成报告，不能创建新的智能体任务。", { exact: true })).toBeVisible();

  await page.goto(`/projects/${projectId}/settings`, { waitUntil: "networkidle" });
  await expect(page.getByText("只有项目管理员可以访问项目设置。", { exact: true })).toBeVisible();
});
