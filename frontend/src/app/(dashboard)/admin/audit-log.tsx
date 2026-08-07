"use client";

import { FormEvent, useState } from "react";
import { ChevronLeft, ChevronRight, Download } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { AuditTable } from "@/components/shared/audit-table";
import { auditActionText } from "@/components/constants";
import { getAuditLogs, type AuditLog, type Project, type User } from "@/lib/api";
import { getErrorMessage } from "@/lib/utils";
import { useActionFeedback } from "@/hooks/use-action-feedback";

const PAGE_SIZE = 20;
const EXPORT_PAGE_SIZE = 200;
const EXPORT_LIMIT = 2000;
const ALL = "__all__";

interface Props {
  token: string;
  auditLogs: AuditLog[];
  auditTotal: number;
  usersById: Map<number, User>;
  projects: Project[];
  busy: boolean;
  onLogsUpdate: (logs: AuditLog[], total: number) => void;
  onError: (message: string) => void;
}

function buildFilters(actor: string, project: string, action: string, dateFrom: string, dateTo: string) {
  return {
    actor_user_id: actor === ALL ? "" : actor,
    project_id: project === ALL ? "" : project,
    action: action.trim(),
    date_from: dateFrom,
    date_to: dateTo,
  };
}

function escapeCsvCell(value: string) {
  return `"${value.replace(/"/g, "\"\"")}"`;
}

export function AuditLog({
  token,
  auditLogs,
  auditTotal,
  usersById,
  projects,
  busy,
  onLogsUpdate,
  onError,
}: Props) {
  const [auditActor, setAuditActor] = useState(ALL);
  const [auditProject, setAuditProject] = useState(ALL);
  const [auditAction, setAuditAction] = useState("");
  const [auditDateFrom, setAuditDateFrom] = useState("");
  const [auditDateTo, setAuditDateTo] = useState("");
  const [skip, setSkip] = useState(0);
  const [querying, setQuerying] = useState(false);
  const [exporting, setExporting] = useState(false);
  const feedback = useActionFeedback();

  const runQuery = async (nextSkip: number) => {
    setQuerying(true);
    try {
      const result = await getAuditLogs(token, {
        ...buildFilters(auditActor, auditProject, auditAction, auditDateFrom, auditDateTo),
        skip: nextSkip,
        limit: PAGE_SIZE,
      });
      setSkip(nextSkip);
      onLogsUpdate(result.items, result.total);
    } catch (cause) {
      onError(getErrorMessage(cause, "审计日志查询失败"));
    } finally {
      setQuerying(false);
    }
  };

  const handleAuditSearch = (event: FormEvent) => {
    event.preventDefault();
    void runQuery(0);
  };

  const totalPages = Math.max(1, Math.ceil(auditTotal / PAGE_SIZE));
  const currentPage = Math.floor(skip / PAGE_SIZE);

  const handleExport = async () => {
    setExporting(true);
    try {
      const filters = buildFilters(auditActor, auditProject, auditAction, auditDateFrom, auditDateTo);
      const all: AuditLog[] = [];
      let cursor = 0;
      let exportTotal = 0;
      while (cursor < EXPORT_LIMIT) {
        const result = await getAuditLogs(token, { ...filters, skip: cursor, limit: EXPORT_PAGE_SIZE });
        all.push(...result.items);
        exportTotal = result.total;
        if (result.items.length < EXPORT_PAGE_SIZE) break;
        cursor += EXPORT_PAGE_SIZE;
        if (cursor >= result.total) break;
      }
      const header = ["ID", "时间", "操作人", "动作代码", "动作中文", "目标类型", "目标ID", "项目ID", "详情"];
      const lines = all.map((log) => [
        String(log.id),
        new Date(log.created_at).toLocaleString("zh-CN"),
        log.actor_user_id
          ? usersById.get(log.actor_user_id)?.username || `#${log.actor_user_id}`
          : "系统",
        log.action,
        auditActionText[log.action] || "",
        log.target_type || "",
        log.target_id !== null ? String(log.target_id) : "",
        log.project_id !== null ? String(log.project_id) : "",
        JSON.stringify(log.detail_json ?? {}),
      ].map(escapeCsvCell).join(","));
      const csv = [header.map(escapeCsvCell).join(","), ...lines].join("\r\n");
      const blob = new Blob([`\uFEFF${csv}`], { type: "text/csv;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-");
      anchor.href = url;
      anchor.download = `audit-logs-${stamp}.csv`;
      anchor.click();
      URL.revokeObjectURL(url);
      // 达到导出上限时明确提示截断，避免管理员误以为文件完整。
      if (all.length < exportTotal) {
        feedback.success(`已导出前 ${all.length} 条审计记录（匹配 ${exportTotal} 条超过 ${EXPORT_LIMIT} 条上限，其余已截断）`);
      } else {
        feedback.success(`已导出 ${all.length} 条审计记录`);
      }
    } catch (cause) {
      onError(getErrorMessage(cause, "审计日志导出失败"));
    } finally {
      setExporting(false);
    }
  };

  return (
    <Card>
      <CardHeader><CardTitle className="text-base">全局审计日志</CardTitle></CardHeader>
      <CardContent className="space-y-4">
        <form className="grid gap-3 md:grid-cols-5" onSubmit={handleAuditSearch}>
          <Select value={auditActor} onValueChange={setAuditActor}>
            <SelectTrigger aria-label="操作人" className="w-full">
              <SelectValue placeholder="操作人" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL}>全部操作人</SelectItem>
              {[...usersById.values()].map((user) => (
                <SelectItem key={user.id} value={String(user.id)}>
                  {user.display_name}（{user.username}）
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={auditProject} onValueChange={setAuditProject}>
            <SelectTrigger aria-label="项目" className="w-full">
              <SelectValue placeholder="项目" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL}>全部项目</SelectItem>
              {projects.map((project) => (
                <SelectItem key={project.id} value={String(project.id)}>
                  {project.name}（#{project.id}）
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <div className="w-full">
            {/* 保留文本输入以支持自由输入兜底；datalist 提供动作建议 */}
            <Input
              aria-label="审计动作"
              list="audit-action-options"
              placeholder="动作，如 create_user"
              value={auditAction}
              onChange={(event) => setAuditAction(event.target.value)}
            />
            <datalist id="audit-action-options">
              {Object.entries(auditActionText).map(([code, label]) => (
                <option key={code} value={code}>{label}</option>
              ))}
            </datalist>
          </div>
          <Input aria-label="开始时间" type="datetime-local" value={auditDateFrom} onChange={(event) => setAuditDateFrom(event.target.value)} />
          <Input aria-label="结束时间" type="datetime-local" value={auditDateTo} onChange={(event) => setAuditDateTo(event.target.value)} />
          <div className="flex gap-2 md:col-span-5">
            <Button type="submit" disabled={busy || querying}>{querying ? "查询中..." : "查询审计日志"}</Button>
            <Button type="button" variant="outline" onClick={handleExport} disabled={busy || exporting || auditLogs.length === 0}>
              <Download className="mr-1 h-4 w-4" />{exporting ? "导出中..." : "导出 CSV"}
            </Button>
          </div>
        </form>

        <AuditTable logs={auditLogs} usersById={usersById} />

        {auditLogs.length === 0 && <p className="text-center text-sm text-muted-foreground">没有匹配的审计记录。</p>}

        {auditTotal > 0 && (
          <div className="flex items-center justify-between border-t pt-3">
            <p className="text-sm text-muted-foreground">共 {auditTotal} 条</p>
            {auditTotal > PAGE_SIZE && (
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={busy || querying || currentPage === 0}
                  onClick={() => void runQuery(Math.max(0, skip - PAGE_SIZE))}
                >
                  <ChevronLeft className="mr-1 h-4 w-4" />上一页
                </Button>
                <span className="text-sm text-muted-foreground">第 {currentPage + 1} / {totalPages} 页</span>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={busy || querying || skip + PAGE_SIZE >= auditTotal}
                  onClick={() => void runQuery(skip + PAGE_SIZE)}
                >
                  下一页<ChevronRight className="ml-1 h-4 w-4" />
                </Button>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
