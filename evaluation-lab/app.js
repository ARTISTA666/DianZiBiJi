const state = { summary: null, projects: [], projectId: null, run: null };

const $ = (id) => document.getElementById(id);
const formatPercent = (value) => `${(Number(value || 0) * 100).toFixed(1)}%`;
const formatMs = (value) => `${Math.round(Number(value || 0))} ms`;
const modeLabel = { pure_llm: "纯 LLM", bm25_rag: "BM25 RAG", project_rag: "普通 RAG", structured_query: "结构化查询", kg_enhanced_rag: "图谱增强 RAG", hybrid_rag: "混合 RAG", graph_enhanced_rag: "图谱增强检索" };

async function api(path, options = {}) {
  const response = await fetch(path, { credentials: "include", ...options, headers: { "Content-Type": "application/json", ...(options.headers || {}) } });
  const text = await response.text();
  let payload = null;
  try { payload = text ? JSON.parse(text) : null; } catch { payload = { detail: text }; }
  if (!response.ok) throw new Error(payload?.detail || `请求失败：${response.status}`);
  return payload;
}

function showError(error) { $("global-error").textContent = error?.message || String(error); }

function metricCard(label, value, detail, className = "") {
  return `<div class="metric-card"><div class="label">${label}</div><div class="value ${className}">${value}</div><div class="delta">${detail || ""}</div></div>`;
}

function renderBaseline(summary) {
  state.summary = summary;
  const plain = summary.answer.project_rag;
  const kg = summary.answer.kg_enhanced_rag;
  const retrievalPlain = summary.retrieval.aggregate.find((row) => row.mode === "hybrid_rag");
  const retrievalKg = summary.retrieval.aggregate.find((row) => row.mode === "graph_enhanced_rag");
  const accuracyDelta = (kg.closed_set_exact_case_accuracy - plain.closed_set_exact_case_accuracy) * 100;
  const recallDelta = (retrievalKg["Recall@10"] - retrievalPlain["Recall@10"]) * 100;
  $("baseline-meta").textContent = `冻结基线：${summary.dataset.name} · ${summary.dataset.questions} 题 · ${summary.dataset.repetitions} 次重复 · 随机种子 ${summary.dataset.seed} · 生成于 ${summary.generated_at}`;
  $("headline-cards").innerHTML = [
    metricCard("图谱增强精确案例率", formatPercent(kg.closed_set_exact_case_accuracy), `普通 RAG ${formatPercent(plain.closed_set_exact_case_accuracy)}，提升 ${accuracyDelta.toFixed(1)} 个百分点`, "positive"),
    metricCard("图谱增强 Recall@10", formatPercent(retrievalKg["Recall@10"]), `普通混合 RAG ${formatPercent(retrievalPlain["Recall@10"])}，提升 ${recallDelta.toFixed(1)} 个百分点`, "positive"),
    metricCard("图谱增强 F1", kg.closed_set_fact_f1.toFixed(3), `普通 RAG ${plain.closed_set_fact_f1.toFixed(3)}`),
    metricCard("响应耗时", formatMs(kg.mean_response_ms), `普通 RAG ${formatMs(plain.mean_response_ms)}，增加 ${formatMs(kg.mean_response_ms - plain.mean_response_ms)}`, "warning"),
  ].join("");

  const answerRows = ["pure_llm", "project_rag", "kg_enhanced_rag"].map((name) => {
    const item = summary.answer[name];
    return `<tr><td>${modeLabel[name]}</td><td>${formatPercent(item.micro_fact_coverage)}</td><td>${item.closed_set_fact_f1.toFixed(3)}</td><td>${formatPercent(item.closed_set_exact_case_accuracy)}</td><td>${formatMs(item.mean_response_ms)}</td><td>${item.avg_graph_hit_count.toFixed(1)}</td></tr>`;
  }).join("");
  $("answer-table").innerHTML = `<table class="data-table"><thead><tr><th>模式</th><th>事实覆盖</th><th>F1</th><th>精确案例率</th><th>平均耗时</th><th>平均图谱命中</th></tr></thead><tbody>${answerRows}</tbody></table>`;

  const retrievalRows = summary.retrieval.aggregate.map((row) => `<tr><td>${modeLabel[row.mode] || row.mode}</td><td>${formatPercent(row["Recall@1"])}</td><td>${formatPercent(row["Recall@5"])}</td><td>${formatPercent(row["Recall@10"])}</td><td>${row.MRR.toFixed(3)}</td><td>${row["nDCG@10"].toFixed(3)}</td></tr>`).join("");
  $("retrieval-table").innerHTML = `<table class="data-table"><thead><tr><th>检索模式</th><th>R@1</th><th>R@5</th><th>R@10</th><th>MRR</th><th>nDCG@10</th></tr></thead><tbody>${retrievalRows}</tbody></table>`;

  $("explanation-cards").innerHTML = [
    ["图谱为什么更好", `图谱增强把 Recall@10 从 ${formatPercent(retrievalPlain["Recall@10"])} 提高到 ${formatPercent(retrievalKg["Recall@10"])}。这说明差异首先来自“找到了更多相关证据”，而不是单纯让模型更会写。`],
    ["RAG 为什么比纯 LLM 更准", `纯 LLM 的闭集事实覆盖为 ${formatPercent(summary.answer.pure_llm.micro_fact_coverage)}；普通 RAG 为 ${formatPercent(plain.micro_fact_coverage)}。资料被送入上下文后，回答从记忆生成变成基于项目证据生成。`],
    ["代价和风险", `图谱增强平均耗时 ${formatMs(kg.mean_response_ms)}，比普通 RAG 多 ${formatMs(kg.mean_response_ms - plain.mean_response_ms)}；因此论文中应同时报告准确性、延迟和失败案例。`],
  ].map(([title, text]) => `<div class="explanation"><b>${title}</b><span>${text}</span></div>`).join("");
}

function selectedProjectId() { return Number($("project-select").value || state.projectId || 1); }

async function loadProjects() {
  const payload = await api("/api/projects");
  state.projects = payload.items || [];
  $("project-select").innerHTML = state.projects.map((project) => `<option value="${project.id}">${project.name}（${project.id}）</option>`).join("");
  if (state.projectId) $("project-select").value = String(state.projectId);
  state.projectId = state.projects.some((project) => project.id === 1) ? 1 : selectedProjectId();
  $("project-select").value = String(state.projectId);
  await loadExperiments();
}

async function loadExperiments() {
  if (!state.projectId) return;
  const runs = await api(`/api/projects/${state.projectId}/experiments`);
  $("experiment-list").innerHTML = (runs || []).slice(0, 12).map((run) => `<div class="run-item"><div><strong>${run.name}</strong><small>${run.status} · ${run.completed_cases || 0}/${run.total_cases || 0} 个案例 · ${new Date(run.created_at).toLocaleString("zh-CN")}</small></div><span class="chip">#${run.id}</span></div>`).join("") || `<p class="muted">暂无实验记录。</p>`;
}

async function pollRun(runId) {
  for (let attempt = 0; attempt < 180; attempt += 1) {
    const runs = await api(`/api/projects/${state.projectId}/experiments`);
    const run = (runs || []).find((item) => item.id === runId);
    if (run && ["completed", "completed_with_errors", "failed", "interrupted"].includes(run.status)) return run;
    $("experiment-status").textContent = `实验运行中… ${run?.completed_cases || 0}/${run?.total_cases || 0}`;
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  throw new Error("实验运行超过 3 分钟，请到最近实验中查看状态");
}

async function handleExperiment(event) {
  event.preventDefault();
  $("experiment-status").textContent = "正在提交…";
  const modes = [...document.querySelectorAll(".mode-list input:checked")].map((input) => input.value);
  const questions = $("experiment-questions").value.split("\n").map((item) => item.trim()).filter(Boolean);
  if (!modes.length || !questions.length) throw new Error("至少选择一种模式并填写一道题");
  const run = await api(`/api/projects/${selectedProjectId()}/experiments`, { method: "POST", body: JSON.stringify({ name: $("experiment-name").value, questions, modes, repetitions: Number($("experiment-repetitions").value) || 1, randomize_order: true, random_seed: Number($("experiment-seed").value) || null }) });
  const finalRun = await pollRun(run.id);
  $("experiment-status").textContent = `实验 #${finalRun.id} 已${finalRun.status === "completed" ? "完成" : "结束"}`;
  await loadExperiments();
}

async function handleQuery(event) {
  event.preventDefault();
  $("query-result").textContent = "正在请求原系统…";
  const payload = await api(`/api/projects/${selectedProjectId()}/query`, { method: "POST", body: JSON.stringify({ query: $("query-text").value, mode: $("query-mode").value }) });
  const sourceCount = payload.sources?.length || 0;
  const graphCount = payload.graph_context?.length || 0;
  $("query-result").classList.remove("empty");
  $("query-result").innerHTML = `<div class="query-meta"><span class="chip">${modeLabel[payload.rag_mode] || payload.rag_mode}</span><span class="chip">来源 ${sourceCount}</span><span class="chip">图谱命中 ${graphCount}</span><span class="chip">耗时 ${formatMs(payload.response_ms)}</span><span class="chip">模型 ${payload.model_name || payload.provider || "系统"}</span></div><strong>回答</strong><p>${(payload.answer || "无回答").replaceAll("\n", "<br />")}</p>`;
}

async function enterApp(username) {
  $("login-view").classList.add("hidden");
  $("app-view").classList.remove("hidden");
  $("logout-button").classList.remove("hidden");
  $("session-label").textContent = username;
  try { await loadProjects(); } catch (error) { showError(error); }
}

async function init() {
  try { renderBaseline(await api("/api/benchmark-summary")); } catch (error) { showError(error); }
  try {
    const me = await api("/api/me");
    await enterApp(me.username || "已登录");
  } catch { /* 未登录时显示登录框 */ }
}

$("login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  $("login-error").textContent = "";
  try {
    const result = await api("/api/login", { method: "POST", body: JSON.stringify({ username: $("username").value, password: $("password").value }) });
    await enterApp(result.username);
  } catch (error) { $("login-error").textContent = error.message; }
});
$("logout-button").addEventListener("click", async () => { await api("/api/logout", { method: "POST" }); window.location.reload(); });
$("project-select").addEventListener("change", async () => { state.projectId = selectedProjectId(); await loadExperiments(); });
$("refresh-experiments").addEventListener("click", () => loadExperiments().catch(showError));
$("experiment-form").addEventListener("submit", (event) => handleExperiment(event).catch(showError));
$("query-form").addEventListener("submit", (event) => handleQuery(event).catch(showError));
document.querySelectorAll(".tab").forEach((button) => button.addEventListener("click", () => {
  document.querySelectorAll(".tab").forEach((item) => item.classList.toggle("active", item === button));
  document.querySelectorAll(".tab-panel").forEach((panel) => panel.classList.toggle("active", panel.id === `tab-${button.dataset.tab}`));
}));
init();
