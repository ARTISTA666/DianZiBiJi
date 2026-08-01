"use client";

import { FormEvent, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { getAuditLogs, type AuditLog, type User } from "@/lib/api";
import { getErrorMessage } from "@/lib/utils";

interface Props {
  token: string;
  auditLogs: AuditLog[];
  usersById: Map<number, User>;
  busy: boolean;
  onLogsUpdate: (logs: AuditLog[]) => void;
  onError: (message: string) => void;
}

export function AuditLog({ token, auditLogs, usersById, busy, onLogsUpdate, onError }: Props) {
  const [auditActor, setAuditActor] = useState("");
  const [auditProject, setAuditProject] = useState("");
  const [auditAction, setAuditAction] = useState("");
  const [auditDateFrom, setAuditDateFrom] = useState("");
  const [auditDateTo, setAuditDateTo] = useState("");

  const handleAuditSearch = async (event: FormEvent) => {
    event.preventDefault();
    try {
      const result = await getAuditLogs(token, {
        actor_user_id: auditActor,
        project_id: auditProject,
        action: auditAction.trim(),
        date_from: auditDateFrom,
        date_to: auditDateTo,
      });
      onLogsUpdate(result.items);
    } catch (cause) {
      onError(getErrorMessage(cause, "审计日志查询失败"));
    }
  };

  return (
    <Card>
      <CardHeader><CardTitle className="text-base">全局审计日志</CardTitle></CardHeader>
      <CardContent className="space-y-4">
        <form className="grid gap-3 md:grid-cols-5" onSubmit={handleAuditSearch}>
          <Input aria-label="操作人 ID" type="number" placeholder="操作人 ID" value={auditActor} onChange={(event) => setAuditActor(event.target.value)} />
          <Input aria-label="项目 ID" type="number" placeholder="项目 ID" value={auditProject} onChange={(event) => setAuditProject(event.target.value)} />
          <Input aria-label="审计动作" placeholder="动作，如 create_user" value={auditAction} onChange={(event) => setAuditAction(event.target.value)} />
          <Input aria-label="开始时间" type="datetime-local" value={auditDateFrom} onChange={(event) => setAuditDateFrom(event.target.value)} />
          <Input aria-label="结束时间" type="datetime-local" value={auditDateTo} onChange={(event) => setAuditDateTo(event.target.value)} />
          <Button className="md:col-span-5" type="submit" disabled={busy}>查询审计日志</Button>
        </form>
        <div className="overflow-x-auto">
        <Table>
          <TableHeader><TableRow><TableHead>时间</TableHead><TableHead>操作人</TableHead><TableHead>动作</TableHead><TableHead>目标</TableHead><TableHead>项目</TableHead></TableRow></TableHeader>
          <TableBody>{auditLogs.map((log) => <TableRow key={log.id}><TableCell className="whitespace-nowrap">{new Date(log.created_at).toLocaleString("zh-CN")}</TableCell><TableCell>{log.actor_user_id ? usersById.get(log.actor_user_id)?.username || `#${log.actor_user_id}` : "系统"}</TableCell><TableCell><code className="text-xs">{log.action}</code></TableCell><TableCell>{log.target_type || "-"}{log.target_id ? ` #${log.target_id}` : ""}</TableCell><TableCell>{log.project_id ? `#${log.project_id}` : "-"}</TableCell></TableRow>)}</TableBody>
        </Table>
        </div>
        {auditLogs.length === 0 && <p className="text-center text-sm text-muted-foreground">没有匹配的审计记录。</p>}
      </CardContent>
    </Card>
  );
}
