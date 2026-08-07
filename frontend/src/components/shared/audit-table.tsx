"use client";

import { Fragment, useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { auditActionText } from "@/components/constants";
import type { AuditLog, User } from "@/lib/api";

interface AuditTableProps {
  logs: AuditLog[];
  /** 可选：有用户字典时显示用户名，否则退化为 #用户ID（如项目设置页无全量用户列表）。 */
  usersById?: Map<number, User>;
}

/** 详情摘要：取 detail_json 前几个键值拼接，便于快速扫读。 */
function summarizeDetail(detail: Record<string, unknown> | null | undefined): string {
  if (!detail) return "-";
  const entries = Object.entries(detail);
  if (entries.length === 0) return "-";
  return entries
    .slice(0, 3)
    .map(([key, value]) => {
      const text = typeof value === "string" ? value : JSON.stringify(value);
      const clipped = text.length > 24 ? `${text.slice(0, 24)}…` : text;
      return `${key}=${clipped}`;
    })
    .join("；");
}

function formatTime(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("zh-CN");
}

/**
 * 共享审计日志表格（全局审计页与项目设置页复用）。
 * E2E 依赖：动作原代码必须以独立 <code> 节点渲染（getByText 精确匹配）。
 */
export function AuditTable({ logs, usersById }: AuditTableProps) {
  const [expandedIds, setExpandedIds] = useState<Set<number>>(new Set());

  const toggleDetail = (id: number) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-8" aria-label="展开详情" />
            <TableHead>时间</TableHead>
            <TableHead>操作人</TableHead>
            <TableHead>动作</TableHead>
            <TableHead>目标</TableHead>
            <TableHead>项目</TableHead>
            <TableHead>详情摘要</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {logs.map((log) => {
            const expanded = expandedIds.has(log.id);
            const actionLabel = auditActionText[log.action];
            return (
              <Fragment key={log.id}>
                <TableRow>
                  <TableCell className="px-2">
                    <button
                      type="button"
                      aria-label={expanded ? `收起详情 ${log.id}` : `展开详情 ${log.id}`}
                      aria-expanded={expanded}
                      className="text-muted-foreground hover:text-foreground"
                      onClick={() => toggleDetail(log.id)}
                    >
                      {expanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                    </button>
                  </TableCell>
                  <TableCell className="whitespace-nowrap">{formatTime(log.created_at)}</TableCell>
                  <TableCell>
                    {log.actor_user_id
                      ? usersById?.get(log.actor_user_id)?.username || `#${log.actor_user_id}`
                      : "系统"}
                  </TableCell>
                  <TableCell>
                    <span className="inline-flex flex-wrap items-center gap-1.5">
                      <code className="text-xs">{log.action}</code>
                      {actionLabel && (
                        <span className="text-xs text-muted-foreground">{actionLabel}</span>
                      )}
                    </span>
                  </TableCell>
                  <TableCell>
                    {log.target_type || "-"}
                    {log.target_id ? ` #${log.target_id}` : ""}
                  </TableCell>
                  <TableCell>{log.project_id ? `#${log.project_id}` : "-"}</TableCell>
                  <TableCell className="max-w-64 truncate text-muted-foreground" title={JSON.stringify(log.detail_json)}>
                    {summarizeDetail(log.detail_json)}
                  </TableCell>
                </TableRow>
                {expanded && (
                  <TableRow>
                    <TableCell />
                    <TableCell colSpan={6}>
                      <pre className="max-h-64 overflow-auto rounded-md bg-muted/50 p-3 text-xs">
                        {JSON.stringify(log.detail_json, null, 2)}
                      </pre>
                    </TableCell>
                  </TableRow>
                )}
              </Fragment>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
