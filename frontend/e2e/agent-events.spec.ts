import { expect, type Page, test } from "@playwright/test";
import { createServer, type Server } from "node:http";

// Run against an isolated frontend built with NEXT_PUBLIC_NEW_AGENT_ENABLED=true
// and NEXT_PUBLIC_API_BASE_URL=/t148-api. Business APIs are intercepted here;
// EventSource uses a disposable loopback HTTP server and the native SSE parser.
test.describe("Agent durable-event replay", () => {
  test.skip(process.env.E2E_AGENT_MOCK !== "1", "Requires the isolated mock API frontend");

  type Event = { id: string; event: string; data: Record<string, unknown> };
  const servers: Server[] = [];
  test.afterEach(async () => {
    for (const server of servers.splice(0)) {
      server.closeAllConnections();
      await new Promise<void>((resolve) => server.close(() => resolve()));
    }
  });

  const sessionId = "00000000-0000-4000-8000-000000000148";
  const actionId = "00000000-0000-4000-8000-000000000149";
  const requiredAction = { tool: "write", status: "awaiting_confirmation", result: { structuredContent: { pending_action_id: actionId } } };
  const snapshot = {
    session: { id: sessionId, project_id: null, status: "completed", provider: "mock", model_name: "mock", prompt_version: "test", usage: {} },
    messages: [{ id: 1, role: "assistant", content: "模拟工具结果。", metadata: {} }],
    steps: [],
    pending_actions: [],
  };

  async function openAgent(page: Page, streams: Event[][], options?: {
    approvalStatus?: number; rejected?: boolean; deepPlanStatus?: number; deferEvents?: boolean;
    pendingActions?: { id: string; tool_name: string; arguments_summary: string; status: string; expires_at: string }[];
  }) {
    const calls = { turns: 0, start: 0, approve: 0, reject: 0, mockWrites: 0, cursors: [] as string[], approvedActions: [] as string[] };
    let releaseEvents!: () => void;
    const eventsReady = new Promise<void>((resolve) => { releaseEvents = resolve; });
    if (!options?.deferEvents) releaseEvents();
    const server = createServer((request, response) => {
      const index = calls.cursors.length;
      calls.cursors.push(String(request.headers["last-event-id"] || ""));
      response.writeHead(200, {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "Access-Control-Allow-Origin": new URL(page.url()).origin,
        "Access-Control-Allow-Credentials": "true",
      });
      response.flushHeaders();
      void eventsReady.then(() => {
        if (!response.destroyed) response.end(`retry: ${index + 1 < streams.length ? 50 : 10000}\n\n` + (streams[index] || []).map((event) => `id: ${event.id}\nevent: ${event.event}\ndata: ${JSON.stringify(event.data)}\n\n`).join(""));
      });
    });
    await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
    servers.push(server);
    const address = server.address();
    if (!address || typeof address === "string") throw new Error("Mock SSE server did not listen");
    // Keep the browser's native SSE parser/reconnection logic. Only its URL is
    // redirected to this disposable loopback server; no events are synthesized.
    await page.addInitScript((streamUrl) => {
      const NativeEventSource = window.EventSource;
      window.EventSource = class extends NativeEventSource {
        constructor(url: string | URL, options?: EventSourceInit) {
          super(new URL(String(url), location.href).pathname.endsWith("/events") ? streamUrl : url, options);
        }
      };
    }, `http://127.0.0.1:${address.port}/events`);
    await page.route("**/t148-api/**", async (route) => {
      const request = route.request();
      const pathname = new URL(request.url()).pathname.replace("/t148-api", "");
      let data: unknown = [];
      let status = 200;
      if (pathname === "/auth/me") {
        data = { id: 148, username: "mock-reviewer", display_name: "模拟账号", role: "member" };
      } else if (pathname === "/projects") {
        data = { items: [], total: 0, skip: 0, limit: 20 };
      } else if (pathname === "/api/agent/sessions") {
        data = snapshot;
      } else if (pathname.endsWith("/turns")) {
        calls.turns += 1;
        data = options?.deepPlanStatus
          ? { turn_id: sessionId, status: "awaiting_plan_approval", plan: { text: "模拟待确认计划" }, plan_hash: "hash", budget: {} }
          : { ...snapshot, pending_actions: options?.pendingActions ?? (options?.approvalStatus ? [{ id: actionId, tool_name: "write", arguments_summary: "模拟写入", status: "pending", expires_at: "2099-01-01T00:00:00Z" }] : []) };
        if (!options) calls.mockWrites += 1;
      } else if (pathname.endsWith("/start")) {
        calls.start += 1;
        status = options?.deepPlanStatus || 200;
        data = { detail: "Agent prompt changed; cancel this turn and request a new plan preview" };
      } else if (pathname.endsWith("/approve")) {
        calls.approve += 1;
        calls.approvedActions.push(pathname.split("/").at(-2)!);
        status = options?.approvalStatus || 200;
        data = status === 200
          ? { id: calls.approvedActions.at(-1), tool: "write", status: "completed", execution_status: "completed" }
          : { detail: status === 409 ? "Pending action is expired, replayed, or unavailable" : "Forbidden: permission withdrawn" };
        if (status === 200) calls.mockWrites += 1;
      } else if (pathname.endsWith("/reject")) {
        calls.reject += 1;
        data = { id: actionId, tool: "write", status: "rejected" };
      }
      await route.fulfill({ status, json: data });
    });
    await page.goto("/projects");
    await page.getByRole("button", { name: "打开 Agent 助手", exact: true }).click();
    const assistant = page.getByRole("region", { name: "Agent 助手", exact: true });
    if (options?.deepPlanStatus) await assistant.getByLabel("Agent 模式").selectOption("deep");
    await assistant.getByLabel("输入 Agent 指令").fill("执行模拟工具");
    await assistant.getByRole("button", { name: "发送", exact: true }).click();
    await expect(assistant.getByText(options?.deepPlanStatus ? "深度计划待确认" : "模拟工具结果。", { exact: true })).toBeVisible();
    return { assistant, calls, releaseEvents };
  }

  test("native expiry of the last confirmation removes its queue and allows another turn", async ({ page }) => {
    const { assistant, calls, releaseEvents } = await openAgent(page, [[
      { id: "1", event: "confirmation.required", data: requiredAction },
      { id: "2", event: "confirmation.expired", data: { action_id: actionId, turn_id: sessionId, terminal: true } },
    ]], { approvalStatus: 200, deferEvents: true });
    releaseEvents();
    await expect(assistant.getByText("高风险操作已过期，未执行工具", { exact: true })).toBeVisible();
    await expect(assistant.getByText("等待确认高风险操作", { exact: true })).toHaveCount(0);
    await expect(assistant.getByText("事件连接中断，正在重连；操作不会自动重试", { exact: true })).toHaveCount(0);
    await assistant.getByRole("button", { name: "执行轨迹（1 步）", exact: true }).click();
    await expect(assistant.getByText("确认已过期，未执行工具", { exact: true })).toBeVisible();
    await expect(assistant.locator("ol li .bg-rose-500")).toHaveCount(1);
    await assistant.getByLabel("输入 Agent 指令").fill("发送另一条指令");
    await assistant.getByRole("button", { name: "发送", exact: true }).click();
    await expect.poll(() => calls.turns).toBe(2);
    expect({ approve: calls.approve, mockWrites: calls.mockWrites }).toEqual({ approve: 0, mockWrites: 0 });
  });

  test("native expiry of one confirmation leaves the next queued action operable", async ({ page }) => {
    const otherId = "00000000-0000-4000-8000-000000000150";
    const { assistant, calls, releaseEvents } = await openAgent(page, [[
      { id: "1", event: "confirmation.required", data: requiredAction },
      { id: "2", event: "confirmation.required", data: { action_id: otherId, tool: "other_write" } },
      { id: "3", event: "confirmation.expired", data: { action_id: actionId, turn_id: sessionId, terminal: false } },
    ]], { deferEvents: true, pendingActions: [
      { id: actionId, tool_name: "write", arguments_summary: "第一项", status: "pending", expires_at: "2099-01-01T00:00:00Z" },
      { id: otherId, tool_name: "other_write", arguments_summary: "第二项", status: "pending", expires_at: "2099-01-01T00:00:00Z" },
    ] });
    releaseEvents();
    await assistant.getByRole("button", { name: "执行轨迹（2 步）", exact: true }).click();
    await expect(assistant.locator("ol li .bg-rose-500")).toHaveCount(1);
    await expect(assistant.locator("ol li .bg-amber-400")).toHaveCount(1);
    await expect(assistant.getByText(/确认执行 other_write（第二项）/)).toBeVisible();
    await assistant.getByLabel("输入 Agent 指令").fill("确认");
    await assistant.getByRole("button", { name: "发送", exact: true }).click();
    await expect.poll(() => calls.approvedActions).toEqual([otherId]);
    await expect(assistant.getByText("other_write 已执行完成。", { exact: true })).toBeVisible();
    expect({ approve: calls.approve, mockWrites: calls.mockWrites, turns: calls.turns }).toEqual({ approve: 1, mockWrites: 1, turns: 1 });
  });

  test("native reconnect preserves the cursor and replayed IDs do not duplicate UI or writes", async ({ page }) => {
    const first: Event[] = [
      { id: "1", event: "plan.preview", data: { plan: { text: "模拟研究计划" } } },
      { id: "1", event: "plan.preview", data: { plan: { text: "模拟研究计划" } } },
      { id: "2", event: "tool.started", data: { step_id: 1, tool: "write", arguments_summary: "第一次调用" } },
      { id: "3", event: "tool.completed", data: { step_id: 1, tool: "write", status: "completed" } },
    ];
    const second: Event[] = [
      ...first,
      { id: "9007199254740992", event: "tool.started", data: { step_id: 2, tool: "write", arguments_summary: "第二次独立调用" } },
      { id: "9007199254740993", event: "tool.completed", data: { step_id: 2, tool: "write", status: "already_completed" } },
      { id: "9007199254740994", event: "tool.started", data: { step_id: 3, tool: "failed_write" } },
      { id: "9007199254740995", event: "tool.failed", data: { step_id: 3, tool: "failed_write", status: "failed" } },
      { id: "9007199254740996", event: "turn.completed", data: { status: "completed", terminal: true } },
    ];
    const { assistant, calls } = await openAgent(page, [first, second]);
    await expect.poll(() => calls.cursors.length).toBe(2);
    await expect(assistant.getByRole("button", { name: "执行轨迹（4 步）", exact: true })).toBeVisible();
    expect(calls.cursors).toEqual(["", "3"]);
    await assistant.getByRole("button", { name: "执行轨迹（4 步）", exact: true }).click();
    await expect(assistant.getByText("调用 write", { exact: true })).toHaveCount(2);
    await expect(assistant.getByText("此前已完成，本次未执行", { exact: true })).toBeVisible();
    await expect(assistant.getByText("工具执行失败，未确认本次操作成功", { exact: true })).toBeVisible();
    await expect(assistant.locator("ol li .bg-rose-500")).toHaveCount(1);
    await expect(assistant.locator("ol li .animate-pulse")).toHaveCount(0);
    await expect(assistant.getByText("服务端 Agent 发生错误", { exact: true })).toHaveCount(0);
    await expect(assistant.getByText("事件连接中断，正在重连；操作不会自动重试", { exact: true })).toHaveCount(0);
    expect({ turns: calls.turns, mockWrites: calls.mockWrites }).toEqual({ turns: 1, mockWrites: 1 });
  });

  test("a stale deep plan is refused without an index-error message, write or retry", async ({ page }) => {
    const { assistant, calls } = await openAgent(page, [[
      { id: "1", event: "plan.preview", data: { plan: { text: "模拟待确认计划" } } },
    ]], { deepPlanStatus: 409 });
    await assistant.getByRole("button", { name: "确认执行", exact: true }).click();
    await expect(assistant.getByText("计划已变更、已处理或不可用；本次未执行，请重新生成计划。", { exact: true })).toBeVisible();
    await expect(assistant.getByText(/知识库索引状态已失效/)).toHaveCount(0);
    expect({ start: calls.start, mockWrites: calls.mockWrites, turns: calls.turns }).toEqual({ start: 1, mockWrites: 0, turns: 1 });
  });

  test("legacy string IDs stay distinct; events without an ID are not collapsed", async ({ page }) => {
    const events: Event[] = [
      { id: "step:41", event: "tool.started", data: { tool: "first" } },
      { id: "step:41", event: "tool.started", data: { tool: "first" } },
      { id: "step:42", event: "tool.started", data: { tool: "second" } },
      { id: "step:42", event: "tool.started", data: { tool: "second" } },
      { id: "", event: "plan.preview", data: { plan: { text: "无ID事件A" } } },
      { id: "", event: "plan.preview", data: { plan: { text: "无ID事件B" } } },
    ];
    // An explicit empty id resets EventSource.lastEventId rather than inheriting
    // the preceding event's id, as required by the SSE wire protocol.
    const { assistant } = await openAgent(page, [events]);
    await expect(assistant.getByRole("button", { name: "执行轨迹（4 步）", exact: true })).toBeVisible();
  });

  for (const approvalStatus of [409, 403]) {
    test(`confirmation ${approvalStatus === 409 ? "expiry" : "permission withdrawal"} causes no write or automatic retry`, async ({ page }) => {
      const { assistant, calls } = await openAgent(page, [[
        { id: "1", event: "confirmation.required", data: requiredAction },
      ]], { approvalStatus });
      await assistant.getByLabel("输入 Agent 指令").fill("确认");
      await assistant.getByRole("button", { name: "发送", exact: true }).click();
      const message = approvalStatus === 409 ? "确认已过期、已处理或不可用；本次确认未成功，请查看会话记录。" : "当前账号没有执行这项操作的权限，后端已拒绝请求；没有产生写入。";
      await expect(assistant.getByText(message, { exact: true })).toBeVisible();
      await expect(assistant.getByText("等待确认高风险操作", { exact: true })).toHaveCount(0);
      expect({ approve: calls.approve, mockWrites: calls.mockWrites, turns: calls.turns }).toEqual({ approve: 1, mockWrites: 0, turns: 1 });
    });
  }

  test("a rejection event closes the waiting trajectory without displaying success", async ({ page }) => {
    const { assistant, calls } = await openAgent(page, [[
      { id: "1", event: "confirmation.required", data: requiredAction },
      { id: "2", event: "confirmation.rejected", data: { action_id: actionId } },
    ]], { rejected: true });
    await expect(assistant.getByText("高风险操作已取消，未执行工具", { exact: true })).toBeVisible();
    await expect(assistant.getByText("等待确认高风险操作", { exact: true })).toHaveCount(0);
    expect(calls.mockWrites).toBe(0);
  });

  test("a completed confirmation replay does not claim a new write", async ({ page }) => {
    const { assistant, calls } = await openAgent(page, [[
      { id: "1", event: "confirmation.required", data: requiredAction },
      { id: "2", event: "confirmation.completed", data: { action_id: actionId, replayed: true } },
    ]], { rejected: true });
    await expect(assistant.getByText("此前已完成，本次未执行", { exact: true })).toBeVisible();
    await expect(assistant.getByText("服务端 Agent 发生错误", { exact: true })).toHaveCount(0);
    expect({ approve: calls.approve, mockWrites: calls.mockWrites }).toEqual({ approve: 0, mockWrites: 0 });
  });

  test("a server error message remains a failure after normal stream EOF", async ({ page }) => {
    const { assistant } = await openAgent(page, [[
      { id: "1", event: "tool.started", data: { step_id: 1, tool: "write" } },
      { id: "2", event: "error", data: { reason: "timed_out" } },
    ]], { rejected: true });
    await expect(assistant.getByText("服务端 Agent 发生错误", { exact: true })).toBeVisible();
    await assistant.getByRole("button", { name: "执行轨迹（1 步）", exact: true }).click();
    await expect(assistant.locator("ol li .bg-rose-500")).toHaveCount(1);
    await expect(assistant.locator("ol li .bg-emerald-500")).toHaveCount(0);
  });

  test("completing one pending action keeps the other confirmation waiting", async ({ page }) => {
    const otherId = "00000000-0000-4000-8000-000000000150";
    const { assistant } = await openAgent(page, [[
      { id: "1", event: "confirmation.required", data: requiredAction },
      { id: "2", event: "confirmation.required", data: { tool: "other_write", result: { structuredContent: { pending_action_id: otherId } } } },
      { id: "3", event: "confirmation.completed", data: { action_id: actionId, replayed: true } },
    ]], { rejected: true });
    await assistant.getByRole("button", { name: "执行轨迹（2 步）", exact: true }).click();
    const entries = assistant.locator("ol li");
    await expect(entries.nth(0).locator(".bg-emerald-500")).toHaveCount(1);
    await expect(entries.nth(1).locator(".bg-amber-400")).toHaveCount(1);
    await expect(entries.nth(1).getByText("此前已完成，本次未执行", { exact: true })).toHaveCount(0);
  });

  test("switching project while session creation is pending never sends a turn to the old session", async ({ page }) => {
    const projects = [1, 2].map((id) => ({ id, name: `Race project ${id}`, status: "active", is_sensitive: false, owner_user_id: 148 }));
    const sessionProjects: number[] = [];
    const turnSessions: string[] = [];
    let releaseOldSession: () => void = () => {};
    let oldResponseSent = false;
    const oldSessionGate = new Promise<void>((resolve) => { releaseOldSession = resolve; });
    await page.route("**/t148-api/**", async (route) => {
      const request = route.request();
      const pathname = new URL(request.url()).pathname.replace("/t148-api", "");
      let data: unknown = [];
      if (pathname === "/auth/me") {
        data = { id: 148, username: "race-reviewer", display_name: "模拟账号", role: "super_admin" };
      } else if (pathname === "/projects") {
        data = { items: projects, total: 2, skip: 0, limit: 20 };
      } else if (/^\/projects\/\d+$/.test(pathname)) {
        data = projects.find((project) => project.id === Number(pathname.split("/")[2]));
      } else if (pathname.endsWith("/members")) {
        data = [{ user_id: 148, can_read: true, can_write: true, can_review: true, can_manage: true }];
      } else if (pathname.endsWith("/notes") || pathname.endsWith("/files")) {
        data = { items: [], total: 0, skip: 0, limit: 200 };
      } else if (pathname.endsWith("/rag/status")) {
        data = { initialized: false };
      } else if (pathname === "/api/agent/sessions") {
        const projectId = request.postDataJSON().project_id as number;
        sessionProjects.push(projectId);
        if (projectId === 1) await oldSessionGate;
        data = { ...snapshot, session: { ...snapshot.session, id: `race-session-${projectId}`, project_id: projectId } };
        if (projectId === 1) oldResponseSent = true;
      } else if (pathname.endsWith("/turns")) {
        const id = pathname.split("/")[4];
        turnSessions.push(id);
        data = { ...snapshot, session: { ...snapshot.session, id }, messages: [{ role: "assistant", content: `Result ${id}` }] };
      } else if (pathname.endsWith("/events")) {
        await route.fulfill({ status: 200, contentType: "text/event-stream", body: ": connected\n\n" });
        return;
      }
      await route.fulfill({ status: 200, json: data });
    });
    await page.goto("/projects/1");
    await expect(page.getByRole("button", { name: "Race project 1", exact: true })).toBeVisible();
    await page.getByRole("button", { name: "打开 Agent 助手", exact: true }).click();
    const assistant = page.getByRole("region", { name: "Agent 助手", exact: true });
    await assistant.getByLabel("输入 Agent 指令").fill("A request");
    await assistant.getByRole("button", { name: "发送", exact: true }).click();
    await expect.poll(() => sessionProjects).toEqual([1]);
    await page.getByRole("button", { name: "Race project 1", exact: true }).click();
    await page.getByRole("menuitem", { name: "Race project 2", exact: true }).click();
    await expect(page.getByRole("button", { name: "Race project 2", exact: true })).toBeVisible();
    releaseOldSession();
    await expect.poll(() => oldResponseSent).toBe(true);
    if (!await assistant.isVisible()) await page.getByRole("button", { name: "打开 Agent 助手", exact: true }).click();
    await assistant.getByLabel("输入 Agent 指令").fill("B request");
    await assistant.getByRole("button", { name: "发送", exact: true }).click();
    await expect(assistant.getByText("Result race-session-2", { exact: true })).toBeVisible();
    expect(sessionProjects).toEqual([1, 2]);
    expect(turnSessions).toEqual(["race-session-2"]);
  });
});
