"use client";

import { ShieldCheck } from "lucide-react";
import type { AuditLog, User } from "@/lib/api";
import { cardClass } from "../shared/utils";

interface ProjectLogsPanelProps {
  auditLogs: AuditLog[];
  usersById: Map<number, User>;
  canAdmin: boolean;
}

export function ProjectLogsPanel({ auditLogs, usersById, canAdmin }: ProjectLogsPanelProps) {
  return (
    <div className={cardClass("p-5")}>
      <h2 className="flex items-center gap-2 font-semibold"><ShieldCheck size={18} />项目日志</h2>
      {!canAdmin && <p className="mt-4 text-sm text-muted">当前账号没有审计日志查看权限。</p>}
      {canAdmin && (
        <div className="mt-4 max-h-96 overflow-auto rounded-md border border-border">
          <table className="w-full border-collapse text-left text-sm">
            <thead className="sticky top-0 bg-surface text-xs text-muted">
              <tr>
                <th className="px-3 py-2 font-medium">时间</th>
                <th className="px-3 py-2 font-medium">用户</th>
                <th className="px-3 py-2 font-medium">动作</th>
                <th className="px-3 py-2 font-medium">对象</th>
              </tr>
            </thead>
            <tbody>
              {auditLogs.length === 0 && (
                <tr><td colSpan={4} className="px-3 py-6 text-center text-muted">当前项目暂无审计记录</td></tr>
              )}
              {auditLogs.map((log) => (
                <tr key={log.id} className="border-t border-border">
                  <td className="px-3 py-2">{new Date(log.created_at).toLocaleString("zh-CN")}</td>
                  <td className="px-3 py-2">
                    {log.actor_user_id ? usersById.get(log.actor_user_id)?.display_name || log.actor_user_id : "-"}
                  </td>
                  <td className="px-3 py-2">{log.action}</td>
                  <td className="px-3 py-2">{log.target_type || "-"} {log.target_id || ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
