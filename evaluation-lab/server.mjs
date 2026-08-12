import http from "node:http";
import { createHash, randomUUID } from "node:crypto";
import { readFile, stat } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const LAB_ROOT = path.dirname(fileURLToPath(import.meta.url));
const PROJECT_ROOT = path.resolve(LAB_ROOT, "..");
const DATA_ROOT = process.env.DATA_ROOT || path.join(PROJECT_ROOT, "data/real/GSE111619");
const PORT = Number(process.env.PORT || 4100);
const BACKEND_URL = (process.env.BACKEND_URL || "http://localhost:8001").replace(/\/$/, "");
const sessions = new Map();

const MIME_TYPES = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
};

function jsonHash(value) {
  return createHash("sha256").update(JSON.stringify(value)).digest("hex");
}

async function readJson(filePath) {
  return JSON.parse(await readFile(filePath, "utf8"));
}

function sendJson(response, status, payload, extraHeaders = {}) {
  const body = JSON.stringify(payload);
  response.writeHead(status, {
    "Content-Type": "application/json; charset=utf-8",
    "Cache-Control": "no-store",
    ...extraHeaders,
  });
  response.end(body);
}

function sendText(response, status, body, contentType = "text/plain; charset=utf-8") {
  response.writeHead(status, { "Content-Type": contentType });
  response.end(body);
}

async function readRequestBody(request) {
  const chunks = [];
  for await (const chunk of request) chunks.push(chunk);
  const text = Buffer.concat(chunks).toString("utf8");
  return text ? JSON.parse(text) : {};
}

function requestSession(request) {
  const cookie = request.headers.cookie || "";
  const match = cookie.match(/(?:^|;\s*)eval_session=([^;]+)/);
  return match ? sessions.get(match[1]) : null;
}

async function backendFetch(session, route, options = {}) {
  const headers = new Headers(options.headers || {});
  headers.set("Accept", "application/json");
  if (session?.token) headers.set("Authorization", `Bearer ${session.token}`);
  if (options.body !== undefined) headers.set("Content-Type", "application/json");
  const response = await fetch(`${BACKEND_URL}${route}`, {
    method: options.method || "GET",
    headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  });
  const text = await response.text();
  let payload;
  try {
    payload = text ? JSON.parse(text) : null;
  } catch {
    payload = { detail: text || `后端返回 ${response.status}` };
  }
  return { response, payload };
}

async function requireSession(request, response) {
  const session = requestSession(request);
  if (!session) {
    sendJson(response, 401, { detail: "请先登录评测实验室" });
    return null;
  }
  return session;
}

async function benchmarkSummary() {
  const holdoutPath = path.join(DATA_ROOT, "main_v8_kg_holdout_experiment_report.json");
  const retrievalPath = path.join(DATA_ROOT, "main-retrieval-evaluation/report.json");
  const agentPath = path.join(DATA_ROOT, "main_v8_agent_probe_report.json");
  const [holdout, retrieval, agent] = await Promise.all([
    readJson(holdoutPath),
    readJson(retrievalPath),
    readJson(agentPath),
  ]);
  const answerModes = holdout.objective_evaluation.mode_summary || [];
  const mode = (name) => answerModes.find((item) => item.mode === name) || null;
  return {
    generated_at: holdout.generated_at,
    dataset: {
      name: holdout.dataset,
      questions: holdout.selected_case_ids?.length || 0,
      question_set_file: holdout.question_set,
      repetitions: holdout.repetitions,
      seed: holdout.random_seed,
      evidence_level: holdout.evidence_level,
    },
    answer: {
      pure_llm: mode("pure_llm"),
      bm25_rag: mode("bm25_rag"),
      project_rag: mode("project_rag"),
      kg_enhanced_rag: mode("kg_enhanced_rag"),
      structured_query: mode("structured_query"),
      comparison: holdout.objective_evaluation.paired_comparison,
      limitations: holdout.objective_evaluation.limitations,
    },
    retrieval: {
      aggregate: retrieval.aggregate,
      ablation: retrieval.ablation,
      questions: retrieval.question_count,
      facts: retrieval.fact_count,
      reproducibility_verified: retrieval.reproducibility_verified,
      result_sha256: retrieval.result_sha256,
    },
    agent: {
      completed_runs: agent.completed_runs,
      failed_runs: agent.failed_runs,
      needs_review_runs: agent.needs_review_runs,
      invalid_citations: agent.invalid_citations,
      task_types: agent.task_types,
    },
    source_hash: jsonHash({ holdout: holdout.generated_at, retrieval: retrieval.result_sha256 }),
  };
}

async function serveStatic(request, response, pathname) {
  const requested = pathname === "/" ? "/index.html" : pathname;
  const filePath = path.resolve(LAB_ROOT, `.${requested}`);
  if (!filePath.startsWith(`${LAB_ROOT}${path.sep}`)) {
    sendText(response, 403, "Forbidden");
    return;
  }
  try {
    const fileStat = await stat(filePath);
    if (!fileStat.isFile()) throw new Error("not a file");
    const extension = path.extname(filePath);
    sendText(response, 200, await readFile(filePath), MIME_TYPES[extension] || "application/octet-stream");
  } catch {
    sendText(response, 404, "Not found");
  }
}

async function handleApi(request, response, pathname) {
  if (pathname === "/api/health") {
    sendJson(response, 200, { ok: true, backend_url: BACKEND_URL });
    return;
  }

  if (pathname === "/api/login" && request.method === "POST") {
    const body = await readRequestBody(request);
    const upstream = await backendFetch(null, "/auth/login", { method: "POST", body });
    if (!upstream.response.ok) {
      sendJson(response, upstream.response.status, upstream.payload);
      return;
    }
    const sessionId = randomUUID();
    sessions.set(sessionId, { token: upstream.payload.access_token, username: body.username });
    sendJson(response, 200, { username: body.username }, {
      "Set-Cookie": `eval_session=${sessionId}; HttpOnly; SameSite=Lax; Path=/`,
    });
    return;
  }

  if (pathname === "/api/logout" && request.method === "POST") {
    const cookie = request.headers.cookie || "";
    const match = cookie.match(/(?:^|;\s*)eval_session=([^;]+)/);
    if (match) sessions.delete(match[1]);
    sendJson(response, 200, { ok: true }, { "Set-Cookie": "eval_session=; Max-Age=0; HttpOnly; SameSite=Lax; Path=/" });
    return;
  }

  if (pathname === "/api/benchmark-summary" && request.method === "GET") {
    try {
      sendJson(response, 200, await benchmarkSummary());
    } catch (error) {
      sendJson(response, 500, { detail: error instanceof Error ? error.message : "读取评测基线失败" });
    }
    return;
  }

  const session = await requireSession(request, response);
  if (!session) return;

  if (pathname === "/api/me") {
    const upstream = await backendFetch(session, "/auth/me");
    sendJson(response, upstream.response.status, upstream.payload);
    return;
  }
  if (pathname === "/api/projects") {
    const upstream = await backendFetch(session, "/projects?skip=0&limit=100");
    sendJson(response, upstream.response.status, upstream.payload);
    return;
  }

  const projectMatch = pathname.match(/^\/api\/projects\/(\d+)\/(rag-status|query-logs)$/);
  if (projectMatch) {
    const projectId = projectMatch[1];
    const route = projectMatch[2] === "rag-status"
      ? `/projects/${projectId}/rag/status`
      : `/projects/${projectId}/rag/query-logs`;
    const upstream = await backendFetch(session, route);
    sendJson(response, upstream.response.status, upstream.payload);
    return;
  }

  const projectExperiments = pathname.match(/^\/api\/projects\/(\d+)\/experiments$/);
  if (projectExperiments) {
    const projectId = projectExperiments[1];
    const upstream = await backendFetch(session, `/projects/${projectId}/rag/experiments`, {
      method: request.method,
      body: request.method === "POST" ? await readRequestBody(request) : undefined,
    });
    sendJson(response, upstream.response.status, upstream.payload);
    return;
  }

  const queryMatch = pathname.match(/^\/api\/projects\/(\d+)\/query$/);
  if (queryMatch && request.method === "POST") {
    const projectId = queryMatch[1];
    const upstream = await backendFetch(session, `/projects/${projectId}/rag/query`, {
      method: "POST",
      body: await readRequestBody(request),
    });
    sendJson(response, upstream.response.status, upstream.payload);
    return;
  }

  sendJson(response, 404, { detail: "评测接口不存在" });
}

const server = http.createServer(async (request, response) => {
  try {
    const url = new URL(request.url || "/", `http://${request.headers.host || "localhost"}`);
    if (url.pathname.startsWith("/api/")) {
      await handleApi(request, response, url.pathname);
    } else {
      await serveStatic(request, response, url.pathname);
    }
  } catch (error) {
    sendJson(response, 500, { detail: error instanceof Error ? error.message : "评测实验室服务异常" });
  }
});

server.listen(PORT, "0.0.0.0", () => {
  console.log(`Evaluation lab listening on http://localhost:${PORT}`);
});
