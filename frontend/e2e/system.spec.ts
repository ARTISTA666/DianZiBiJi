import path from "node:path";
import { APIRequestContext, APIResponse, expect, Page, request, test } from "@playwright/test";


const API_URL = process.env.E2E_API_URL || "http://127.0.0.1:18000";
const RUN_ID = process.env.E2E_RUN_ID || Date.now().toString();
const PROJECT_NAME = `系统级自动化测试项目 ${RUN_ID}`;
const NOTE_TITLE = `E2E PCR 审批笔记 ${RUN_ID}`;
const EVALUATOR = `e2e_evaluator_${RUN_ID}`;
const EVALUATOR_PASSWORD = "E2eEvaluator123";
const MANAGED_USER = `e2e_managed_${RUN_ID}`;
const MANAGED_DISPLAY_NAME = `E2E 管理台用户 ${RUN_ID}`;
const MANAGED_GROUP = `E2E 管理台小组 ${RUN_ID}`;
const OCR_CORRECTION = [
  "180 Jany 29 1845",
  "Repeat this exp!",
  "Arranged needles on the outside of the two poles as in the diagram, found them all magnetized minus.",
].join("\n");
const OCR_QUESTION = "What was arranged on the outside of the two poles?";
const IMAGE_PATH = path.resolve(
  __dirname,
  "../../data/real/smithsonian_joseph_henry/images/SIA-SIA2012-6685.jpg",
);

let adminApi: APIRequestContext;
let noteId: number;
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
  const loginButton = page.getByRole("button", { name: "登录" });
  await expect(loginButton).toBeEnabled();
  await loginButton.click();
  // 项目首页待审批横幅会渲染含项目名的链接，必须精确匹配导航链接本身。
  await expect(page.getByRole("link", { name: "项目", exact: true })).toBeVisible();
}


async function selectProject(page: Page) {
  await page.getByText(PROJECT_NAME, { exact: true }).click();
  await expect(page.getByRole("button", { name: PROJECT_NAME, exact: true })).toBeVisible();
}


async function selectRadixOption(page: Page, label: string, option: string) {
  await page.getByLabel(label).click();
  await page.getByRole("option", { name: option, exact: true }).click();
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

  const me = await checkedJson(await adminApi.get("/auth/me"));
  const evaluator = await checkedJson(
    await adminApi.post("/users", {
      data: {
        username: EVALUATOR,
        password: EVALUATOR_PASSWORD,
        display_name: "E2E 独立评价人",
        role: "reviewer",
      },
    }),
  );
  const project = await checkedJson(
    await adminApi.post("/projects", {
      data: {
        name: PROJECT_NAME,
        description: "隔离环境中的浏览器自动化测试项目",
        is_sensitive: true,
        approval_enabled: true,
        owner_user_id: me.id,
      },
    }),
  );
  projectId = project.id;
  await checkedJson(
    await adminApi.post(`/projects/${project.id}/reviewers`, {
      data: {
        user_id: evaluator.id,
        review_scope: "all",
      },
    }),
  );
  const note = await checkedJson(
    await adminApi.post(`/projects/${project.id}/notes`, {
      data: {
        title: NOTE_TITLE,
        experiment_type: "PCR",
        experiment_date: "2026-07-13",
        fixed_fields_json: {
          reagents: "Taq DNA Polymerase、dNTP",
          sample: "cDNA 样本 1、cDNA 样本 2",
          result: "扩增条带清晰",
        },
        content_json: { text: "PCR 实验使用 Taq DNA Polymerase，扩增条带清晰。" },
      },
    }),
  );
  noteId = note.id;
  await checkedJson(await adminApi.post(`/notes/${note.id}/submit`));
});


test.afterAll(async () => {
  await adminApi?.dispose();
});


test("登录并完成笔记审批", async ({ page }) => {
  await login(page, "admin", "admin123");
  await selectProject(page);
  await page.getByRole("tab", { name: "审批", exact: true }).click();

  const card = page.getByTestId(`approval-note-${noteId}`);
  await card.getByPlaceholder("审核意见").fill("E2E 审批通过");
  await card.getByRole("button", { name: "通过", exact: true }).click();

  await expect(page.getByText("所有笔记已审批完毕")).toBeVisible();
});


test("图片 OCR、人工校对、入库、问答和五方法实验形成闭环", async ({ page }) => {
  await login(page, "admin", "admin123");
  await selectProject(page);
  await page.getByRole("tab", { name: "AI 问答", exact: true }).click();

  await page.getByRole("button", { name: "初始化资料库" }).click();
  await expect(page.getByText("项目资料库已初始化", { exact: true })).toBeVisible();

  await page.getByRole("tab", { name: "资料", exact: true }).click();
  await page.getByLabel("文件类别").click();
  await page.getByRole("option", { name: "知识文档" }).click();

  const filename = path.basename(IMAGE_PATH);
  await page.getByLabel("选择上传文件").setInputFiles(IMAGE_PATH);
  await page.getByRole("button", { name: "上传", exact: true }).click();
  const fileRow = page.locator('[data-testid^="file-row-"]').filter({ hasText: filename });
  await expect(fileRow).toBeVisible();
  await fileRow.getByRole("button", { name: `通过 ${filename}` }).click();

  await fileRow.getByRole("button", { name: `提取文本 ${filename}` }).click();
  const correction = page.getByLabel("OCR 校对文本");
  await expect(correction).toBeVisible({ timeout: 120_000 });
  await correction.fill(OCR_CORRECTION);
  await page.getByRole("button", { name: "确认校对并签名" }).click();
  await expect(page.getByText("文本校对已确认，图片资料现可进入 RAG 入库流程")).toBeVisible();

  await fileRow.getByRole("button", { name: "本地向量入库" }).click();
  await expect(page.getByText("资料已同步到 AI 知识库")).toBeVisible({ timeout: 120_000 });

  await page.getByRole("tab", { name: "AI 问答", exact: true }).click();
  await expect(page.getByText("已初始化 · 1 个文件已入库", { exact: true })).toBeVisible();
  await page.getByPlaceholder("输入问题...").fill(OCR_QUESTION);
  await page.getByRole("button", { name: "提问", exact: true }).click();
  await expect(page.getByText(/E2E 固定回答/).first()).toBeVisible({ timeout: 60_000 });

  await page.goto(`/projects/${projectId}/system-test`, { waitUntil: "networkidle" });
  await page.getByLabel("实验名称").fill("E2E 五方法问答实验");
  await page.getByLabel("测试问题（每行一个）").fill(OCR_QUESTION);
  await page.getByLabel("每种方法重复次数").fill("1");
  await page.getByLabel("随机种子").fill("20260713");
  await page.getByRole("button", { name: "运行五方法对照实验" }).click();
  await expect(page.getByText(/对照实验 #\d+ 已结束：成功 5，失败 0/)).toBeVisible({ timeout: 120_000 });
});


test("独立评价人只能在盲评页面提交评价", async ({ page }) => {
  await login(page, EVALUATOR, EVALUATOR_PASSWORD);
  await selectProject(page);
  await expect(page.getByRole("heading", { name: "独立人工盲评" })).toBeVisible();
  await expect(page.getByText("正式评审前必须先冻结题集、语料和评分规则。")).toBeVisible();
  await expect(page.getByRole("tab", { name: "笔记", exact: true })).toHaveCount(0);

  const item = page.locator('[data-testid^="blind-review-"]').first();
  await expect(item).toBeVisible();
  const testId = await item.getAttribute("data-testid");
  const blindId = testId!.replace("blind-review-", "");
  await selectRadixOption(page, `${blindId} 评分`, "5");
  await selectRadixOption(page, `${blindId} 准确性`, "准确");
  await selectRadixOption(page, `${blindId} 可追溯性`, "可追溯");
  await item.getByLabel(`${blindId} 评价备注`).fill("E2E 盲评流程通过");
  page.once("dialog", (dialog) => dialog.accept());
  await item.getByRole("button", { name: "提交并继续" }).click();

  await expect(page.getByText(`盲评 ${blindId} 已保存`)).toBeVisible();
});


test("系统管理员完成账号、小组和审计闭环", async ({ page }) => {
  await login(page, "admin", "admin123");
  await page.getByRole("link", { name: "管理", exact: true }).click();
  await expect(page.getByRole("heading", { name: "系统管理" })).toBeVisible();

  await page.getByRole("textbox", { name: "账号" }).fill(MANAGED_USER);
  await page.getByLabel("显示名").fill(MANAGED_DISPLAY_NAME);
  await page.getByLabel("邮箱").fill(`${MANAGED_USER}@example.test`);
  await page.getByLabel("初始密码").fill("ManagedUser123!");
  await page.getByRole("button", { name: "创建账号" }).click();
  await expect(page.getByText(`账号 ${MANAGED_USER} 已创建`)).toBeVisible();
  const managedRow = page.locator('[data-testid^="admin-user-"]').filter({ hasText: MANAGED_USER });
  await expect(managedRow.getByRole("button", { name: `停用 ${MANAGED_USER}` })).toBeVisible();
  const managedUserId = Number((await managedRow.getAttribute("data-testid"))?.replace("admin-user-", ""));
  expect(managedUserId).toBeGreaterThan(0);

  await page.getByRole("tab", { name: "小组", exact: true }).click();
  await page.getByLabel("小组名称").fill(MANAGED_GROUP);
  await page.getByLabel("说明").fill("隔离端到端管理测试");
  await selectRadixOption(page, "负责人", `${MANAGED_DISPLAY_NAME}（${MANAGED_USER}）`);
  await page.getByRole("button", { name: "创建小组" }).click();
  await expect(page.getByText(`小组 ${MANAGED_GROUP} 已创建`)).toBeVisible();

  await selectRadixOption(page, "添加成员", `${MANAGED_DISPLAY_NAME}（${MANAGED_USER}）`);
  await page.getByRole("button", { name: "添加或更新成员" }).click();
  await expect(page.getByText("小组成员已保存")).toBeVisible();
  await expect(page.getByText(`${MANAGED_DISPLAY_NAME} · member`)).toBeVisible();

  await page.getByRole("tab", { name: "审计", exact: true }).click();
  await page.getByLabel("审计动作").fill("create_user");
  await page.getByRole("button", { name: "查询审计日志" }).click();
  await expect(page.getByText("create_user", { exact: true }).first()).toBeVisible();

  await page.goto(`/projects/${projectId}/settings`, { waitUntil: "networkidle" });
  await page.getByRole("button", { name: "添加成员" }).click();
  await page.getByPlaceholder("输入用户ID").fill(String(managedUserId));
  await page.getByLabel("设为独立盲评人").check();
  await page.getByRole("button", { name: "添加独立盲评人" }).click();
  const reviewerRow = page.locator("div.rounded-md.border.p-3").filter({
    has: page.getByText(`用户 #${managedUserId}`, { exact: true }),
  });
  await expect(reviewerRow).toBeVisible();
  await expect(reviewerRow.getByText("独立盲评", { exact: true })).toBeVisible();
  await expect(page.getByLabel(`用户 ${managedUserId} 读权限`)).toBeDisabled();
  await expect(page.getByLabel(`用户 ${managedUserId} 评权限`)).toBeDisabled();
  await page.getByRole("button", { name: `移除独立盲评人 ${managedUserId}` }).click();
  await page.getByRole("button", { name: "确认", exact: true }).click();
  await expect(reviewerRow).toHaveCount(0);

  await page.getByRole("button", { name: "账户菜单" }).click();
  await page.getByRole("menuitem", { name: "退出登录" }).click();
  await login(page, MANAGED_USER, "ManagedUser123!");
  await expect(page.getByText("暂无项目", { exact: true })).toBeVisible();
  await expect(page.getByText(PROJECT_NAME, { exact: true })).toHaveCount(0);
});
