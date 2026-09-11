import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const require = createRequire(import.meta.url);

const { chromium } = require(path.resolve(__dirname, "../../frontend/node_modules/playwright"));

// 使用 localhost 确保与后端 HttpOnly Cookie 处于同源同一 cookie jar
const BASE_URL = process.env.BASE_URL || "http://localhost:3000";
const SCREENSHOT_DIR = path.resolve(__dirname, "../../docs/user-simulation-evidence/screenshots");
const VIDEO_DIR = path.resolve(__dirname, "../../docs/user-simulation-evidence/videos");
const TEMP_VIDEO_DIR = path.resolve(__dirname, "../../docs/user-simulation-evidence/videos/temp");

fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
fs.mkdirSync(VIDEO_DIR, { recursive: true });
fs.mkdirSync(TEMP_VIDEO_DIR, { recursive: true });

async function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

async function loginUser(page, username, password) {
  console.log(`[Auth] 正在登录用户: ${username}...`);
  await page.goto(`${BASE_URL}/login`, { waitUntil: "networkidle" });
  await page.locator("#username").fill(username);
  await sleep(200);
  await page.locator("#password").fill(password);
  await sleep(200);
  await page.getByRole("button", { name: "登录" }).click();
  await page.waitForURL((url) => !url.pathname.includes("/login"), { timeout: 15000 });
  await page.waitForLoadState("networkidle");
  await sleep(1000);
}

async function runSimulation() {
  console.log("==================================================================");
  console.log("启动论文创新点多用户操作模拟与自动化录屏/截屏 (精细优化版)");
  console.log(`前端地址: ${BASE_URL}`);
  console.log(`截图目录: ${SCREENSHOT_DIR}`);
  console.log(`视频目录: ${VIDEO_DIR}`);
  console.log("==================================================================");

  const browser = await chromium.launch({
    headless: true,
    args: ["--no-sandbox", "--disable-setuid-sandbox"],
  });

  // =========================================================================
  // 角色 1: 陈薇 (chenwei_lab / Lab@2026) - 项目负责人 / 导师
  // 重点验证: 创新点一(知识蓝图双态图谱、待实证导引)、创新点二(预警四维指标、告警确认与调阈留痕)
  // =========================================================================
  console.log("\n>>> 开始模拟 角色 1: 陈薇 (项目负责人 / 导师)");
  {
    const context = await browser.newContext({
      viewport: { width: 1920, height: 1080 },
      recordVideo: { dir: TEMP_VIDEO_DIR, size: { width: 1920, height: 1080 } },
    });
    const page = await context.newPage();

    // 1. 登录
    await loginUser(page, "chenwei_lab", "Lab@2026");

    // 2. 进入项目 10 工作台
    console.log("  -> 进入项目 10: 乳腺癌外泌体 miRNA 标志物筛选课题");
    await page.goto(`${BASE_URL}/projects/10`, { waitUntil: "networkidle" });
    await sleep(2000);
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, "01_chenwei_workspace.png"),
      fullPage: false,
    });
    console.log("  [Screenshot] 01_chenwei_workspace.png");

    // 3. 进入「预警」页签（创新点二：预警与人工审核闭环）
    console.log("  -> 切换到「预警」页签，查看四维指标监控与严重告警");
    await page.goto(`${BASE_URL}/projects/10/alerts`, { waitUntil: "networkidle" });
    await sleep(2500);
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, "02_chenwei_alerts_inbox.png"),
      fullPage: false,
    });
    console.log("  [Screenshot] 02_chenwei_alerts_inbox.png");

    // 4. 查看告警详情与导师确认备注（论文 7.9.1 真实记录）
    const ackAlert = page.locator("text=已知晓：蓝图刚解析完成").first();
    if (await ackAlert.count() > 0) {
      console.log("  -> 聚焦导师确认留痕备注卡片");
      await ackAlert.scrollIntoViewIfNeeded();
      await sleep(1000);
    }
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, "03_chenwei_alert_acknowledged.png"),
      fullPage: false,
    });
    console.log("  [Screenshot] 03_chenwei_alert_acknowledged.png");

    // 5. 进入「图谱」页签并切换到「知识蓝图（计划态 vs 实证态）」（创新点一：动态知识蓝图）
    console.log("  -> 切换到「图谱」页签，进入「知识蓝图」子页签");
    await page.goto(`${BASE_URL}/projects/10/kg`, { waitUntil: "networkidle" });
    await sleep(2000);
    const blueprintTabTrigger = page.getByRole("tab", { name: /知识蓝图/ });
    if (await blueprintTabTrigger.isVisible()) {
      await blueprintTabTrigger.click();
      console.log("  -> 点击「知识蓝图（计划态 vs 实证态）」标签");
      await sleep(4000); // 等待 ForceGraph 与待实证缺口列表充分渲染
    }
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, "04_chenwei_blueprint_gaps.png"),
      fullPage: false,
    });
    console.log("  [Screenshot] 04_chenwei_blueprint_gaps.png");

    // 6. 进入「设置」页签（查看课题组成员能力位与权限划分）
    console.log("  -> 切换到「设置」页签，查看成员能力位配置");
    await page.goto(`${BASE_URL}/projects/10/settings`, { waitUntil: "networkidle" });
    await sleep(2000);
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, "05_chenwei_project_settings.png"),
      fullPage: false,
    });
    console.log("  [Screenshot] 05_chenwei_project_settings.png");

    // 完成角色 1 录制
    await sleep(1000);
    const video = page.video();
    await context.close();
    if (video) {
      const videoPath = await video.path();
      const targetVideoPath = path.join(VIDEO_DIR, "01_chenwei_workflow.webm");
      if (fs.existsSync(videoPath)) {
        fs.renameSync(videoPath, targetVideoPath);
        console.log(`  [Video] 已保存录屏: ${targetVideoPath}`);
      }
    }
  }

  // =========================================================================
  // 角色 2: 李娜 (liuna_lab / Lab@2026) - 审核人员
  // 重点验证: 核心业务闭环(实验笔记审核门禁流转与四元组结构化审查)、创新点二(AI 问答独立评价打分)
  // =========================================================================
  console.log("\n>>> 开始模拟 角色 2: 李娜 (审核人员)");
  {
    const context = await browser.newContext({
      viewport: { width: 1920, height: 1080 },
      recordVideo: { dir: TEMP_VIDEO_DIR, size: { width: 1920, height: 1080 } },
    });
    const page = await context.newPage();

    // 1. 登录
    await loginUser(page, "liuna_lab", "Lab@2026");

    // 2. 进入项目 10 笔记列表页，点击审阅一条笔记，打开结构化字段与审核记录对话框
    console.log("  -> 进入项目 10 笔记列表，打开已审核实验笔记详情");
    await page.goto(`${BASE_URL}/projects/10`, { waitUntil: "networkidle" });
    await sleep(2000);

    const firstNoteTitle = page.locator("h3, .font-semibold, div").filter({ hasText: /外泌体 Western Blot 鉴定|miRNA/ }).first();
    if (await firstNoteTitle.count() > 0) {
      await firstNoteTitle.click();
      await sleep(2000);
    }
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, "07_liuna_note_review_detail.png"),
      fullPage: false,
    });
    console.log("  [Screenshot] 07_liuna_note_review_detail.png (笔记详情/四元组/审核流转)");

    // 关闭弹窗
    const closeDialogBtn = page.locator("button[aria-label='Close'], button:has-text('关闭')").first();
    if (await closeDialogBtn.count() > 0 && await closeDialogBtn.isVisible()) {
      await closeDialogBtn.click();
      await sleep(600);
    }

    // 3. 进入「审批」中心，展示审批状态与待审/已审流转
    console.log("  -> 进入项目 10「审批」中心");
    await page.goto(`${BASE_URL}/projects/10/approvals`, { waitUntil: "networkidle" });
    await sleep(2000);
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, "06_liuna_approvals_center.png"),
      fullPage: false,
    });
    console.log("  [Screenshot] 06_liuna_approvals_center.png");

    // 4. 切换到「AI 问答」页签，执行独立评价与打分
    console.log("  -> 切换到「AI 问答」页签，对既有问答进行质量与可追溯性评价");
    await page.goto(`${BASE_URL}/projects/10/ai`, { waitUntil: "networkidle" });
    await sleep(2500);

    // 寻找问答卡片上的反馈评价按钮（如 ThumbsUp / 评价按钮）
    const thumbsUpBtn = page.locator("button:has(.lucide-thumbs-up)").first();
    if (await thumbsUpBtn.count() > 0 && await thumbsUpBtn.isVisible()) {
      await thumbsUpBtn.click();
      await sleep(1000);
    }
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, "08_liuna_qa_evaluation.png"),
      fullPage: false,
    });
    console.log("  [Screenshot] 08_liuna_qa_evaluation.png");

    // 完成角色 2 录制
    await sleep(1000);
    const video = page.video();
    await context.close();
    if (video) {
      const videoPath = await video.path();
      const targetVideoPath = path.join(VIDEO_DIR, "02_liuna_workflow.webm");
      if (fs.existsSync(videoPath)) {
        fs.renameSync(videoPath, targetVideoPath);
        console.log(`  [Video] 已保存录屏: ${targetVideoPath}`);
      }
    }
  }

  // =========================================================================
  // 角色 3: 赵鹏 (zhaopeng_lab / Lab@2026) - 实验记录员 / 普通成员
  // 重点验证: 业务记录规范化表单、创新点二(AI 导师助手主动建议与 [S]/[G] 引用问答)、创新点三(语义可视化反馈与 Ego-Network 一跳聚焦)
  // =========================================================================
  console.log("\n>>> 开始模拟 角色 3: 赵鹏 (实验记录员 / 普通成员)");
  {
    const context = await browser.newContext({
      viewport: { width: 1920, height: 1080 },
      recordVideo: { dir: TEMP_VIDEO_DIR, size: { width: 1920, height: 1080 } },
    });
    const page = await context.newPage();

    // 1. 登录
    await loginUser(page, "zhaopeng_lab", "Lab@2026");

    // 2. 在项目笔记页，点击「新建笔记」展示四元组结构化表单
    console.log("  -> 进入项目笔记列表，打开「新建笔记」对话框");
    await page.goto(`${BASE_URL}/projects/10`, { waitUntil: "networkidle" });
    await sleep(2000);
    const newNoteBtn = page.getByRole("button", { name: "新建笔记" });
    try {
      await newNoteBtn.waitFor({ state: "visible", timeout: 8000 });
      await newNoteBtn.click();
      await sleep(1500);
      await page.screenshot({
        path: path.join(SCREENSHOT_DIR, "09_zhaopeng_new_note_form.png"),
        fullPage: false,
      });
      console.log("  [Screenshot] 09_zhaopeng_new_note_form.png");

      // 关闭弹窗
      const closeBtn = page.locator("button:has-text('取消'), button[aria-label='Close']").first();
      if (await closeBtn.isVisible()) await closeBtn.click();
      await sleep(500);
    } catch (err) {
      console.warn("  [Warn] 未能打开新建笔记表单:", err.message);
    }

    // 3. 切换到「AI 问答」页签，查看基于蓝图缺口推导的主动建议
    console.log("  -> 切换到「AI 问答」页签，查看 AI 导师助手下一步建议");
    await page.goto(`${BASE_URL}/projects/10/ai`, { waitUntil: "networkidle" });
    await sleep(3000); // 等待建议卡片请求与历史问答加载
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, "10_zhaopeng_agent_suggestions.png"),
      fullPage: false,
    });
    console.log("  [Screenshot] 10_zhaopeng_agent_suggestions.png");

    // 4. 聚焦问答卡片上的 [S]/[G] 来源引用与证据链
    console.log("  -> 检查图谱增强回答与 [S]/[G] 来源引用与证据链核对");
    const citedAnswer = page.locator("text=[S1], text=[G1], text=项目资料 [S1]").first();
    if (await citedAnswer.count() > 0) {
      await citedAnswer.scrollIntoViewIfNeeded();
      await sleep(1000);
    }
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, "11_zhaopeng_kg_rag_qa_cited.png"),
      fullPage: false,
    });
    console.log("  [Screenshot] 11_zhaopeng_kg_rag_qa_cited.png");

    // 5. 切换到「图谱」页签，展示面向导师监督的语义可视化（17 类实体色板、尺寸、连线专属色）
    console.log("  -> 切换到「图谱」页签，加载实证图谱五通道语义可视化全景");
    await page.goto(`${BASE_URL}/projects/10/kg`, { waitUntil: "networkidle" });
    await sleep(4500); // 等待 ForceGraph2D 稳定
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, "12_zhaopeng_kg_semantic_vis.png"),
      fullPage: false,
    });
    console.log("  [Screenshot] 12_zhaopeng_kg_semantic_vis.png");

    // 6. 模拟悬停/聚焦操作，触发 Ego-Network 局部证据链聚焦（背景虚化）
    console.log("  -> 鼠标移动至图谱核心区域，触发局部关系聚焦与检视");
    const canvas = page.locator("canvas").first();
    if (await canvas.isVisible()) {
      const box = await canvas.boundingBox();
      if (box) {
        await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
        await sleep(1000);
        await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
        await sleep(2000);
      }
    }
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, "13_zhaopeng_kg_ego_network_focus.png"),
      fullPage: false,
    });
    console.log("  [Screenshot] 13_zhaopeng_kg_ego_network_focus.png");

    // 完成角色 3 录制
    await sleep(1000);
    const video = page.video();
    await context.close();
    if (video) {
      const videoPath = await video.path();
      const targetVideoPath = path.join(VIDEO_DIR, "03_zhaopeng_workflow.webm");
      if (fs.existsSync(videoPath)) {
        fs.renameSync(videoPath, targetVideoPath);
        console.log(`  [Video] 已保存录屏: ${targetVideoPath}`);
      }
    }
  }

  // =========================================================================
  // 角色 4: 王芳 (wangfang_lab / Lab@2026) - 只读成员
  // 重点验证: 权限边界与式(4-1)判定函数约束(无写操作、无管理/预警/审批页签)
  // =========================================================================
  console.log("\n>>> 开始模拟 角色 4: 王芳 (只读成员)");
  {
    const context = await browser.newContext({
      viewport: { width: 1920, height: 1080 },
      recordVideo: { dir: TEMP_VIDEO_DIR, size: { width: 1920, height: 1080 } },
    });
    const page = await context.newPage();

    // 1. 登录
    await loginUser(page, "wangfang_lab", "Lab@2026");

    // 2. 进入项目 10，查看受限制的页面边界
    console.log("  -> 进入项目 10，检验权限隔离与受限视图");
    await page.goto(`${BASE_URL}/projects/10`, { waitUntil: "networkidle" });
    await sleep(2000);

    // 检查是否无「新建笔记」按钮、无「审批」/「预警」/「设置」页签
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, "14_wangfang_readonly_boundary.png"),
      fullPage: false,
    });
    console.log("  [Screenshot] 14_wangfang_readonly_boundary.png");

    // 完成角色 4 录制
    await sleep(1000);
    const video = page.video();
    await context.close();
    if (video) {
      const videoPath = await video.path();
      const targetVideoPath = path.join(VIDEO_DIR, "04_wangfang_workflow.webm");
      if (fs.existsSync(videoPath)) {
        fs.renameSync(videoPath, targetVideoPath);
        console.log(`  [Video] 已保存录屏: ${targetVideoPath}`);
      }
    }
  }

  // =========================================================================
  // 角色 5: 系统管理员 (admin / admin123)
  // 重点验证: 全链路可追溯性闭环(项目级与全局审计日志流水)
  // =========================================================================
  console.log("\n>>> 开始模拟 角色 5: 系统管理员 (admin)");
  {
    const context = await browser.newContext({
      viewport: { width: 1920, height: 1080 },
      recordVideo: { dir: TEMP_VIDEO_DIR, size: { width: 1920, height: 1080 } },
    });
    const page = await context.newPage();

    // 1. 登录
    await loginUser(page, "admin", "admin123");

    // 2. 进入系统管理员控制台 (/admin)
    console.log("  -> 进入系统管理控制台 /admin");
    await page.goto(`${BASE_URL}/admin`, { waitUntil: "networkidle" });
    await sleep(2000);

    // 3. 点击「审计」Tab，呈现全流程操作留痕
    console.log("  -> 点击「审计」标签页，查看全链路追溯证据");
    const auditTabTrigger = page.getByRole("tab", { name: "审计" });
    if (await auditTabTrigger.isVisible()) {
      await auditTabTrigger.click();
      await sleep(2500);
    }
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, "15_admin_full_audit_log.png"),
      fullPage: false,
    });
    console.log("  [Screenshot] 15_admin_full_audit_log.png");

    // 完成角色 5 录制
    await sleep(1000);
    const video = page.video();
    await context.close();
    if (video) {
      const videoPath = await video.path();
      const targetVideoPath = path.join(VIDEO_DIR, "05_admin_workflow.webm");
      if (fs.existsSync(videoPath)) {
        fs.renameSync(videoPath, targetVideoPath);
        console.log(`  [Video] 已保存录屏: ${targetVideoPath}`);
      }
    }
  }

  await browser.close();

  // 清理临时视频目录（如有残留）
  try {
    fs.rmSync(TEMP_VIDEO_DIR, { recursive: true, force: true });
  } catch {}

  console.log("\n==================================================================");
  console.log("全部角色模拟走查、高清截图与操作录屏生成完毕！");
  console.log("==================================================================");
}

runSimulation().catch((err) => {
  console.error("执行模拟失败:", err);
  process.exit(1);
});
