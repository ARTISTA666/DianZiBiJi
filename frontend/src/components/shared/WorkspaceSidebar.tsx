"use client";

import { LayoutDashboard, Settings } from "lucide-react";
import type { Project, Group, User } from "@/lib/api";
import { cardClass } from "./utils";

interface WorkspaceSidebarProps {
  workspaceView: "project" | "admin";
  projects: Project[];
  groups: Group[];
  users: User[];
  selectedProjectId: number | null;
  selectedGroupId: number | null;
  canAdmin: boolean;
  onSetWorkspaceView: (v: "project" | "admin") => void;
  onSetSelectedProjectId: (id: number | null) => void;
  onSetSelectedGroupId: (id: number | null) => void;
}

export function WorkspaceSidebar({
  workspaceView,
  projects,
  groups,
  users,
  selectedProjectId,
  selectedGroupId,
  canAdmin,
  onSetWorkspaceView,
  onSetSelectedProjectId,
  onSetSelectedGroupId,
}: WorkspaceSidebarProps) {
  return (
    <aside className={cardClass("min-w-0 self-start p-3 lg:sticky lg:top-6")}>
      <div className="grid grid-cols-2 gap-2 lg:grid-cols-1">
        <button
          type="button"
          onClick={() => onSetWorkspaceView("project")}
          className={`flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium ${workspaceView === "project" ? "bg-brand text-white" : "text-muted hover:bg-surface hover:text-ink"}`}
        >
          <LayoutDashboard size={17} />
          项目工作台
        </button>
        {canAdmin && (
          <button
            type="button"
            onClick={() => onSetWorkspaceView("admin")}
            className={`flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium ${workspaceView === "admin" ? "bg-brand text-white" : "text-muted hover:bg-surface hover:text-ink"}`}
          >
            <Settings size={17} />
            系统管理
          </button>
        )}
      </div>

      {workspaceView === "project" && (
        <div className="mt-4 border-t border-border pt-4">
          <div className="mb-3 flex items-center justify-between px-1 text-xs font-semibold text-muted">
            <span>我的项目</span>
            <span>{projects.length}</span>
          </div>
          <div className="space-y-2">
            {projects.length === 0 && <p className="px-2 py-4 text-sm text-muted">暂无可访问项目。</p>}
            {projects.map((project) => (
              <button
                key={project.id}
                onClick={() => onSetSelectedProjectId(project.id)}
                className={`w-full rounded-md border px-3 py-3 text-left text-sm transition-colors ${
                  selectedProjectId === project.id
                    ? "border-brand bg-[#edf7f5] text-ink"
                    : "border-transparent text-muted hover:border-border hover:bg-surface hover:text-ink"
                }`}
              >
                <span className="flex items-start justify-between gap-2 font-medium">
                  <span>{project.name}</span>
                </span>
                <span className="mt-1 block text-xs">{project.approval_enabled ? "审批流程已启用" : "无需审批"}</span>
              </button>
            ))}
          </div>
        </div>
      )}

      {workspaceView === "admin" && groups.length > 0 && (
        <div className="mt-4 border-t border-border pt-4">
          <div className="mb-3 flex items-center justify-between px-1 text-xs font-semibold text-muted">
            <span>小组</span>
            <span>{groups.length}</span>
          </div>
          <div className="space-y-2">
            {groups.map((group) => (
              <button
                key={group.id}
                onClick={() => onSetSelectedGroupId(group.id)}
                className={`w-full rounded-md border px-3 py-3 text-left text-sm transition-colors ${
                  selectedGroupId === group.id
                    ? "border-brand bg-[#edf7f5] text-ink"
                    : "border-transparent text-muted hover:border-border hover:bg-surface hover:text-ink"
                }`}
              >
                {group.name}
              </button>
            ))}
          </div>
        </div>
      )}
    </aside>
  );
}
