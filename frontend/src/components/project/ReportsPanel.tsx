"use client";

import { BarChart } from "lucide-react";
import type { AgentGenerationRun } from "@/lib/api";
import { cardClass } from "../shared/utils";
import { agentTaskOptions } from "../constants";

interface ReportsPanelProps {
  agentDraft: { task_type: string; date_from: string; date_to: string };
  onAgentDraftChange: (draft: { task_type: string; date_from: string; date_to: string }) => void;
  agentRun: AgentGenerationRun | null;
  onAgentRunSelect: (run: AgentGenerationRun) => void;
  agentRuns: AgentGenerationRun[];
  agentBusy: boolean;
  selectedProjectId: number | null;
  onGenerate: () => void;
}

export function ReportsPanel({
  agentDraft,
  onAgentDraftChange,
  agentRun,
  onAgentRunSelect,
  agentRuns,
  agentBusy,
  selectedProjectId,
  onGenerate,
}: ReportsPanelProps) {
  if (!selectedProjectId) return null;

  return (
    <div className="grid gap-4">
      <div className={cardClass("p-5")}>
        <h2 className="flex items-center gap-2 font-semibold"><BarChart size={18} />智能生成</h2>
        <p className="mt-1 text-sm text-muted">基于已审核实验笔记、资料库和知识图谱生成可追溯草稿。</p>
        <div className="mt-4 grid gap-3 md:grid-cols-[1fr_150px_150px_auto]">
          <select
            className="rounded-md border border-border px-3 py-2 text-sm"
            value={agentDraft.task_type}
            onChange={(e) => onAgentDraftChange({ ...agentDraft, task_type: e.target.value })}
          >
            {agentTaskOptions.map((option) => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>
          <input
            type="date"
            className="rounded-md border border-border px-3 py-2 text-sm"
            value={agentDraft.date_from}
            onChange={(e) => onAgentDraftChange({ ...agentDraft, date_from: e.target.value })}
          />
          <input
            type="date"
            className="rounded-md border border-border px-3 py-2 text-sm"
            value={agentDraft.date_to}
            onChange={(e) => onAgentDraftChange({ ...agentDraft, date_to: e.target.value })}
          />
          <button
            disabled={agentBusy}
            onClick={onGenerate}
            className="rounded-md bg-brand px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-60"
          >
            {agentBusy ? "生成中..." : "生成"}
          </button>
        </div>
        {agentRun && (
          <div className="mt-4 rounded-md border border-border bg-surface px-3 py-3 text-sm">
            <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
              <span>任务：{agentTaskOptions.find((o) => o.value === agentRun.task_type)?.label || agentRun.task_type}</span>
              <span>耗时：{agentRun.response_ms} ms</span>
              <span>来源笔记：{agentRun.source_note_ids_json.length} 条</span>
              <span>来源资料：{agentRun.source_file_ids_json.length} 份</span>
              <span>图谱依据：{agentRun.source_graph_relation_ids_json.length} 条</span>
            </div>
            <h3 className="mt-3 font-semibold">{agentRun.title}</h3>
            <pre className="mt-2 whitespace-pre-wrap text-muted">{agentRun.body}</pre>
            {agentRun.message && <p className="mt-3 text-xs text-muted">{agentRun.message}</p>}
          </div>
        )}
      </div>

      <div className={cardClass("p-5")}>
        <h3 className="font-semibold">生成历史</h3>
        <div className="mt-4 max-h-80 space-y-2 overflow-auto">
          {agentRuns.length === 0 && <p className="text-sm text-muted">暂无智能体生成记录。</p>}
          {agentRuns.map((run) => (
            <button
              key={run.id}
              type="button"
              onClick={() => onAgentRunSelect(run)}
              className={`w-full rounded-md border px-3 py-2 text-left text-sm ${agentRun?.id === run.id ? "border-brand bg-[#eef8f6]" : "border-border hover:bg-surface"}`}
            >
              <span className="block font-medium">{run.title}</span>
              <span className="mt-1 block text-xs text-muted">
                {new Date(run.created_at).toLocaleString()} · {agentTaskOptions.find((o) => o.value === run.task_type)?.label || run.task_type} ·
                笔记 {run.source_note_ids_json.length} · 图谱 {run.source_graph_relation_ids_json.length}
              </span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
