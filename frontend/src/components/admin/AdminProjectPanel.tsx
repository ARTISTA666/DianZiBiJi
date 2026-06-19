"use client";

import { FormEvent } from "react";
import { Database } from "lucide-react";
import type { User } from "@/lib/api";
import { cardClass } from "../shared/utils";

interface AdminProjectPanelProps {
  users: User[];
  newProject: { name: string; description: string; is_sensitive: boolean; approval_enabled: boolean; owner_user_id: string };
  onNewProjectChange: (p: { name: string; description: string; is_sensitive: boolean; approval_enabled: boolean; owner_user_id: string }) => void;
  onCreateProject: (e: FormEvent<HTMLFormElement>) => void;
}

export function AdminProjectPanel({
  users,
  newProject,
  onNewProjectChange,
  onCreateProject,
}: AdminProjectPanelProps) {
  return (
    <form onSubmit={onCreateProject} className={cardClass("p-5")}>
      <h2 className="flex items-center gap-2 font-semibold"><Database size={18} />创建项目</h2>
      <div className="mt-4 grid gap-3 md:grid-cols-2">
        <input
          className="rounded-md border border-border px-3 py-2"
          placeholder="项目名称"
          value={newProject.name}
          onChange={(e) => onNewProjectChange({ ...newProject, name: e.target.value })}
          required
        />
        <select
          className="rounded-md border border-border px-3 py-2"
          value={newProject.owner_user_id}
          onChange={(e) => onNewProjectChange({ ...newProject, owner_user_id: e.target.value })}
        >
          <option value="">项目负责人可稍后设置</option>
          {users.map((u) => <option key={u.id} value={u.id}>{u.display_name}</option>)}
        </select>
        <textarea
          className="rounded-md border border-border px-3 py-2 md:col-span-2"
          placeholder="项目说明"
          value={newProject.description}
          onChange={(e) => onNewProjectChange({ ...newProject, description: e.target.value })}
        />
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={newProject.is_sensitive}
            onChange={(e) => onNewProjectChange({ ...newProject, is_sensitive: e.target.checked })}
          />敏感项目
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={newProject.approval_enabled}
            onChange={(e) => onNewProjectChange({ ...newProject, approval_enabled: e.target.checked })}
          />启用审批
        </label>
      </div>
      <button className="mt-4 flex items-center gap-2 rounded-md bg-brand px-4 py-2 text-sm font-medium text-white">
        <span>+</span>创建项目
      </button>
    </form>
  );
}
