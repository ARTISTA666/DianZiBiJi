"use client";

import { FormEvent } from "react";
import { ShieldCheck } from "lucide-react";
import type { AuditLog, User, Project } from "@/lib/api";
import { cardClass } from "../shared/utils";

interface AuditLogPanelProps {
  auditLogs: AuditLog[];
  auditFilters: { actor_user_id: string; project_id: string; action: string; date_from: string; date_to: string };
  onAuditFiltersChange: (filters: { actor_user_id: string; project_id: string; action: string; date_from: string; date_to: string }) => void;
  users: User[];
  projects: Project[];
  usersById: Map<number, User>;
  onSearch: (e: FormEvent<HTMLFormElement>) => void;
}

export function AuditLogPanel({
  auditLogs,
  auditFilters,
  onAuditFiltersChange,
  users,
  projects,
  usersById,
  onSearch,
}: AuditLogPanelProps) {
  return (
    <div className={cardClass("p-5")}>
      <h2 className="flex items-center gap-2 font-semibold"><ShieldCheck size={18} />审计日志</h2>
      <form onSubmit={onSearch} className="mt-4 grid gap-3 md:grid-cols-5">
        <select
          className="rounded-md border border-border px-3 py-2 text-sm"
          value={auditFilters.actor_user_id}
          onChange={(e) => onAuditFiltersChange({ ...auditFilters, actor_user_id: e.target.value })}
        >
          <option value="">全部用户</option>
          {users.map((u) => <option key={u.id} value={u.id}>{u.display_name}</option>)}
        </select>
        <select
          className="rounded-md border border-border px-3 py-2 text-sm"
          value={auditFilters.project_id}
          onChange={(e) => onAuditFiltersChange({ ...auditFilters, project_id: e.target.value })}
        >
          <option value="">全部项目</option>
          {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
        <input
          className="rounded-md border border-border px-3 py-2 text-sm"
          placeholder="动作"
          value={auditFilters.action}
          onChange={(e) => onAuditFiltersChange({ ...auditFilters, action: e.target.value })}
        />
        <input
          className="rounded-md border border-border px-3 py-2 text-sm"
          type="datetime-local"
          value={auditFilters.date_from}
          onChange={(e) => onAuditFiltersChange({ ...auditFilters, date_from: e.target.value })}
        />
        <div className="flex gap-2">
          <input
            className="min-w-0 flex-1 rounded-md border border-border px-3 py-2 text-sm"
            type="datetime-local"
            value={auditFilters.date_to}
            onChange={(e) => onAuditFiltersChange({ ...auditFilters, date_to: e.target.value })}
          />
          <button className="rounded-md bg-brand px-3 py-2 text-sm font-medium text-white">筛选</button>
        </div>
      </form>
      <div className="mt-4 max-h-80 overflow-auto rounded-md border border-border">
        <table className="w-full border-collapse text-left text-sm">
          <thead className="sticky top-0 bg-surface text-xs text-muted">
            <tr>
              <th className="px-3 py-2 font-medium">时间</th>
              <th className="px-3 py-2 font-medium">用户</th>
              <th className="px-3 py-2 font-medium">项目</th>
              <th className="px-3 py-2 font-medium">动作</th>
              <th className="px-3 py-2 font-medium">对象</th>
            </tr>
          </thead>
          <tbody>
            {auditLogs.length === 0 && (
              <tr><td colSpan={5} className="px-3 py-6 text-center text-muted">暂无审计记录</td></tr>
            )}
            {auditLogs.map((log) => (
              <tr key={log.id} className="border-t border-border">
                <td className="px-3 py-2">{new Date(log.created_at).toLocaleString("zh-CN")}</td>
                <td className="px-3 py-2">
                  {log.actor_user_id ? usersById.get(log.actor_user_id)?.display_name || log.actor_user_id : "-"}
                </td>
                <td className="px-3 py-2">
                  {log.project_id ? projects.find((p) => p.id === log.project_id)?.name || log.project_id : "-"}
                </td>
                <td className="px-3 py-2">{log.action}</td>
                <td className="px-3 py-2">{log.target_type || "-"} {log.target_id || ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
