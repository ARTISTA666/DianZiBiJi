"use client";

import type { Project, KnowledgeGraph } from "@/lib/api";
import { cardClass } from "../shared/utils";
import { projectTabs } from "../constants";
import type { ProjectTab } from "../constants";

interface ProjectHeaderProps {
  selectedProject: Project | null;
  activeProjectTab: ProjectTab;
  onTabChange: (tab: ProjectTab) => void;
  kgEntityCount: number;
  kgRelationCount: number;
  queryLogCount: number;
  agentRunCount: number;
}

export function ProjectHeader({
  selectedProject,
  activeProjectTab,
  onTabChange,
  kgEntityCount,
  kgRelationCount,
  queryLogCount,
  agentRunCount,
}: ProjectHeaderProps) {
  return (
    <div className={cardClass("overflow-hidden")}>
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0 p-5">
          <h2 className="truncate text-lg font-semibold">{selectedProject?.name || "请选择项目"}</h2>
          <p className="mt-1 text-sm text-muted">
            {selectedProject?.description || "项目笔记、附件和审批会在这里汇总。"}
          </p>
          <div className="mt-3 flex flex-wrap gap-2 text-xs text-muted">
            <span className="rounded-md border border-border px-2 py-1">
              {selectedProject?.approval_enabled ? "启用审批" : "未启用审批"}
            </span>
            <span className="rounded-md border border-border px-2 py-1">
              {selectedProject?.is_sensitive ? "敏感项目" : "普通项目"}
            </span>
            <span className="rounded-md border border-border px-2 py-1">
              {selectedProject?.status || "active"}
            </span>
          </div>
        </div>
        <div className="grid shrink-0 grid-cols-2 gap-3 p-5 text-sm sm:grid-cols-4 lg:w-[420px]">
          <div className="rounded-md border border-border bg-surface px-3 py-2">
            <p className="text-xs text-muted">图谱实体</p>
            <p className="mt-1 font-semibold">{kgEntityCount}</p>
          </div>
          <div className="rounded-md border border-border bg-surface px-3 py-2">
            <p className="text-xs text-muted">图谱关系</p>
            <p className="mt-1 font-semibold">{kgRelationCount}</p>
          </div>
          <div className="rounded-md border border-border bg-surface px-3 py-2">
            <p className="text-xs text-muted">问答记录</p>
            <p className="mt-1 font-semibold">{queryLogCount}</p>
          </div>
          <div className="rounded-md border border-border bg-surface px-3 py-2">
            <p className="text-xs text-muted">生成记录</p>
            <p className="mt-1 font-semibold">{agentRunCount}</p>
          </div>
        </div>
      </div>
      <div className="border-t border-border bg-surface/70 px-3 py-3">
        <div className="flex gap-2 overflow-x-auto pb-1">
          {projectTabs.map((tab) => (
            <button
              key={tab.key}
              type="button"
              onClick={() => onTabChange(tab.key)}
              className={`flex shrink-0 items-center gap-2 rounded-md border px-3 py-2 text-sm ${
                activeProjectTab === tab.key
                  ? "border-brand bg-white text-brand shadow-panel"
                  : "border-transparent text-muted hover:border-border hover:bg-white hover:text-ink"
              }`}
            >
              <span>{tab.label}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
